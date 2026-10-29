# Test recordings for speech-to-text (B6)

Three short questions recorded with the VA Eyes app (m4a, 16 kHz mono), one per language:

| File | Say |
|---|---|
| `en.m4a` | "What is in front of me?" |
| `fr.m4a` | "Qu'est-ce qu'il y a devant moi ?" |
| `ar.m4a` | "ماذا يوجد أمامي؟" |

Run the real-model tests from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -m slow tests/assistant/test_stt.py -s
```

Only consenting team members' voices are stored here.
