# Demo checklist (Student B, polish)

One laptop runs everything (Docker, backend, worker, dashboard); the phone only needs the
VA Eyes app and the same Wi-Fi.

## The day before
- [ ] Phone charged; VA Eyes installed (no USB cable needed afterwards).
- [ ] Laptop charged, charger packed. Windows updates done (no surprise restart).
- [ ] Oracle / MySQL set to **Manual** start (admin PowerShell, once):
      `'OracleServiceXE','OracleOraDB21Home1TNSListener','OracleOraDB21Home1MTSRecoveryService','MySQL80','mysql' | ForEach-Object { Set-Service -Name $_ -StartupType Manual }`
- [ ] `.env` has a working `GEMINI_API_KEY`; a test question gets an answer.
- [ ] Backup video of a working run saved on the laptop **and** a USB stick.

## In the room, 15 minutes before
1. **Close VS Code, Adobe, extra browser tabs** - the laptop has 7.8 GB and the AI models need about 5 GB.
2. Laptop and phone on the **same Wi-Fi** (or the phone's hotspot, laptop connected to it).
   Venue Wi-Fi often blocks phone-to-laptop traffic; the hotspot always works.
3. Double-click **`infra\start-demo.cmd`**. It frees memory, updates `LAN_IP` if the Wi-Fi address
   changed, starts Docker, opens the 3 windows (backend, worker at low priority, dashboard) and prints
   the IP for the phone.
4. Phone: VA Eyes -> Settings -> the printed IP -> Save. Wait for **"Ready"** and **"Camera connected"**.
5. Ask one test question. Dashboard: Live shows the video, History shows the answer.

## Demo flow (about 5 minutes)
1. **Live:** point the phone at the room, show the dashboard Live page and the status bar.
2. **"What is in front of me?"** - spoken answer + History entry with the evidence photo.
3. **A sign:** "What does the sign say?" (OCR, translation into the question's language).
4. **Memory:** look at something, turn away, ask **"What was in front of me before?"**
5. **Another language:** the same question in French or Arabic -> answer in that language.
6. **Honesty:** cover the camera -> *"I'm not sure. I can't see anything clearly right now."*
7. *(Bonus)* point at stairs or a closed door -> spoken warning with a double vibration.

## If something goes wrong
| Symptom | Fix |
|---|---|
| Phone: "Server not reachable" | Same Wi-Fi? IP in the app = IP printed by the start script? |
| Phone: "Camera disconnected" | Wait 10 s (it reconnects); reopen the app; check `LAN_IP` in `.env` and rerun the start script |
| Answer: "I can't analyse the images right now" | Gemini overloaded or no internet: wait 30 s and ask again; check the laptop's internet |
| Question fails / "failed to allocate memory" in the backend window | Close more apps; rerun the start script (it stops Oracle/MySQL and build helpers) |
| Answers take more than 30 s | Worker must run at low priority: start it with the script, not by hand |
| Nothing works | Play the backup video and explain the architecture with the slides |

Stop everything afterwards with **`infra\stop-demo.cmd`** (data is kept).
