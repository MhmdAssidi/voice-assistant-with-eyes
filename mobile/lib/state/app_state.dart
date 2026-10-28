import 'dart:async';

import 'package:flutter/foundation.dart';

import '../l10n/strings.dart';
import '../services/api_client.dart';
import '../services/audio_service.dart';
import '../services/settings_service.dart';
import '../services/stream_service.dart';

/// What the app is doing right now. Each value has a status sentence that is
/// shown in large text and announced to the screen reader.
enum AppStatus { connecting, noServer, offline, ready, listening, thinking, error }

/// The single source of truth for the UI (simple ChangeNotifier state).
///
/// Screens listen to it and rebuild; it never touches widgets itself. Screen
/// reader announcements go out through [onAnnounce], which the home screen sets.
class AppState extends ChangeNotifier {
  AppState({
    SettingsService? settingsService,
    ApiClient? api,
    CameraStreamer? streamer,
    QuestionRecorder? recorder,
    this.healthCheckInterval = const Duration(seconds: 5),
    this.maxRecording = const Duration(seconds: 10),
    this.minRecording = const Duration(milliseconds: 700),
  })  : _settingsService = settingsService ?? SettingsService(),
        _api = api ?? ApiClient(),
        _streamer = streamer ?? WhipStreamService(),
        _recorder = recorder ?? MicRecorder() {
    _streamer.status.addListener(_onCameraStatusChanged);
  }

  final SettingsService _settingsService;
  final ApiClient _api;
  final CameraStreamer _streamer;
  final QuestionRecorder _recorder;
  final Duration healthCheckInterval;

  /// Recording stops by itself after this (questions are short).
  final Duration maxRecording;

  /// Shorter recordings are treated as an accidental tap.
  final Duration minRecording;

  Settings _settings = const Settings(serverHost: '', language: 'en');
  AppStatus _status = AppStatus.connecting;
  CameraStatus _lastCameraStatus = CameraStatus.off;
  AskResponse? _lastResponse;
  Timer? _healthTimer;
  Timer? _autoStop;
  bool _paused = false; // app in the background
  bool _busy = false; // a start/stop of the recorder is in progress
  int _failedChecks = 0; // health checks failed in a row

  /// Called with every sentence that should be spoken by TalkBack.
  void Function(String message)? onAnnounce;

  Settings get settings => _settings;
  AppStatus get status => _status;
  CameraStatus get cameraStatus => _streamer.status.value;
  CameraStreamer get streamer => _streamer;
  AskResponse? get lastResponse => _lastResponse;
  String? get lastAnswer => _lastResponse?.answer;
  AppStrings get strings => AppStrings.of(_settings.language);

  String get statusText => switch (_status) {
        AppStatus.connecting => strings.statusConnecting,
        AppStatus.noServer => strings.statusNoServer,
        AppStatus.offline => strings.statusOffline,
        AppStatus.ready => strings.statusReady,
        AppStatus.listening => strings.statusListening,
        AppStatus.thinking => strings.statusThinking,
        AppStatus.error => strings.statusError,
      };

  String get cameraText => switch (cameraStatus) {
        CameraStatus.off => strings.cameraOff,
        CameraStatus.connecting => strings.cameraConnecting,
        CameraStatus.streaming => strings.cameraConnected,
        CameraStatus.reconnecting => strings.cameraDisconnected,
      };

  /// Statuses where nothing is in progress, so a health check may change them.
  bool get _isIdle => const {
        AppStatus.connecting,
        AppStatus.noServer,
        AppStatus.offline,
        AppStatus.ready,
        AppStatus.error,
      }.contains(_status);

  /// Loads the saved settings. Call once before the first frame.
  Future<void> loadSettings() async {
    _settings = await _settingsService.load();
    if (!_settings.hasServer) _status = AppStatus.noServer;
    notifyListeners();
  }

  /// Checks the server now and then every [healthCheckInterval], so the user
  /// hears it when the connection is lost or comes back.
  void startMonitoring() {
    _healthTimer?.cancel();
    checkServer();
    _healthTimer = Timer.periodic(healthCheckInterval, (_) => checkServer());
  }

  /// App sent to the background: Android takes the camera away anyway, so we
  /// stop cleanly (MediaMTX frees the "live" path) and stop polling.
  Future<void> onAppPaused() async {
    _paused = true;
    _healthTimer?.cancel();
    _healthTimer = null;
    if (_status == AppStatus.listening) await _finishRecording(send: false);
    await _streamer.stop();
  }

  /// App back in front: check the server again, which restarts the camera.
  void onAppResumed() {
    _paused = false;
    startMonitoring();
  }

