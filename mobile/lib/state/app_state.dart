import 'dart:async';

import 'package:flutter/foundation.dart';

import '../l10n/strings.dart';
import '../services/api_client.dart';
import '../services/settings_service.dart';

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
    this.healthCheckInterval = const Duration(seconds: 5),
    this.fakeAnswerDelay = const Duration(seconds: 1),
  })  : _settingsService = settingsService ?? SettingsService(),
        _api = api ?? ApiClient();

  final SettingsService _settingsService;
  final ApiClient _api;
  final Duration healthCheckInterval;
  final Duration fakeAnswerDelay;

  Settings _settings = const Settings(serverHost: '', language: 'en');
  AppStatus _status = AppStatus.connecting;
  String? _lastAnswer;
  Timer? _healthTimer;

  /// Called with every sentence that should be spoken by TalkBack.
  void Function(String message)? onAnnounce;

  Settings get settings => _settings;
  AppStatus get status => _status;
  String? get lastAnswer => _lastAnswer;
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

  Future<void> checkServer() async {
    if (!_settings.hasServer) {
      if (_isIdle) _setStatus(AppStatus.noServer);
      return;
    }
    final reachable = await _api.isServerReachable(_settings.serverHost);
    // Never interrupt a question in progress; B5 handles errors during it.
    if (_isIdle) _setStatus(reachable ? AppStatus.ready : AppStatus.offline);
  }

  Future<void> updateSettings(Settings newSettings) async {
    await _settingsService.save(newSettings);
    _settings = newSettings;
    notifyListeners();
    _announce(strings.saved);
    if (_isIdle) _setStatus(AppStatus.connecting, announce: false);
    await checkServer();
  }

  /// The big button: tap once to start listening, tap again to send.
  Future<void> onAskPressed() async {
    switch (_status) {
      case AppStatus.ready:
      case AppStatus.error:
        // TODO(B5): start recording here.
        _setStatus(AppStatus.listening);
      case AppStatus.listening:
        // TODO(B5): stop recording and upload to POST /api/ask.
        _setStatus(AppStatus.thinking);
        await Future<void>.delayed(fakeAnswerDelay);
        _lastAnswer = strings.testAnswer;
        _setStatus(AppStatus.ready, announce: false);
        _announce(_lastAnswer!);
      case AppStatus.thinking:
        break; // already busy: ignore extra taps
      case AppStatus.connecting:
      case AppStatus.noServer:
      case AppStatus.offline:
        _announce(statusText); // repeat why asking is not possible yet
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
    super.dispose();
  }
}
