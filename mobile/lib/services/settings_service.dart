import 'package:shared_preferences/shared_preferences.dart';

/// The user's settings, saved on the phone so they survive app restarts.
class Settings {
  const Settings({required this.serverHost, required this.language});

  /// Laptop address on the Wi-Fi, e.g. "192.168.0.105". Empty = not set yet.
  final String serverHost;

  /// Preferred language: "en", "fr" or "ar".
  final String language;

  bool get hasServer => serverHost.isNotEmpty;
}

/// Loads and saves [Settings] with shared_preferences.
class SettingsService {
  static const _hostKey = 'server_host';
  static const _languageKey = 'language';

  Future<Settings> load() async {
    final prefs = await SharedPreferences.getInstance();
    return Settings(
      serverHost: prefs.getString(_hostKey) ?? '',
      language: prefs.getString(_languageKey) ?? 'en',
    );
  }

  Future<void> save(Settings settings) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_hostKey, settings.serverHost);
    await prefs.setString(_languageKey, settings.language);
  }

  /// Cleans what the user typed ("http://192.168.0.105:8000/" -> "192.168.0.105").
  /// Returns null if it does not look like an IP address or host name.
  static String? normalizeHost(String input) {
    var host = input.trim();
    host = host.replaceFirst(RegExp(r'^[a-zA-Z]+://'), '');
    host = host.split('/').first.split(':').first;
    final valid = RegExp(r'^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$');
    return valid.hasMatch(host) ? host : null;
  }
}
