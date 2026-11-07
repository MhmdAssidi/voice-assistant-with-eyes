# Accessibility of the VA Eyes app (Student B, task B10)

The app is used by blind and visually impaired people. It is built so that **one big
button and the app's own voice** are enough: no reading, no precise tapping, no setup
by the user (a helper types the server address once).

Test phone: Samsung Galaxy A31, Android 12. Automated checks run in CI on every pull
request (`mobile/test/accessibility_test.dart`, `app_state_test.dart`, `widget_test.dart`).

## Checklist

| # | Requirement | How it is met | How it is checked | Result |
|---|---|---|---|---|
| 1 | **Touch targets ≥ 48 dp** | Ask button fills most of the screen; settings rows 64 dp, Save 64 dp, gear icon 48 dp | Android tap-target guideline, every screen and every button state | ✅ automated |
| 2 | **Every control has a label** | Ask button: label + hint "Tap to start speaking, tap again to send"; gear: "Settings"; language rows; headers marked as headings | Android labelled-tap-target guideline, every screen and state | ✅ automated |
| 3 | **Text contrast ≥ 4.5:1** | High-contrast dark theme, see table below (lowest 5.6:1) | Android text-contrast guideline + WCAG calculation | ✅ automated |
| 4 | **Text scaling to 200 %** | Flexible layout; status line and answer box scroll; settings page scrolls to Save | 200 % text on a small 360×690 dp screen, en/fr/ar, all states: no overflow, Save reachable | ✅ automated · ✅ phone check |
| 5 | **Spoken feedback, also on connection loss** | The app speaks with its own voice (works without TalkBack): ready, server not reachable / back, camera connected / disconnected, thinking, the answer (in the question's language), errors (no microphone permission, nothing heard, server too slow) | `app_state_test.dart` (connection lost announced once, answer spoken in the question's language, nothing spoken while recording) | ✅ automated |
| 6 | **No information by colour only** | Each button state has its own words and icon: "Ask a question" 🎤 / 🎤̸ (not available), "Stop and send" ⏹, "Thinking…" ⏳, "Stop reading" 🔇; camera line has words + icon; History badges "✓ confident / ? not sure" | Test: 4 states → 4 different text+icon pairs | ✅ automated |
| 7 | **One-handed use** | Whole flow = tap the big button with a thumb (≥ 85 % of the width, ≥ 30 % of the height); start/stop beeps + vibration replace looking at the screen | Size test + phone check | ✅ automated · ✅ phone check |
| 8 | **Arabic right-to-left** | Arabic UI mirrors; an Arabic answer is shown right-to-left even in an English app | `widget_test.dart` (RTL) + phone check | ✅ automated · ✅ phone check |
| 9 | **No voice over the user** | Status speech is muted while recording (it would be recorded) and while an answer is read; the voice is silenced before recording starts | `app_state_test.dart` | ✅ automated |
| 10 | **Honest answers** | "I'm not sure" when evidence is weak, never "safe", at most 2 sentences (backend B8); covered lens → "I can't see anything clearly right now" | `backend/tests/assistant/test_uncertainty.py`, `test_answer.py` | ✅ automated |

TalkBack (Android's screen reader) is supported through the labels above, but the app does
not depend on it: everything important is spoken by the app itself.

## Colour contrast (WCAG 2.1, minimum 4.5:1 for normal text)

| Element | Text | Background | Ratio |
|---|---|---|---|
| Ask button (ready) | black | yellow `#FFD600` | **14.9:1** |
| Stop and send (listening) | white | red `#C62828` | **5.6:1** |
| Thinking / not available | white | grey `#424242` | **10.0:1** |
| Stop reading (speaking) | white | blue `#1565C0` | **5.7:1** |
| Status line, camera line, answer | white | black | **21.0:1** |
| "Last answer" title | white 70 % `#B3B3B3` | black | **10.0:1** |

## Manual check on the phone (≈ 10 minutes)

1. **200 % text:** Settings → Display → Font size and style → largest font size (and
   "Screen zoom" largest). Open VA Eyes: status, button text and answer are fully readable;
   Settings scrolls down to Save.
2. **One hand:** hold the phone in one hand, ask a question with the thumb only.
3. **Arabic:** Settings → العربية → Save: the screen mirrors (gear on the left), texts in Arabic.
