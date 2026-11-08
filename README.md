# Voice Assistant with Eyes

**An AI that describes the world out loud.** A phone streams live video to a server. The server remembers useful frames (with the text and objects in them), and the user asks questions by voice — "What's in front of me?", "What was written on the door I just passed?" — and hears a short, honest answer.

Final project for *Multimedia Database and Image Processing*, Université Antonine, Fall 2026/2027.

> This is a helper, not a replacement for a white cane or guide dog. It never says that something is "safe", and it says "I'm not sure" when the evidence is weak.

## How it works

1. **Stream** — the Flutter app sends the phone camera to MediaMTX over WebRTC (WHIP).
2. **Remember** — the ingest worker reads the stream, keeps sharp and new frames, reads text (OCR), detects objects, and stores everything with time and embeddings in PostgreSQL + pgvector.
3. **Ask** — the user taps and speaks; the audio goes to `POST /api/ask`, where speech is turned into text.
4. **Answer** — the most relevant frames are retrieved, a vision-language model writes a short answer, and the phone speaks it in the user's language (English, French or Arabic).

The web dashboard shows the live stream, system status, the timeline of stored frames, search, and past questions and answers.

## Repository layout

| Folder | What it holds |
| --- | --- |
| `backend/` | FastAPI API, ingest worker, image processing, database access, AI assistant |
| `dashboard/` | React + Vite + TypeScript web dashboard |
| `mobile/` | Flutter app (added in B0) |
| `infra/` | MediaMTX configuration (added in B1) |
| `docs/` | API contract, architecture, team responsibilities |
| `eval/` | Test scripts and results (speed, search quality, answer accuracy) |

## Run it locally

Requirements: Git, Python 3.11+, Node 20+, Docker Desktop.

```bash
# 1. Settings (once)
cp .env.example .env            # Windows: copy .env.example .env
#    then in .env: LAN_IP = the laptop's Wi-Fi IP (ipconfig), GEMINI_API_KEY = your key

# 2. Database + streaming server
docker compose up -d

# 3. Backend API  →  http://localhost:8000/docs
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 4. Dashboard  →  http://localhost:5173   (in a second terminal)
cd dashboard
npm install
npm run dev
```

On Windows, if `uvicorn` says *"Unable to create process"* (the folder was moved after the
virtual environment was made), start it as `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`.
The ingest worker runs in a third terminal: `python -m app.ingest.worker` (from `backend/`).

### The phone app (Android)

The app is in `mobile/` (Flutter). Install it once with the phone on USB
(Developer options → USB debugging):

```bash
cd mobile
flutter pub get
flutter run          # builds and installs "VA Eyes" on the phone
```

Then the cable is no longer needed. Phone and laptop must be on the **same Wi-Fi**.
In the app: ⚙ Settings → the laptop's IP (same as `LAN_IP`) and the preferred language → Save.
The app says *"Ready"* and *"Camera connected"*; tap the big yellow button, ask, tap again.
Spoken answers need the Google text-to-speech voices for English, French and Arabic
(Android Settings → General management → Text-to-speech; the app's Settings page shows
which voices are missing).

## Evaluation

Student A's part (remembering and finding what the camera saw) is measured in [`eval/`](eval/README.md). Every test frame goes through the real pipeline and is then searched with 44 questions in English, French and Arabic:

| | Result |
| --- | --- |
| Right frame first (Recall@1) | **0.84** (English 0.94, French 0.91, Arabic 0.60) |
| Right frame in the top 3 | 0.92 |
| Unanswerable question, yet "confident" | **0 of 7** (the assistant says "I'm not sure") |
| OCR on signs | 80% of words read; a sign at 8% light read perfectly thanks to enhancement |
| Stairs / closed-door warnings | 4/4 and 3/3 found, 0 false alarms |
| Time per stored frame / per search | ~2 s (mostly OCR) / 25 ms |

Full tables, method and known weaknesses: [eval/README.md](eval/README.md). Run it with `python ../eval/run_eval.py` from `backend/`.

### Student B's part: whole questions, answers and users (B13)

Measured on the **real system** (phone → laptop → Gemini), not on a test set: every question
asked with the phone is saved in the `qa_log` table with its answer and timings (B11).

| What | How | Script |
| --- | --- | --- |
| **Latency** | time of each stage of a spoken question: speech-to-text, memory search, vision-language model, total; **mean** and **P95** (95 % of questions were faster) | `python ../eval/latency.py --since <day>` |
| **Answer accuracy** | 30 questions in real scenes (10 English, 10 French, 10 Arabic), each answer scored by a person who saw the scene: *correct / partial / honest "not sure" / wrong*; also whether the question was heard right | `python ../eval/answer_eval.py export --since <day>`, score `eval/results/answers.csv`, then `… report` |
| **User feedback** | at least 3 consenting testers, consent + 7 statements rated 1–5 | [docs/feedback-form.md](docs/feedback-form.md) → `eval/results/feedback.csv` |

All three write CSV files, PNG charts and a short Markdown report to `eval/results/`
(`latency.md`, `answers.md`). The number to keep at zero is **wrong (confident)**: a false
fact said without "I'm not sure".

First latency numbers (22 full answers from development testing, Nov 4–7, laptop with
7.8 GB RAM running everything): mean **29 s** per question, of which speech-to-text 19 s,
Gemini 9 s, search 1 s. Speech-to-text was slowed down by the laptop running out of memory
(Whisper waiting for swapped memory); the final measurement is done after freeing memory.
The accuracy and feedback results are added after the tester sessions (week of Nov 23).

## Team

| Student | Role | Owns |
| --- | --- | --- |
| Student A | Vision Memory lead | Frame selection, image enhancement, OCR, object detection, multimedia database, search, dashboard Live / Timeline / Search |
| Student B | Voice and Streaming lead | Shared skeleton, mobile app, streaming, speech-to-text, vision-language answers, honesty rules, dashboard History / Status |

Details: [docs/team-responsibilities.md](docs/team-responsibilities.md) · API: [docs/api-contract.md](docs/api-contract.md)

## Ground rules

No face recognition (faces are only detected to blur them before storing). Old frames are deleted automatically. Testing only with people who agree.
