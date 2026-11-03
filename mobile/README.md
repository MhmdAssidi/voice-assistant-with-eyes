# VA Eyes — mobile app (Student B)

Accessible Android app for "Voice Assistant with Eyes": streams the back camera to MediaMTX
(WebRTC/WHIP), records spoken questions, sends them to `POST /api/ask` and speaks the answer.

Android only (Flutter cannot build iOS apps on Windows).

## Run on a phone

1. Enable Developer options and USB debugging on the phone, plug it in, accept the prompt.
2. From this folder:

   ```powershell
   flutter pub get
   flutter devices      # the phone must be listed
   flutter run
   ```

## Checks (same as CI)

```powershell
flutter analyze
flutter test
```

## Voices for spoken answers (English, French, Arabic)

Answers are read aloud with the phone's own text-to-speech engine, in the **language of the
question** (en-US, fr-FR, ar-SA). **Settings → Voices on this phone** shows ✓/✗ for each.

The app uses **Speech Services by Google** automatically when it is installed: phone makers'
own engines often have no Arabic (Samsung TTS on our test phone had none).

If a voice is still missing (Samsung, Android 12):

1. Make sure **Speech Services by Google** is installed (Play Store).
2. Settings → **General management** → **Text-to-speech output**
   (other phones: Settings → Accessibility → Text-to-speech).
3. Tap ⚙️ next to **Speech Services by Google** → **Install voice data** → download
   **English (United States)**, **Français (France)** and **العربية**.
4. Reopen VA Eyes → Settings: all three show ✓.

A missing voice does not break the app: the answer is still shown on screen and read with the
default voice.

## Layout

- `lib/screens/` — UI screens (main screen, settings)
- `lib/services/` — camera stream, audio recording, API client, TTS, events WebSocket
- `lib/state/` — app state (`ChangeNotifier`)

Permissions are declared in `android/app/src/main/AndroidManifest.xml`. Plain HTTP to the laptop
server is allowed by `android/app/src/main/res/xml/network_security_config.xml`.
