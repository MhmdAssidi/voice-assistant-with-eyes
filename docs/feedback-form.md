# Tester consent and feedback form (Student B, task B13)

Print one copy per tester (or fill it in on a phone). A tester is a volunteer who tries
the app for about 15 minutes. **At least 3 consenting testers** are needed.

Results are typed into `eval/results/feedback.csv` (template: `eval/feedback.example.csv`)
and summarised by `python ../eval/answer_eval.py report` (run from `backend/`).

---

## Part 1: Consent (read with the tester, before anything is recorded)

**Project:** *An AI That Describes the World Out Loud*, a student project at Université
Antonine (Database and Image Processing course), by Student A and Student B.

**What you will do:** hold a phone (the camera looks forward) and ask the app spoken
questions such as "What is in front of me?" or "What does the sign say?". The app answers
out loud. You may close your eyes or wear a blindfold, **only while seated or standing
still, indoors, with a team member next to you**. You never walk near stairs or traffic
without help: the app is a student prototype, **not a safety device**.

**What is recorded, and for how long:**

| Data | Kept | Where |
|---|---|---|
| Camera pictures | **30 minutes**, then deleted automatically; faces are blurred before storage | the team laptop only |
| Your spoken questions, as **text**, and the answers | until the project is graded (December 2026), then deleted | the team laptop only |
| The **audio** of your questions | only if you tick the box below; deleted after grading | the team laptop only |
| This form | your answers under a code (T1, T2, T3…), **never your name** | the project report |

Nothing is published with your name or face. Pictures are sent to Google's Gemini model
to produce the answers (as for any user of the app).

**Your rights:** taking part is voluntary. You can stop at any time without giving a
reason, and ask for your data to be deleted.

| | Yes | No |
|---|---|---|
| I understood the above and agree to take part. | ☐ | ☐ |
| I agree that the **audio** of my questions is recorded for the evaluation (optional). | ☐ | ☐ |

Tester code: **T___** Date: ____________ Signature: ________________________

---

## Part 2: The test (≈ 10 minutes, a team member guides)

Do as many as you like, in any language (English, French or Arabic):

1. Point the phone at a table with objects and ask **"What is in front of me?"**
2. Point it at a sign or a printed page and ask **"What does it say?"**
3. Look at something for a few seconds, turn away, then ask **"What was in front of me
   before?"**
4. Cover the camera with your hand and ask a question (the app should say it cannot see).
5. *(Optional, seated or guided)* Point the phone at stairs or a closed door and wait
   for the spoken warning.

---

## Part 3: Your opinion

Circle one number: **1 = strongly disagree, 2 = disagree, 3 = neutral, 4 = agree,
5 = strongly agree.**

| # | Statement | | | | | |
|---|---|---|---|---|---|---|
| q1 | Asking a question was easy (one big button). | 1 | 2 | 3 | 4 | 5 |
| q2 | The spoken answer was clear and easy to understand. | 1 | 2 | 3 | 4 | 5 |
| q3 | The answer came fast enough. | 1 | 2 | 3 | 4 | 5 |
| q4 | The answers matched what was really in front of me. | 1 | 2 | 3 | 4 | 5 |
| q5 | When the app was not sure, it said so. | 1 | 2 | 3 | 4 | 5 |
| q6 | The warnings (stairs, door) were helpful. *(skip if you did not hear one)* | 1 | 2 | 3 | 4 | 5 |
| q7 | I would use this app, or recommend it to a visually impaired person. | 1 | 2 | 3 | 4 | 5 |

**What was the best thing?** ______________________________________________

**What should be improved first?** ______________________________________________

---

## For the team: typing the results

One row per tester in `eval/results/feedback.csv`:

```csv
tester,consent,q1_easy,q2_voice_clear,q3_fast_enough,q4_matches,q5_says_unsure,q6_warnings,q7_would_use,comment
T1,yes,5,4,3,4,5,,4,"Best: one button. Improve: faster answers."
```

- `consent` must be **yes**; any other row is ignored by the report.
- Leave a number empty if the tester skipped it (e.g. q6 without a warning).
- `comment`: the two open answers, short, **without names**.
- Keep the signed paper forms until grading, then destroy them with the data.
