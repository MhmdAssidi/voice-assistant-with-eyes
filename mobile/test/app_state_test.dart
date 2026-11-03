import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart' show MediaStream;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:va_mobile/services/api_client.dart';
import 'package:va_mobile/services/audio_service.dart';
import 'package:va_mobile/services/settings_service.dart';
import 'package:va_mobile/services/stream_service.dart';
import 'package:va_mobile/services/tts_service.dart';
import 'package:va_mobile/state/app_state.dart';

/// Pretends to be the server so tests need no network.
class FakeApi extends ApiClient {
  FakeApi({this.reachable = true});

  bool reachable;
  String answerLanguage = 'en';
  Object? askError; // thrown by ask() when set
  final asked = <(String path, String? langHint)>[];

  @override
  Future<bool> isServerReachable(String host) async => reachable;

  @override
  Future<AskResponse> ask(String host, String audioPath, {String? langHint}) async {
    asked.add((audioPath, langHint));
    if (askError != null) throw askError!;
    return AskResponse(
      id: 1,
      question: 'what is in front of me?',
      language: answerLanguage,
      answer: 'A door with an exit sign.',
      confident: true,
      timingsMs: {'total': 900},
    );
  }
}

/// Pretends to be the camera stream; tests change [status] by hand.
class FakeStreamer implements CameraStreamer {
  final startedHosts = <String>[];

  @override
  final ValueNotifier<CameraStatus> status = ValueNotifier(CameraStatus.off);

  @override
  MediaStream? get localStream => null;

  @override
  Future<void> start(String host) async {
    if (startedHosts.isEmpty || startedHosts.last != host) startedHosts.add(host);
  }

  @override
  Future<void> stop() async => status.value = CameraStatus.off;
}

/// Pretends to be the microphone.
class FakeRecorder implements QuestionRecorder {
  bool permission = true;
  bool recording = false;
  Duration duration = const Duration(seconds: 2);

  @override
  Future<bool> hasPermission() async => permission;

  @override
  Future<void> start() async => recording = true;

  @override
  Future<RecordedAudio?> stop() async {
    recording = false;
    return RecordedAudio(path: '/tmp/question.m4a', duration: duration);
  }
}

/// Pretends to be the phone's voice. By default a sentence "ends" at once;
/// with [holdAnswers], speak() waits until stop() is called (to test stopping).
class FakeSpeaker implements Speaker {
  FakeSpeaker({this.holdAnswers = false});

  final bool holdAnswers;
  final spoken = <(String text, String language)>[];
  int stops = 0;
  Completer<void>? _current;

  @override
  Future<void> speak(String text, String language) async {
    spoken.add((text, language));
    if (!holdAnswers) return;
    _current = Completer<void>();
    await _current!.future;
  }

  @override
  Future<void> stop() async {
    stops++;
    if (_current?.isCompleted == false) _current!.complete();
  }

  @override
  Future<Map<String, bool>> voices() async => {'en': true, 'fr': true, 'ar': false};
}

class Harness {
  Harness(this.state, this.api, this.streamer, this.recorder, this.speaker, this.announced);

  final AppState state;
  final FakeApi api;
  final FakeStreamer streamer;
  final FakeRecorder recorder;
  final FakeSpeaker speaker;
  final List<String> announced;
}

Future<Harness> makeState({
  Map<String, Object> saved = const {'server_host': '192.168.0.105'},
  bool reachable = true,
  Duration maxRecording = const Duration(seconds: 10),
  FakeSpeaker? speaker,
}) async {
  SharedPreferences.setMockInitialValues(saved);
  final api = FakeApi(reachable: reachable);
  final streamer = FakeStreamer();
  final recorder = FakeRecorder();
  final voice = speaker ?? FakeSpeaker();
  final state = AppState(
    api: api,
    streamer: streamer,
    recorder: recorder,
    speaker: voice,
    maxRecording: maxRecording,
  );
  final announced = <String>[];
  state.onAnnounce = announced.add;
  await state.loadSettings();
  await state.checkServer();
  return Harness(state, api, streamer, recorder, voice, announced);
}

