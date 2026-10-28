import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:record/record.dart';

/// A finished recording, ready to upload.
class RecordedAudio {
  const RecordedAudio({required this.path, required this.duration});

  final String path;
  final Duration duration;
}

/// Records the user's spoken question. An interface so tests can use a fake.
abstract interface class QuestionRecorder {
  /// Asks for the microphone permission the first time.
  Future<bool> hasPermission();

  /// Beep + vibration, then starts recording.
  Future<void> start();

  /// Stops recording, then beep + vibration. Null if nothing was recorded.
  Future<RecordedAudio?> stop();
}

/// Records AAC-LC .m4a at 16 kHz mono (task B5): Whisper works at 16 kHz,
/// and a 10-second question is only about 40 KB to upload.
class MicRecorder implements QuestionRecorder {
  static const _cues = MethodChannel('edu.ua.vaeyes/cues');

  /// Pause after the start beep so the beep itself is not recorded.
  static const _beepGap = Duration(milliseconds: 250);

  final AudioRecorder _recorder = AudioRecorder();
  final Stopwatch _clock = Stopwatch();

  /// One file, overwritten for each question. On Android the system temp
  /// folder is the app's private cache folder.
  String get _path => '${Directory.systemTemp.path}/question.m4a';

  @override
  Future<bool> hasPermission() => _recorder.hasPermission();

  @override
  Future<void> start() async {
    await _feedback('start');
    await Future<void>.delayed(_beepGap);
    await _recorder.start(
      const RecordConfig(
        encoder: AudioEncoder.aacLc,
        sampleRate: 16000,
        numChannels: 1,
        bitRate: 32000,
      ),
      path: _path,
    );
    _clock
      ..reset()
      ..start();
  }

  @override
  Future<RecordedAudio?> stop() async {
    final path = await _recorder.stop();
    _clock.stop();
    await _feedback('stop');
    if (path == null) return null;
    return RecordedAudio(path: path, duration: _clock.elapsed);
  }

  /// Vibration and a short tone (one beep = start, two beeps = stop), so the
  /// user knows what happened without looking at the screen.
  static Future<void> _feedback(String kind) async {
    await HapticFeedback.heavyImpact();
    try {
      await _cues.invokeMethod<void>('beep', {'kind': kind});
    } catch (e) {
      debugPrint('[audio] no beep: $e'); // vibration still happened
    }
  }
}
