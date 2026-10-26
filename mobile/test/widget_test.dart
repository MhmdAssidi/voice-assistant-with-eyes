import 'package:flutter_test/flutter_test.dart';

import 'package:va_mobile/main.dart';

void main() {
  testWidgets('App starts and shows the home screen', (WidgetTester tester) async {
    await tester.pumpWidget(const VaApp());

    expect(find.text('VA Eyes'), findsOneWidget);
    expect(find.text('Setup OK'), findsOneWidget);
  });
}
