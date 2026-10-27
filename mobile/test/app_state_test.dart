import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:va_mobile/services/api_client.dart';
import 'package:va_mobile/services/settings_service.dart';
import 'package:va_mobile/state/app_state.dart';

/// Pretends to be the server so tests need no network.
class FakeApi extends ApiClient {
  FakeApi({this.reachable = true});

  bool reachable;

  @override
  Future<bool> isServerReachable(String host) async => reachable;
}

Future<(AppState, List<String>)> makeState({
  Map<String, Object> saved = const {},
  bool reachable = true,
}) async {
  SharedPreferences.setMockInitialValues(saved);
  final state = AppState(api: FakeApi(reachable: reachable), fakeAnswerDelay: Duration.zero);
  final announced = <String>[];
  state.onAnnounce = announced.add;
  await state.loadSettings();
  return (state, announced);
}

void main() {
  test('no saved server -> asks the user to set it', () async {
    final (state, _) = await makeState();
    await state.checkServer();
    expect(state.status, AppStatus.noServer);
  });

  test('server reachable -> ready, and it is announced', () async {
    final (state, announced) = await makeState(saved: {'server_host': '192.168.0.105'});
    await state.checkServer();
    expect(state.status, AppStatus.ready);
    expect(announced, [state.strings.statusReady]);
  });

  test('connection lost is announced once', () async {
    final api = FakeApi();
    SharedPreferences.setMockInitialValues({'server_host': '192.168.0.105'});
    final state = AppState(api: api);
    final announced = <String>[];
    state.onAnnounce = announced.add;
    await state.loadSettings();
    await state.checkServer();

    api.reachable = false;
    await state.checkServer();
    await state.checkServer(); // still offline: no second announcement
    expect(state.status, AppStatus.offline);
    expect(announced.where((m) => m == state.strings.statusOffline).length, 1);
  });

  test('tap, tap -> listening, thinking, answer', () async {
    final (state, announced) = await makeState(saved: {'server_host': '192.168.0.105'});
    await state.checkServer();

    await state.onAskPressed();
    expect(state.status, AppStatus.listening);

    await state.onAskPressed();
    expect(state.status, AppStatus.ready);
    expect(state.lastAnswer, isNotNull);
    expect(announced.last, state.lastAnswer);
    expect(announced, contains(state.strings.statusThinking));
  });

  test('tapping while offline only repeats the reason', () async {
    final (state, announced) =
        await makeState(saved: {'server_host': '192.168.0.105'}, reachable: false);
    await state.checkServer();
    announced.clear();

    await state.onAskPressed();
    expect(state.status, AppStatus.offline);
    expect(announced, [state.strings.statusOffline]);
  });

  test('settings are saved and the language changes the texts', () async {
    final (state, _) = await makeState();
    await state.updateSettings(const Settings(serverHost: '10.0.0.5', language: 'fr'));

    expect(state.status, AppStatus.ready);
    expect(state.strings.askButton, 'Poser une question');
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
}
