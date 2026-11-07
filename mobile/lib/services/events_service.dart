import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:web_socket_channel/io.dart';

import 'api_client.dart';

/// A hazard seen by Student A's worker (A11): the `warning` event of the contract,
/// {kind: "closed_door" | "stairs", confidence, frame_id, position}.
class HazardWarning {
  const HazardWarning({required this.kind, required this.confidence, this.position = 'center'});

  /// The kinds the phone knows how to say; any other kind is ignored.
  static const kinds = {'closed_door', 'stairs'};

  final String kind;
  final double confidence;
  final String position;

  /// The warning inside one WebSocket message, or null for every other event
  /// (frame_stored, ingest_status, question_answered) and for broken messages.
  static HazardWarning? fromMessage(Object? message) {
    if (message is! String) return null;
    try {
      final event = jsonDecode(message);
      if (event is! Map<String, dynamic> || event['type'] != 'warning') return null;
      final data = event['data'];
      if (data is! Map<String, dynamic>) return null;
      final kind = data['kind'];
      if (kind is! String || !kinds.contains(kind)) return null;
      return HazardWarning(
        kind: kind,
        confidence: (data['confidence'] as num?)?.toDouble() ?? 0,
        position: data['position'] as String? ?? 'center',
      );
    } on FormatException {
      return null;
    } on TypeError {
      return null;
    }
  }
}

/// Delivers hazard warnings from the server. An interface so tests can use a fake.
abstract interface class WarningSource {
  Stream<HazardWarning> get warnings;

  /// Connects to the server at [host] and stays connected (reconnects by itself).
  /// Does nothing if it is already connected or connecting to that host.
  void start(String host);

  Future<void> stop();
}

/// Listens on the backend's WebSocket `ws://<laptop>:8000/ws/events` (task B12).
///
/// The server broadcasts every event to everyone (the dashboard needs them all);
/// the phone keeps only the `warning` ones.
class EventsService implements WarningSource {
  /// Wait before trying again after the connection failed or dropped.
  static const retryDelay = Duration(seconds: 5);

  /// A ping every 10 s: a dead Wi-Fi connection is noticed (and repaired) quickly,
  /// instead of the phone silently waiting for warnings that can never arrive.
  static const pingInterval = Duration(seconds: 10);

  final _warnings = StreamController<HazardWarning>.broadcast();
  IOWebSocketChannel? _channel;
  StreamSubscription<dynamic>? _subscription;
  Timer? _retry;
  String? _host; // the host we want to be connected to (null = stopped)

  @override
  Stream<HazardWarning> get warnings => _warnings.stream;

  @override
  void start(String host) {
    if (_host == host) return; // already connected or (re)connecting there
    _host = host;
    _closeConnection();
    _connect();
  }

  Future<void> _connect() async {
    final host = _host;
    if (host == null) return;
    final uri = ApiClient.baseUri(host).replace(scheme: 'ws', path: '/ws/events');
    final channel = IOWebSocketChannel.connect(
      uri,
      pingInterval: pingInterval,
      connectTimeout: const Duration(seconds: 5),
    );
    _channel = channel;
    try {
      await channel.ready;
    } catch (e) {
      debugPrint('[events] could not connect to $uri: $e');
      if (_channel == channel) _retryLater();
      return;
    }
    if (_channel != channel) return; // stopped or moved to another host meanwhile
    debugPrint('[events] listening for warnings on $uri');
    _subscription = channel.stream.listen(
      (message) {
        final warning = HazardWarning.fromMessage(message);
        if (warning != null) _warnings.add(warning);
      },
      onError: (Object e) => debugPrint('[events] connection error: $e'),
      onDone: () {
        if (_channel != channel) return;
        debugPrint('[events] connection closed, retrying');
        _retryLater();
      },
    );
  }

  void _retryLater() {
    _closeConnection();
    _retry = Timer(retryDelay, _connect);
  }

  void _closeConnection() {
    _retry?.cancel();
    _retry = null;
    unawaited(_subscription?.cancel());
    _subscription = null;
    unawaited(_channel?.sink.close().catchError((Object _) {}));
    _channel = null;
  }

  @override
  Future<void> stop() async {
    _host = null;
    _closeConnection();
  }
}

/// The vibration that comes with a spoken warning. An interface so tests can use a fake.
abstract interface class WarningBuzzer {
  Future<void> buzz();
}

/// Two long pulses, clearly different from the single short tap of the
/// record start/stop (B5), so a warning is felt even before it is heard.
class PhoneBuzzer implements WarningBuzzer {
  static const _cues = MethodChannel('edu.ua.vaeyes/cues');

  @override
  Future<void> buzz() async {
    try {
      await _cues.invokeMethod<void>('warn');
    } catch (e) {
      debugPrint('[events] no warning vibration: $e');
      await HapticFeedback.vibrate(); // at least the phone's standard buzz
    }
  }
}
