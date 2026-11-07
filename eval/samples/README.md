# Recording a test walk

The best test of the system is a real walk through the university, recorded with the phone and replayed through the evaluation (`../run_eval.py --video`).

## Record
- **Consent first:** film only people who agreed. Faces are blurred before anything is stored (A9), but the video file itself is not.
- Hold the phone at chest height, pointing forward, and walk slowly for **2–3 minutes**.
- Pass several **signs** (French, English and Arabic if possible), at least one **staircase**, a **closed door**, a corridor, and a room with furniture.
- Save it as `walk.mp4` in this folder: H.264, 640×480, 15 fps, no sound. The phone's normal camera video is fine. If needed, convert with
  `ffmpeg -i input.mp4 -vf scale=640:480 -r 15 -an -c:v libx264 -g 15 walk.mp4`
- Videos are **not committed** (see `.gitignore`): they are large and may show people.

## Label
Watch the video and, for each question, write **from which second to which second** the answer is visible. Copy `walk_queries.example.csv` to `walk_queries.csv` and edit it:

```csv
query,language,from_s,to_s
What did the exit sign say?,en,12,18
Où est l'escalier ?,fr,40,52
a plate of spaghetti,en,,
```
Leave `from_s` and `to_s` empty for a question whose answer was **never** seen. These check that the assistant says *"I'm not sure"*.

Aim for about 30 questions, about 10 per language.
