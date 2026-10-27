import 'package:flutter/material.dart';

import '../l10n/strings.dart';
import '../services/settings_service.dart';
import '../state/app_state.dart';

/// Server address and preferred language, saved on the phone.
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key, required this.state});

  final AppState state;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final TextEditingController _hostController;
  late String _language;
  String? _hostError;

  @override
  void initState() {
    super.initState();
    _hostController = TextEditingController(text: widget.state.settings.serverHost);
    _language = widget.state.settings.language;
  }

  @override
  void dispose() {
    _hostController.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final s = widget.state.strings;
    final host = SettingsService.normalizeHost(_hostController.text);
    if (host == null) {
      setState(() => _hostError = s.serverAddressInvalid);
      widget.state.onAnnounce?.call(s.serverAddressInvalid);
      return;
    }
    final navigator = Navigator.of(context);
    await widget.state.updateSettings(Settings(serverHost: host, language: _language));
    navigator.pop();
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.state.strings;
    return Scaffold(
      appBar: AppBar(title: Text(s.settings)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextField(
              controller: _hostController,
              keyboardType: TextInputType.url,
              autocorrect: false,
              style: const TextStyle(fontSize: 24),
              decoration: InputDecoration(
                labelText: s.serverAddress,
                hintText: s.serverAddressHint,
                errorText: _hostError, // TalkBack reads the error with the field
                border: const OutlineInputBorder(),
              ),
              onChanged: (_) {
                if (_hostError != null) setState(() => _hostError = null);
              },
            ),
            const SizedBox(height: 32),
            Semantics(
              header: true,
              child: Text(s.language, style: Theme.of(context).textTheme.titleLarge),
            ),
            const SizedBox(height: 8),
            // One big row per language. The word is written in its own language so
            // it can be found even when the app is set to a language you don't read.
            for (final entry in AppStrings.languages.entries)
              ListTile(
                minTileHeight: 64,
                selected: _language == entry.key, // TalkBack says "selected"
                leading: Icon(
                  _language == entry.key
                      ? Icons.radio_button_checked
                      : Icons.radio_button_unchecked,
                ),
                title: Text(entry.value, style: const TextStyle(fontSize: 24)),
                onTap: () => setState(() => _language = entry.key),
              ),
            const SizedBox(height: 32),
            SizedBox(
              height: 64,
              child: FilledButton(
                onPressed: _save,
                child: Text(s.save, style: const TextStyle(fontSize: 24)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
