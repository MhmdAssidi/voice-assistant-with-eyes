// Accessibility checks (task B10), run by CI on every pull request.
//
// Android's accessibility guidelines are tested automatically on every screen and every
// state of the big button: touch targets >= 48 dp, every control has a label, text
// contrast >= 4.5:1, and nothing overflows when the phone's text size is 200 %.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:va_mobile/main.dart';
import 'package:va_mobile/state/app_state.dart';

import 'app_state_test.dart' show FakeApi, FakeRecorder, FakeSpeaker, FakeStreamer;

/// A small phone screen (360 x 690 dp) so 200 % text is a real test.
void useSmallPhone(WidgetTester tester, {double textScale = 1.0}) {
  tester.view.physicalSize = const Size(1080, 2070);
  tester.view.devicePixelRatio = 3.0;
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
}

Future<AppState> pumpApp(
  WidgetTester tester, {
  String language = 'en',
  bool reachable = true,
  FakeSpeaker? speaker,
}) async {
  SharedPreferences.setMockInitialValues({'server_host': '192.168.0.105', 'language': language});
  final state = AppState(
    api: FakeApi(reachable: reachable),
    streamer: FakeStreamer(),
    recorder: FakeRecorder(),
    speaker: speaker ?? FakeSpeaker(),
  );
  await state.loadSettings();
  await state.checkServer();
  await tester.pumpWidget(VaApp(state: state));
  await tester.pumpAndSettle();
  return state;
}

/// Puts the app in each state the user can meet, then runs [check] in it.
Future<void> forEachState(
  WidgetTester tester,
  Future<void> Function(String name) check, {
  String language = 'en',
}) async {
  await pumpApp(tester, language: language, reachable: false);
  await check('offline');

  final speaker = FakeSpeaker(holdAnswers: true);
  final state = await pumpApp(tester, language: language, speaker: speaker);
  await check('ready');

  await tester.tap(find.byType(FilledButton));
  await tester.pump();
  await check('listening');

  await tester.tap(find.byType(FilledButton)); // send -> answer read aloud (held)
  await tester.pump();
  await tester.pump();
  expect(state.status, AppStatus.speaking);
  await check('speaking');

  await tester.tap(find.byType(FilledButton)); // stop reading
  await tester.pumpAndSettle();
  state.dispose();
}

Future<void> openSettings(WidgetTester tester, AppState state) async {
  await tester.tap(find.bySemanticsLabel(state.strings.settings)); // in the app's language
  await tester.pumpAndSettle();
}

void main() {
  group('main screen', () {
    testWidgets('touch targets >= 48 dp and every control labelled, in every state',
        (tester) async {
      final handle = tester.ensureSemantics();
      useSmallPhone(tester);
      await forEachState(tester, (name) async {
        await expectLater(tester, meetsGuideline(androidTapTargetGuideline), reason: name);
        await expectLater(tester, meetsGuideline(labeledTapTargetGuideline), reason: name);
      });
      handle.dispose();
    });

    testWidgets('text contrast >= 4.5:1 in every state', (tester) async {
      final handle = tester.ensureSemantics();
      useSmallPhone(tester);
      await forEachState(tester, (name) async {
        await expectLater(tester, meetsGuideline(textContrastGuideline), reason: name);
      });
      handle.dispose();
    });

    for (final language in ['en', 'fr', 'ar']) {
      testWidgets('nothing overflows at 200 % text size ($language)', (tester) async {
        useSmallPhone(tester, textScale: 2.0);
        await forEachState(tester, (name) async {
          // A RenderFlex overflow is reported as an exception during layout.
          expect(tester.takeException(), isNull, reason: '$language, $name');
          expect(find.byType(FilledButton), findsOneWidget);
        }, language: language);
      });
    }

    testWidgets('the big button fills most of the screen (one-handed use)', (tester) async {
      useSmallPhone(tester);
      await pumpApp(tester);
      final button = tester.getSize(find.byType(FilledButton));
      final screen = tester.getSize(find.byType(Scaffold));
      expect(button.width, greaterThan(screen.width * 0.85));
      expect(button.height, greaterThan(screen.height * 0.3));
    });

    testWidgets('each state differs by its words and icon, not only by colour', (tester) async {
      useSmallPhone(tester);
      final looks = <String>{};
      await forEachState(tester, (name) async {
        final inButton = find.descendant(
            of: find.byType(FilledButton), matching: find.byType(Text));
        final icon = find.descendant(of: find.byType(FilledButton), matching: find.byType(Icon));
        looks.add('${tester.widget<Text>(inButton.first).data} '
            '${tester.widget<Icon>(icon.first).icon?.codePoint}');
      });
      // offline, ready, listening and speaking: 4 different text+icon combinations
      expect(looks, hasLength(4));
    });
  });

  group('settings screen', () {
    testWidgets('touch targets, labels and contrast', (tester) async {
      final handle = tester.ensureSemantics();
      useSmallPhone(tester);
      final state = await pumpApp(tester);
      await openSettings(tester, state);
      await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      await expectLater(tester, meetsGuideline(textContrastGuideline));
      handle.dispose();
    });

    for (final language in ['en', 'fr', 'ar']) {
      testWidgets('nothing overflows at 200 % text size ($language)', (tester) async {
        useSmallPhone(tester, textScale: 2.0);
        final state = await pumpApp(tester, language: language);
        await openSettings(tester, state);
        expect(tester.takeException(), isNull);
        // Everything is reachable by scrolling, down to the Save button.
        // (The main screen stays alive behind the settings page: look in the top one.)
        final save = find.widgetWithText(FilledButton, state.strings.save);
        final page = find.descendant(of: find.byType(ListView), matching: find.byType(Scrollable));
        await tester.scrollUntilVisible(save, 200, scrollable: page.first);
        await tester.ensureVisible(save); // fully on screen, not just its edge
        await tester.pumpAndSettle();
        expect(save.hitTestable(), findsOneWidget);
        expect(tester.getSize(save).height, greaterThanOrEqualTo(48));
        expect(tester.takeException(), isNull);
      });
    }
  });
}
