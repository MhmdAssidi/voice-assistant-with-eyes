import 'package:flutter/material.dart';

import 'l10n/strings.dart';
import 'screens/home_screen.dart';
import 'state/app_state.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final state = AppState();
  // Load the saved server address and language before the first frame,
  // so the screen does not flash in the wrong language.
  await state.loadSettings();
  state.startMonitoring();
  runApp(VaApp(state: state));
}

/// Root widget of the "Voice Assistant with Eyes" phone app.
///
/// High-contrast dark theme with large text: the app is built for blind and
/// visually impaired users who rely on TalkBack or on very large type.
class VaApp extends StatelessWidget {
  const VaApp({super.key, required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'VA Eyes',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.yellow,
          brightness: Brightness.dark,
        ),
        scaffoldBackgroundColor: Colors.black,
        useMaterial3: true,
      ),
      // Right-to-left layout when the app language is Arabic.
      builder: (context, child) => ListenableBuilder(
        listenable: state,
        builder: (context, _) => Directionality(
          textDirection: AppStrings.directionOf(state.settings.language),
          child: child!,
        ),
      ),
      home: HomeScreen(state: state),
    );
  }
}
