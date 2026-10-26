import 'package:flutter/material.dart';

import 'screens/home_screen.dart';

void main() {
  runApp(const VaApp());
}

/// Root widget of the "Voice Assistant with Eyes" phone app.
///
/// High-contrast dark theme with large text: the app is built for blind and
/// visually impaired users who rely on TalkBack or on very large type.
class VaApp extends StatelessWidget {
  const VaApp({super.key});

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
      home: const HomeScreen(),
    );
  }
}