void main() {
  group('server and settings', () {
    test('no saved server -> asks the user to set it', () async {
      final h = await makeState(saved: {});
      expect(h.state.status, AppStatus.noServer);
    });

    test('server reachable -> ready, and it is announced', () async {
      final h = await makeState();
      expect(h.state.status, AppStatus.ready);
      expect(h.announced, [h.state.strings.statusReady]);
    });

    test('connection lost after 2 failed checks, announced once', () async {
      final h = await makeState();
      h.api.reachable = false;
      await h.state.checkServer();
      expect(h.state.status, AppStatus.ready, reason: 'one failed check is ignored');
      await h.state.checkServer();
      await h.state.checkServer(); // still offline: no second announcement
      expect(h.state.status, AppStatus.offline);
      expect(h.announced.where((m) => m == h.state.strings.statusOffline).length, 1);
    });

    test('a single failed check between good ones does not flicker', () async {
      final h = await makeState();
      h.api.reachable = false;
      await h.state.checkServer();
      h.api.reachable = true;
      await h.state.checkServer();
      h.api.reachable = false;
      await h.state.checkServer();
      expect(h.state.status, AppStatus.ready);
      expect(h.announced, [h.state.strings.statusReady]);
    });

    test('settings are saved and the language changes the texts', () async {
      final h = await makeState(saved: {});
      await h.state.updateSettings(const Settings(serverHost: '10.0.0.5', language: 'fr'));

      expect(h.state.status, AppStatus.ready);
      expect(h.state.strings.askButton, 'Poser une question');
      final reloaded = await SettingsService().load();
      expect(reloaded.serverHost, '10.0.0.5');
      expect(reloaded.language, 'fr');
    });

    test('normalizeHost cleans what the user typed', () {
      expect(SettingsService.normalizeHost(' 192.168.0.105 '), '192.168.0.105');
      expect(SettingsService.normalizeHost('http://192.168.0.105:8000/'), '192.168.0.105');
      expect(SettingsService.normalizeHost('my-laptop.local'), 'my-laptop.local');
      expect(SettingsService.normalizeHost(''), isNull);
      expect(SettingsService.normalizeHost('192 168 0 1'), isNull);
    });
  });

  group('asking a question (B5)', () {
    test('tap, tap -> records, uploads with the language hint, shows the answer', () async {
      final h = await makeState();
      h.announced.clear();

      await h.state.onAskPressed();
      expect(h.state.status, AppStatus.listening);
      expect(h.recorder.recording, isTrue);
      expect(h.announced, isEmpty, reason: 'nothing spoken while recording');

      await h.state.onAskPressed();
      expect(h.recorder.recording, isFalse);
      expect(h.api.asked.single, ('/tmp/question.m4a', 'en'));
      expect(h.state.status, AppStatus.ready);
      expect(h.state.lastAnswer, 'A door with an exit sign.');
      expect(h.announced, [h.state.strings.statusThinking]);
      expect(h.speaker.spoken.last, ('A door with an exit sign.', 'en'));
    });

    test('recording stops by itself after the maximum time', () async {
      final h = await makeState(maxRecording: const Duration(milliseconds: 20));
      await h.state.onAskPressed();
      await Future<void>.delayed(const Duration(milliseconds: 60));
      expect(h.recorder.recording, isFalse);
      expect(h.api.asked, hasLength(1));
      expect(h.state.lastAnswer, isNotNull);
    });

    test('a very short tap is not uploaded', () async {
      final h = await makeState();
      h.recorder.duration = const Duration(milliseconds: 200);
      await h.state.onAskPressed();
      await h.state.onAskPressed();
      expect(h.api.asked, isEmpty);
      expect(h.state.status, AppStatus.ready);
      expect(h.announced.last, h.state.strings.tooShort);
    });

    test('no microphone permission -> explains, does not record', () async {
      final h = await makeState();
      h.recorder.permission = false;
      await h.state.onAskPressed();
      expect(h.recorder.recording, isFalse);
      expect(h.state.status, AppStatus.ready);
      expect(h.announced.last, h.state.strings.micDenied);
    });

    test('server too slow -> error with a clear message, can ask again', () async {
      final h = await makeState();
      h.api.askError = TimeoutException('slow');
      await h.state.onAskPressed();
      await h.state.onAskPressed();
      expect(h.state.status, AppStatus.error);
      expect(h.announced.last, h.state.strings.serverTooSlow);

      await h.state.onAskPressed(); // error -> can start again
      expect(h.state.status, AppStatus.listening);
    });

    test('server error -> error status announced', () async {
      final h = await makeState();
      h.api.askError = ApiException(500, 'boom');
      await h.state.onAskPressed();
      await h.state.onAskPressed();
      expect(h.state.status, AppStatus.error);
      expect(h.announced.last, h.state.strings.statusError);
    });

    test('tapping while offline only repeats the reason', () async {
      final h = await makeState(reachable: false);
      h.announced.clear();
      await h.state.onAskPressed();
      expect(h.state.status, AppStatus.offline);
      expect(h.recorder.recording, isFalse);
      expect(h.announced, [h.state.strings.statusOffline]);
    });
  });

  group('spoken answers (B9)', () {
    test('the answer is read in the QUESTION language, not the app language', () async {
      final h = await makeState(saved: {'server_host': '192.168.0.105', 'language': 'en'});
      h.api.answerLanguage = 'ar';
      await h.state.onAskPressed();
      await h.state.onAskPressed();
      expect(h.speaker.spoken.last, ('A door with an exit sign.', 'ar'));
      expect(h.state.status, AppStatus.ready);
    });

    test('status sentences are spoken in the app language', () async {
      final h = await makeState(saved: {'server_host': '192.168.0.105', 'language': 'fr'});
      expect(h.speaker.spoken, [(h.state.strings.statusReady, 'fr')]);
    });

    test('a tap while the answer is read stops the voice, then back to ready', () async {
      final h = await makeState(speaker: FakeSpeaker(holdAnswers: true));
      await h.state.onAskPressed();
      final answering = h.state.onAskPressed(); // upload + start reading (held)
      await Future<void>.delayed(Duration.zero);
      expect(h.state.status, AppStatus.speaking);

      await h.state.onAskPressed(); // tap = stop reading
      await answering;
      expect(h.speaker.stops, greaterThanOrEqualTo(1));
      expect(h.state.status, AppStatus.ready);
    });

    test('nothing is spoken while recording; voice is silenced before recording', () async {
      final h = await makeState();
      final stopsBefore = h.speaker.stops;
      await h.state.onAskPressed(); // start recording
      final spokenBefore = h.speaker.spoken.length;
      h.streamer.status.value = CameraStatus.streaming; // would normally be announced
      expect(h.speaker.spoken.length, spokenBefore);
      expect(h.speaker.stops, stopsBefore + 1);
    });

    test('voices on the phone are reported', () async {
      final h = await makeState();
      expect(await h.state.voices(), {'en': true, 'fr': true, 'ar': false});
    });
  });

  group('camera (B3)', () {
    test('starts when the server is reachable, restarts on a new address', () async {
      final h = await makeState();
      await h.state.checkServer();
      expect(h.streamer.startedHosts, ['192.168.0.105']);

      await h.state.updateSettings(const Settings(serverHost: '10.0.0.5', language: 'en'));
      expect(h.streamer.startedHosts, ['192.168.0.105', '10.0.0.5']);
    });

    test('not started while the server is unreachable', () async {
      final h = await makeState(reachable: false);
      expect(h.streamer.startedHosts, isEmpty);
    });

    test('connected / disconnected is announced', () async {
      final h = await makeState(saved: {});
      h.streamer.status.value = CameraStatus.connecting;
      h.streamer.status.value = CameraStatus.streaming;
      h.streamer.status.value = CameraStatus.reconnecting;
      h.streamer.status.value = CameraStatus.reconnecting;
      expect(h.announced, [h.state.strings.cameraConnected, h.state.strings.cameraDisconnected]);
    });

    test('background stops camera and recording, coming back restarts the camera', () async {
      final h = await makeState();
      h.streamer.status.value = CameraStatus.streaming;
      await h.state.onAskPressed(); // recording

      await h.state.onAppPaused();
      expect(h.state.cameraStatus, CameraStatus.off);
      expect(h.recorder.recording, isFalse);
      expect(h.api.asked, isEmpty, reason: 'a question cut by the background is not sent');
      await h.state.checkServer(); // a late check must not restart it
      expect(h.streamer.startedHosts, ['192.168.0.105']);

      h.streamer.startedHosts.clear();
      h.state.onAppResumed();
      await Future<void>.delayed(Duration.zero);
      expect(h.streamer.startedHosts, ['192.168.0.105']);
      h.state.dispose(); // stops the health-check timer
    });
  });
}
