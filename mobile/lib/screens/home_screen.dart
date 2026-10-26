import 'package:flutter/material.dart';

/// Placeholder main screen (B0).
///
/// B2 replaces this with the full-screen "Ask" button, the status line
/// announced to screen readers and the last answer in large text.
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('VA Eyes')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Semantics(
            liveRegion: true,
            child: Text(
              'Setup OK',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.displaySmall,
            ),
          ),
        ),
      ),
    );
  }
}
