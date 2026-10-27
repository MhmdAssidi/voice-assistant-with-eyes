import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';

import '../l10n/strings.dart';
import '../state/app_state.dart';
import 'settings_screen.dart';

/// Main screen, built for TalkBack and very large text:
///   1. status line (what the app is doing, also announced aloud)
///   2. one huge "Ask" button: tap to start, tap again to send
///   3. the last answer in large text
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.state});

  final AppState state;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  @override
  void initState() {
    super.initState();
    widget.state.onAnnounce = _announce;
  }

  @override
  void dispose() {
    widget.state.onAnnounce = null;
    super.dispose();
  }

  /// Makes TalkBack speak [message] even if the user's focus is elsewhere.
  void _announce(String message) {
    if (!mounted) return;
    SemanticsService.sendAnnouncement(
      View.of(context),
      message,
      AppStrings.directionOf(widget.state.settings.language),
    );
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.state,
      builder: (context, _) {
        final state = widget.state;
        final s = state.strings;
        return Scaffold(
          appBar: AppBar(
            title: Text(s.appTitle),
            actions: [
              IconButton(
                // semanticLabel is what TalkBack reads: "Settings, button"
                icon: Icon(Icons.settings, semanticLabel: s.settings),
                iconSize: 32,
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(builder: (_) => SettingsScreen(state: state)),
                ),
              ),
            ],
          ),
          body: SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Flexible(flex: 2, child: _StatusLine(text: state.statusText)),
                  const SizedBox(height: 16),
                  Expanded(flex: 5, child: _AskButton(state: state)),
                  const SizedBox(height: 16),
                  Expanded(
                    flex: 3,
                    child: _LastAnswer(
                      title: s.lastAnswer,
                      answer: state.lastAnswer ?? s.noAnswerYet,
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _StatusLine extends StatelessWidget {
  const _StatusLine({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    // Scrolls instead of overflowing when the user's text size is 200%.
    return SingleChildScrollView(
      child: Text(
        text,
        style: Theme.of(context).textTheme.headlineSmall?.copyWith(
              color: Colors.white,
              fontWeight: FontWeight.bold,
            ),
      ),
    );
  }
}

class _AskButton extends StatelessWidget {
  const _AskButton({required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final s = state.strings;
    // Each state differs by text AND icon, not only by colour.
    // Colour pairs all have a contrast ratio above 4.5:1.
    final (String label, IconData icon, Color background, Color foreground) =
        switch (state.status) {
      AppStatus.listening => (s.stopButton, Icons.stop_circle, const Color(0xFFC62828), Colors.white),
      AppStatus.thinking => (s.statusThinking, Icons.hourglass_top, const Color(0xFF424242), Colors.white),
      AppStatus.ready || AppStatus.error => (s.askButton, Icons.mic, const Color(0xFFFFD600), Colors.black),
      _ => (s.askButton, Icons.mic_off, const Color(0xFF424242), Colors.white),
    };

    return FilledButton(
      onPressed: state.onAskPressed,
      style: FilledButton.styleFrom(
        backgroundColor: background,
        foregroundColor: foreground,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        padding: const EdgeInsets.all(16),
      ),
      child: Semantics(
        hint: s.askHint,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 96),
            const SizedBox(height: 12),
            Flexible(
              child: Text(
                label,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 32, fontWeight: FontWeight.bold),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LastAnswer extends StatelessWidget {
  const _LastAnswer({required this.title, required this.answer});

  final String title;
  final String answer;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        border: Border.all(color: Colors.white70, width: 2),
        borderRadius: BorderRadius.circular(16),
      ),
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Semantics(
              header: true,
              child: Text(title, style: const TextStyle(fontSize: 20, color: Colors.white70)),
            ),
            const SizedBox(height: 8),
            Text(answer, style: const TextStyle(fontSize: 28, color: Colors.white)),
          ],
        ),
      ),
    );
  }
}
