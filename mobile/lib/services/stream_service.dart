import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:http/http.dart' as http;

/// Is the phone's camera reaching the laptop?
enum CameraStatus { off, connecting, streaming, reconnecting }

/// Sends the camera to the server. An interface so tests can use a fake.
abstract interface class CameraStreamer {
  ValueListenable<CameraStatus> get status;

  /// Local camera (for an on-screen preview), null when the camera is off.
  MediaStream? get localStream;

  /// Starts streaming to [host] and keeps reconnecting until [stop] is called.
  Future<void> start(String host);

  Future<void> stop();
}

/// Publishes the back camera to MediaMTX with WebRTC + WHIP (task B3).
///
/// WHIP in one sentence: we POST our SDP offer (a text describing our video)
/// to http://HOST:8889/live/whip and MediaMTX answers with its own SDP; after
/// that the video flows over UDP port 8189.
///
/// Fixed choices (see B1): back camera, 640x480, 15 fps, video only (the
/// microphone stays free for questions), H264 (VLC and OpenCV cannot read the
/// AV1 that Android/Chrome may pick by default).
class WhipStreamService implements CameraStreamer {
  static const whipPort = 8889;
  static const streamPath = 'live';

  /// Time allowed for ICE gathering (collecting our network addresses).
  static const iceGatheringTimeout = Duration(seconds: 2);

  /// Time allowed from sending the offer until video is actually flowing.
  static const connectTimeout = Duration(seconds: 10);

  final _status = ValueNotifier<CameraStatus>(CameraStatus.off);
  final http.Client _http = http.Client();

  String? _host;
  bool _wanted = false; // true between start() and stop()
  int _attempt = 0; // failed attempts in a row, for the back-off delay
  int _generation = 0; // ignores callbacks from an old, closed connection
  MediaStream? _camera;
  RTCPeerConnection? _peer;
  Uri? _sessionUri; // WHIP session URL, DELETE it to free the "live" path
  Timer? _retryTimer;
  Timer? _connectWatchdog;

  @override
  ValueListenable<CameraStatus> get status => _status;

  @override
  MediaStream? get localStream => _camera;

  static Uri whipUri(String host) =>
      Uri(scheme: 'http', host: host, port: whipPort, path: '/$streamPath/whip');

  @override
  Future<void> start(String host) async {
    if (_wanted && _host == host) return; // already streaming there
    await stop();
    _host = host;
    _wanted = true;
    _attempt = 0;
    await _connect();
  }

  @override
  Future<void> stop() async {
    _wanted = false;
    _retryTimer?.cancel();
    await _closePeer();
    final camera = _camera;
    _camera = null;
    if (camera != null) {
      for (final track in camera.getTracks()) {
        await track.stop();
      }
      await camera.dispose();
    }
    _status.value = CameraStatus.off;
  }

  Future<void> _connect() async {
    if (!_wanted) return;
    final generation = ++_generation;
    _status.value = _attempt == 0 ? CameraStatus.connecting : CameraStatus.reconnecting;
    try {
      _camera ??= await navigator.mediaDevices.getUserMedia({
        'audio': false,
        'video': {'facingMode': 'environment', 'width': 640, 'height': 480, 'frameRate': 15},
      });

      // No STUN/TURN servers: phone and laptop are on the same network.
      final peer = await createPeerConnection({'iceServers': [], 'sdpSemantics': 'unified-plan'});
      _peer = peer;
      peer.onConnectionState = (state) => _onConnectionState(generation, state);

      final transceiver = await peer.addTransceiver(
        track: _camera!.getVideoTracks().first,
        kind: RTCRtpMediaType.RTCRtpMediaTypeVideo,
        init: RTCRtpTransceiverInit(
          direction: TransceiverDirection.SendOnly,
          // Enough for 640x480 and gentle on a busy Wi-Fi.
          sendEncodings: [RTCRtpEncoding(maxBitrate: 1000000, maxFramerate: 15)],
        ),
      );
      await _preferH264(transceiver);

      // flutter_webrtc's default offer also asks to RECEIVE audio and video
      // (made for video calls). That adds two extra tracks and MediaMTX refuses
      // the offer with 406 "only a single video and a single audio track".
      await peer.setLocalDescription(await peer.createOffer({
        'mandatory': {'OfferToReceiveAudio': false, 'OfferToReceiveVideo': false},
        'optional': [],
      }));
      await _waitForIceGathering(peer);
      final offer = await peer.getLocalDescription();

      // Body as bytes: with a String body, package:http would append
      // "; charset=utf-8" and MediaMTX only accepts exactly application/sdp.
      final response = await _http
          .post(
            whipUri(_host!),
            headers: {'Content-Type': 'application/sdp'},
            body: utf8.encode(offer!.sdp!),
          )
          .timeout(const Duration(seconds: 5));
      if (response.statusCode != 201) {
        throw StateError('WHIP answered ${response.statusCode}: ${response.body}');
      }
      final location = response.headers['location'];
      _sessionUri = location == null ? null : whipUri(_host!).resolve(location);

      if (generation != _generation) return; // stop() was called meanwhile
      await peer.setRemoteDescription(RTCSessionDescription(response.body, 'answer'));

      // The answer is accepted, but video only flows once ICE connects.
      _connectWatchdog?.cancel();
      _connectWatchdog = Timer(connectTimeout, () {
        if (generation == _generation && _status.value != CameraStatus.streaming) {
          debugPrint('[stream] no connection after ${connectTimeout.inSeconds} s');
          _retry(generation);
        }
      });
    } catch (e) {
      debugPrint('[stream] connect failed: $e');
      _retry(generation);
    }
  }

