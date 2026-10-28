import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';

import '../l10n/strings.dart';
import '../services/stream_service.dart';
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
  late final AppLifecycleListener _lifecycle;

  @override
  void initState() {
    super.initState();
    widget.state.onAnnounce = _announce;
    // Stop the camera when the app goes to the background, restart on return.
    _lifecycle = AppLifecycleListener(
      onPause: widget.state.onAppPaused,
      onResume: widget.state.onAppResumed,
    );
  }

  @override
  void dispose() {
    _lifecycle.dispose();
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
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: _CameraLine(
                          text: state.cameraText,
                          streaming: state.cameraStatus == CameraStatus.streaming,
                        ),
                      ),
                      const SizedBox(width: 8),
                      _CameraPreview(stream: state.streamer.localStream),
                    ],
                  ),
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

/// "Camera connected" with an icon; the words carry the meaning, not the colour.
class _CameraLine extends StatelessWidget {
  const _CameraLine({required this.text, required this.streaming});

  final String text;
  final bool streaming;

  @override
  Widget build(BuildContext context) {
    return MergeSemantics(
      child: Row(
        children: [
          Icon(streaming ? Icons.videocam : Icons.videocam_off, color: Colors.white, size: 28),
          const SizedBox(width: 8),
          Expanded(
            child: Text(text, style: const TextStyle(fontSize: 20, color: Colors.white)),
          ),
        ],
      ),
    );
  }
}

/// Small live view of what is being sent, for sighted helpers and the demo.
/// Hidden from TalkBack: the camera line above already says the same thing.
class _CameraPreview extends StatefulWidget {
  const _CameraPreview({required this.stream});

  final MediaStream? stream;

  @override
  State<_CameraPreview> createState() => _CameraPreviewState();
}

class _CameraPreviewState extends State<_CameraPreview> {
  RTCVideoRenderer? _renderer;

  @override
  void initState() {
    super.initState();
    _attach();
  }

  @override
  void didUpdateWidget(_CameraPreview oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.stream != widget.stream) _attach();
  }

  /// Connects the renderer to the camera. Created only once a camera exists.
  Future<void> _attach() async {
    final stream = widget.stream;
    if (stream == null) {
      _renderer?.srcObject = null;
      return;
    }
    if (_renderer == null) {
      final renderer = RTCVideoRenderer();
      await renderer.initialize();
      if (!mounted) {
        await renderer.dispose();
        return;
      }
      _renderer = renderer;
    }
    _renderer!.srcObject = stream;
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _renderer?.srcObject = null;
    _renderer?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final renderer = _renderer;
    return ExcludeSemantics(
      child: SizedBox(
        width: 96,
        height: 72,
        child: DecoratedBox(
          decoration: BoxDecoration(border: Border.all(color: Colors.white70)),
          child: renderer == null || widget.stream == null
              ? const ColoredBox(color: Color(0xFF212121))
              : RTCVideoView(renderer, objectFit: RTCVideoViewObjectFit.RTCVideoViewObjectFitCover),
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
