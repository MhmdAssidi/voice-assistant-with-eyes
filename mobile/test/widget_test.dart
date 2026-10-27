import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:va_mobile/main.dart';
import 'package:va_mobile/state/app_state.dart';

import 'app_state_test.dart' show FakeApi;

Future<AppState> pumpApp(WidgetTester tester, {String language = 'en'}) async {
  SharedPreferences.setMockInitialValues({'server_host': '192.168.0.105', 'language': language});
  final state = AppState(api: FakeApi(), fakeAnswerDelay: Duration.zero);
  await state.loadSettings();
  await state.checkServer();
  await tester.pumpWidget(VaApp(state: state));
  return state;
}

void main() {
  testWidgets('home screen shows status, ask button and last answer', (tester) async {
    await pumpApp(tester);

    expect(find.text('Ready. Tap the big button to ask.'), findsOneWidget);
    expect(find.text('Ask a question'), findsOneWidget);
    expect(find.text('No answer yet.'), findsOneWidget);
  });

  testWidgets('every control has a screen reader label', (tester) async {
    final handle = tester.ensureSemantics();
    await pumpApp(tester);

    expect(
      tester.getSemantics(find.byType(FilledButton)),
      isSemantics(
        label: 'Ask a question',
        hint: 'Tap to start speaking, tap again to send.',
        isButton: true,
      ),
    );
    expect(find.bySemanticsLabel('Settings'), findsOneWidget);
    expect(find.bySemanticsLabel('Last answer'), findsOneWidget);
    handle.dispose();
  });

  testWidgets('big button meets the 48 dp minimum touch target', (tester) async {
    await pumpApp(tester);
    final size = tester.getSize(find.byType(FilledButton));
    expect(size.height, greaterThanOrEqualTo(48));
    expect(size.width, greaterThanOrEqualTo(48));
    await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
  });

  testWidgets('tapping the button switches to listening', (tester) async {
    await pumpApp(tester);
    await tester.tap(find.byType(FilledButton));
    await tester.pump();
    expect(find.text('Stop and send'), findsOneWidget);
  });

  testWidgets('Arabic uses right-to-left layout', (tester) async {
    await pumpApp(tester, language: 'ar');
    expect(find.text('اطرح سؤالاً'), findsOneWidget);
    final direction = Directionality.of(tester.element(find.byType(FilledButton)));
    expect(direction, TextDirection.rtl);
  });
}