  Future<void> checkServer() async {
    if (!_settings.hasServer) {
      if (_isIdle) _setStatus(AppStatus.noServer);
      return;
    }
    final host = _settings.serverHost;
    final reachable = await _api.isServerReachable(host);
    _failedChecks = reachable ? 0 : _failedChecks + 1;
    // Once ready, one lost check (a dropped Wi-Fi packet) is not enough to
    // say "server not reachable": wait for a second failure in a row.
    if (!reachable && _status == AppStatus.ready && _failedChecks < 2) return;
    // Server found: start the camera (does nothing if it already streams
    // there; if the connection drops, the streamer reconnects by itself).
    // (_paused: this check may have started just before the app went away.)
    if (reachable && !_paused) unawaited(_streamer.start(host));
    // Never interrupt a question in progress.
    if (_isIdle) _setStatus(reachable ? AppStatus.ready : AppStatus.offline);
  }

  /// Speaks "Camera connected" / "Camera disconnected" when it changes.
  void _onCameraStatusChanged() {
    final now = cameraStatus;
    final before = _lastCameraStatus;
    _lastCameraStatus = now;
    notifyListeners();
    // Do not talk over the user while they are asking a question.
    if (_status == AppStatus.listening) return;
    if (now == CameraStatus.streaming && before != CameraStatus.streaming) {
      _announce(strings.cameraConnected);
    } else if (before == CameraStatus.streaming && now != CameraStatus.streaming) {
      _announce(strings.cameraDisconnected);
    }
  }

  Future<void> updateSettings(Settings newSettings) async {
    await _settingsService.save(newSettings);
    _settings = newSettings;
    notifyListeners();
    _announce(strings.saved);
    if (_isIdle) _setStatus(AppStatus.connecting, announce: false);
    await checkServer();
  }

  /// The big button: tap once to start recording, tap again to send.
  Future<void> onAskPressed() async {
    if (_busy) return; // the recorder is still starting or stopping
    switch (_status) {
      case AppStatus.ready:
      case AppStatus.error:
        await _startRecording();
      case AppStatus.listening:
        await _finishRecording();
      case AppStatus.thinking:
        break; // already busy: ignore extra taps
      case AppStatus.connecting:
      case AppStatus.noServer:
      case AppStatus.offline:
        _announce(statusText); // repeat why asking is not possible yet
    }
  }

  Future<void> _startRecording() async {
    _busy = true;
    try {
      if (!await _recorder.hasPermission()) {
        _announce(strings.micDenied);
        return;
      }
      // Not announced on purpose: the screen reader's voice would be recorded
      // into the question. The start beep + vibration is the signal instead.
      _setStatus(AppStatus.listening, announce: false);
      await _recorder.start();
      _autoStop = Timer(maxRecording, () => _finishRecording());
    } catch (e) {
      debugPrint('[ask] could not start recording: $e');
      _setStatus(AppStatus.error);
    } finally {
      _busy = false;
    }
  }

  /// Stops recording and, unless [send] is false, uploads the question.
  Future<void> _finishRecording({bool send = true}) async {
    if (_status != AppStatus.listening || _busy) return;
    _busy = true;
    _autoStop?.cancel();
    RecordedAudio? audio;
    try {
      audio = await _recorder.stop();
    } catch (e) {
      debugPrint('[ask] could not stop recording: $e');
    } finally {
      _busy = false;
    }

    if (!send) {
      _setStatus(AppStatus.ready, announce: false);
      return;
    }
    if (audio == null || audio.duration < minRecording) {
      _setStatus(AppStatus.ready, announce: false);
      _announce(strings.tooShort);
      return;
    }

    _setStatus(AppStatus.thinking);
    try {
      final response = await _api.ask(
        _settings.serverHost,
        audio.path,
        langHint: _settings.language,
      );
      _lastResponse = response;
      _setStatus(AppStatus.ready, announce: false);
      // TODO(B9): speak it with text-to-speech in response.language.
      _announce(response.answer);
    } on TimeoutException {
      _setStatus(AppStatus.error, announce: false);
      _announce(strings.serverTooSlow);
    } catch (e) {
      debugPrint('[ask] upload failed: $e');
      _setStatus(AppStatus.error);
    }
  }

  void _setStatus(AppStatus status, {bool announce = true}) {
    if (status == _status) return;
    _status = status;
    notifyListeners();
    if (announce) _announce(statusText);
  }

  void _announce(String message) => onAnnounce?.call(message);

  @override
  void dispose() {
    _healthTimer?.cancel();
    _autoStop?.cancel();
    _streamer.status.removeListener(_onCameraStatusChanged);
    unawaited(_streamer.stop());
    super.dispose();
  }
}
