import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';

/// Speaks text aloud. An interface so tests can use a fake.
abstract interface class Speaker {
  /// Speaks [text] in [language] ("en", "fr" or "ar"). Completes when the
  /// sentence is finished or [stop] was called. A new call interrupts the old one.
  Future<void> speak(String text, String language);

  Future<void> stop();

  /// Which of en/fr/ar have a voice installed on this phone.
  Future<Map<String, bool>> voices();
}

/// The phone's own text-to-speech engine through flutter_tts (task B9).
class PhoneSpeaker implements Speaker {
  /// Locales tried in order for each language; phones differ in what they offer.
  static const _locales = {
    'en': ['en-US', 'en-GB', 'en'],
    'fr': ['fr-FR', 'fr-CA', 'fr'],
    'ar': ['ar-SA', 'ar-EG', 'ar-XA', 'ar'],
  };

  /// flutter_tts scale: 0.5 = the phone's normal speed. Slightly slower helps
  /// understanding and suits the users this app is made for.
  static const speechRate = 0.45;

  final FlutterTts _tts = FlutterTts();
  final Map<String, String?> _chosenLocale = {}; // cache: "fr" -> "fr-FR" (or null)
  bool _configured = false;

  /// Google's engine has English, French AND Arabic voices; phone makers' own
  /// engines often lack Arabic (e.g. Samsung TTS on our test phone).
  static const _preferredEngine = 'com.google.android.tts';

  Future<void> _configure() async {
    if (_configured) return;
    try {
      final engines = List<String>.from(await _tts.getEngines as List? ?? const []);
      if (engines.contains(_preferredEngine)) {
        await _tts.setEngine(_preferredEngine);
      } else {
        debugPrint('[tts] Google TTS not installed, using the phone default engine $engines');
      }
    } catch (e) {
      debugPrint('[tts] could not choose the engine: $e');
    }
    await _tts.awaitSpeakCompletion(true); // speak() waits until the end
    await _tts.setSpeechRate(speechRate);
    await _tts.setVolume(1.0);
    await _tts.setPitch(1.0);
    _configured = true;
  }

  Future<String?> _locale(String language) async {
    if (_chosenLocale.containsKey(language)) return _chosenLocale[language];
    String? found;
    for (final locale in _locales[language] ?? const <String>[]) {
      if (await _tts.isLanguageAvailable(locale) == true) {
        found = locale;
        break;
      }
    }
    _chosenLocale[language] = found;
    return found;
  }

  @override
  Future<void> speak(String text, String language) async {
    try {
      await _configure();
      final locale = await _locale(language);
      if (locale == null) {
        debugPrint('[tts] no $language voice on this phone, using the default voice');
      } else {
        await _tts.setLanguage(locale);
      }
      await _tts.speak(text);
    } catch (e) {
      debugPrint('[tts] could not speak: $e'); // the answer is still shown on screen
    }
  }

  @override
  Future<void> stop() async {
    try {
      await _tts.stop();
    } catch (e) {
      debugPrint('[tts] could not stop: $e');
    }
  }

  @override
  Future<Map<String, bool>> voices() async {
    await _configure();
    return {for (final language in _locales.keys) language: await _locale(language) != null};
  }
}
