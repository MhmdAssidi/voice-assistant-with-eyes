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

## Layout

- `lib/screens/` — UI screens (main screen, settings)
- `lib/services/` — camera stream, audio recording, API client, TTS, events WebSocket
- `lib/state/` — app state (`ChangeNotifier`)

Permissions are declared in `android/app/src/main/AndroidManifest.xml`. Plain HTTP to the laptop
server is allowed by `android/app/src/main/res/xml/network_security_config.xml`.