  void _onConnectionState(int generation, RTCPeerConnectionState state) {
    if (generation != _generation) return;
    debugPrint('[stream] $state');
    switch (state) {
      case RTCPeerConnectionState.RTCPeerConnectionStateConnected:
        _connectWatchdog?.cancel();
        _attempt = 0;
        _status.value = CameraStatus.streaming;
      case RTCPeerConnectionState.RTCPeerConnectionStateDisconnected:
      case RTCPeerConnectionState.RTCPeerConnectionStateFailed:
        _retry(generation);
      default:
        break;
    }
  }

  /// Closes the broken connection and tries again after a growing delay.
  void _retry(int generation) {
    if (!_wanted || generation != _generation) return;
    _generation++; // ignore any further callback from the broken connection
    _status.value = CameraStatus.reconnecting;
    final delay = Duration(seconds: 1 << _attempt.clamp(0, 4)); // 1, 2, 4, 8, 16, 16...
    _attempt++;
    debugPrint('[stream] retry in ${delay.inSeconds} s');
    _retryTimer?.cancel();
    _retryTimer = Timer(delay, () async {
      await _closePeer();
      await _connect();
    });
  }

  Future<void> _closePeer() async {
    _connectWatchdog?.cancel();
    final peer = _peer;
    final session = _sessionUri;
    _peer = null;
    _sessionUri = null;
    if (session != null) {
      // Tell MediaMTX we left, so the next connection is not refused with
      // "someone is already publishing" (the problem we saw in B1).
      try {
        await _http.delete(session).timeout(const Duration(seconds: 2));
      } catch (_) {
        // Server unreachable: it will notice the timeout by itself.
      }
    }
    if (peer != null) {
      await peer.close();
      await peer.dispose();
    }
  }

  /// Puts H264 first in the offer. Constrained Baseline with
  /// packetization-mode=1 is the most widely decodable variant.
  static Future<void> _preferH264(RTCRtpTransceiver transceiver) async {
    final capabilities = await getRtpSenderCapabilities('video');
    final h264 = (capabilities.codecs ?? [])
        .where((c) => c.mimeType.toLowerCase() == 'video/h264')
        .toList();
    if (h264.isEmpty) {
      debugPrint('[stream] WARNING: no H264 encoder on this phone, using the default codec');
      return;
    }
    int score(RTCRtpCodecCapability c) {
      final fmtp = c.sdpFmtpLine ?? '';
      return (fmtp.contains('profile-level-id=42e0') ? 2 : 0) +
          (fmtp.contains('packetization-mode=1') ? 1 : 0);
    }

    h264.sort((a, b) => score(b).compareTo(score(a)));
    await transceiver.setCodecPreferences(h264);
  }

  /// Waits until all our network addresses are in the offer (WHIP sends the
  /// offer only once, so late addresses would be lost), at most 2 seconds.
  static Future<void> _waitForIceGathering(RTCPeerConnection peer) async {
    if (peer.iceGatheringState == RTCIceGatheringState.RTCIceGatheringStateComplete) return;
    final done = Completer<void>();
    peer.onIceGatheringState = (state) {
      if (state == RTCIceGatheringState.RTCIceGatheringStateComplete && !done.isCompleted) {
        done.complete();
      }
    };
    await done.future.timeout(iceGatheringTimeout, onTimeout: () {});
  }
}
