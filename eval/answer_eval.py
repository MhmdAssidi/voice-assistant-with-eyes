"""Student B evaluation (task B13): are the spoken answers right, and honest?

The test: 30 questions asked with the phone in real scenes (10 English, 10 French,
10 Arabic). Every question and answer is already saved in qa_log (task B11); a person
who SAW the scene then scores each answer by hand:

    correct        the answer matches what was really there
    partial        right, but incomplete or with a small mistake
    wrong          a false statement given as a fact (the dangerous case)
    honest_unsure  the answer starts with "I'm not sure" (the camera did not show it
                   clearly, or the model could not tell): honest, not a lie

    heard_ok       yes / no: did Whisper understand the question? (separates
                   speech-to-text mistakes from vision mistakes)

Two steps, run from backend/ (Docker must be running):
    python ../eval/answer_eval.py export --since 2026-11-20
        -> eval/results/answers.csv: one row per question; fill in truth, heard_ok, score
           (Excel opens it; scores already typed are kept when you export again)
    python ../eval/answer_eval.py report
        -> answers_summary.csv, answers.png, answers.md
           + feedback_summary.csv, feedback.png if eval/results/feedback.csv exists
             (the testers' forms, see docs/feedback-form.md)
"""

import argparse
import csv
import sys
from datetime import date, datetime
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
RESULTS = EVAL_DIR / "results"

SCORES = ["correct", "partial", "honest_unsure", "wrong"]
SCORE_NAMES = {"correct": "Correct", "partial": "Partly correct",
               "honest_unsure": "Honest \"not sure\"", "wrong": "Wrong (confident)"}
# Meaning colours with a text label on every segment: green good, yellow so-so,
# blue honest (not an error), red wrong.
SCORE_COLORS = {"correct": "#0ca30c", "partial": "#fab219", "honest_unsure": "#2a78d6",
                "wrong": "#d03b3b"}
DARK_TEXT_ON = {"partial"}  # white text is unreadable on yellow
LANGUAGES = ["en", "fr", "ar"]
LANGUAGE_NAMES = {"en": "English", "fr": "French", "ar": "Arabic", "all": "All"}
GOAL_PER_LANGUAGE = 10
ANSWER_FIELDS = ["id", "asked_at", "language", "question", "answer", "confident", "total_s",
                 "truth", "heard_ok", "score", "note"]
HAND_FIELDS = ["truth", "heard_ok", "score", "note"]

# The feedback form (docs/feedback-form.md): 1 = strongly disagree ... 5 = strongly agree
FEEDBACK_QUESTIONS = {
    "q1_easy": "Asking a question was easy",
    "q2_voice_clear": "The spoken answer was clear",
    "q3_fast_enough": "The answer came fast enough",
    "q4_matches": "Answers matched what was there",
    "q5_says_unsure": "It said so when it was not sure",
    "q6_warnings": "Warnings (stairs, door) helped",
    "q7_would_use": "I would use / recommend it",
}

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e1e0d9"
BAR_COLOR = "#2a78d6"

# Excel on Windows reads UTF-8 (Arabic, French accents) only with a BOM: "utf-8-sig".
ENCODING = "utf-8-sig"


# ---------- step 1: export ----------


def export(since: date | None, path: Path) -> int:
    sys.path.insert(0, str(EVAL_DIR.parent / "backend"))
    import psycopg
    from psycopg.rows import dict_row

    from app.config import settings

    query = "SELECT id, asked_at, language, question, answer, confident, timings_ms FROM qa_log"
    params: list = []
    if since:
        query += " WHERE asked_at >= %s"
        params.append(since)
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        rows = conn.execute(query + " ORDER BY asked_at", params).fetchall()

    already = {row["id"]: row for row in read_csv(path)} if path.exists() else {}
    out = []
    for row in rows:
        kept = already.get(str(row["id"]), {})
        out.append({
            "id": row["id"],
            "asked_at": row["asked_at"].astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            "language": row["language"],
            "question": row["question"],
            "answer": row["answer"],
            "confident": "yes" if row["confident"] else "no",
            "total_s": round(int((row["timings_ms"] or {}).get("total", 0)) / 1000, 1),
            **{field: kept.get(field, "") for field in HAND_FIELDS},
        })
    write_csv(path, out, ANSWER_FIELDS)
    return len(out)


# ---------- step 2: report ----------


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding=ENCODING, newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=ENCODING, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def scored_rows(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """Rows with a valid score, and a list of problems to show the user."""
    good, problems = [], []
    for row in rows:
        score = row.get("score", "").strip().lower().replace(" ", "_").replace("-", "_")
        if not score:
            continue
        if score not in SCORES:
            problems.append(f"id {row['id']}: unknown score '{row['score']}' (use {SCORES})")
            continue
        if score == "wrong" and row.get("confident") == "no":
            problems.append(f"id {row['id']}: 'wrong' but the answer said it was not sure "
                            "-> should it be honest_unsure?")
        good.append({**row, "score": score})
    return good, problems


def summarize_answers(rows: list[dict]) -> list[dict]:
    summary = []
    for group in [*LANGUAGES, "all"]:
        in_group = [r for r in rows if group == "all" or r["language"] == group]
        n = len(in_group)
        counts = {s: sum(r["score"] == s for r in in_group) for s in SCORES}
        heard = [r for r in in_group if r.get("heard_ok", "").strip().lower() in ("yes", "no")]
        summary.append({
            "group": group,
            "n": n,
            **counts,
            "correct_pct": _pct(counts["correct"], n),
            "useful_pct": _pct(counts["correct"] + counts["partial"], n),
            "honest_unsure_pct": _pct(counts["honest_unsure"], n),
            "wrong_pct": _pct(counts["wrong"], n),
            "heard_ok_pct": _pct(sum(r["heard_ok"].strip().lower() == "yes" for r in heard),
                                 len(heard)),
        })
    return summary


def summarize_feedback(rows: list[dict]) -> tuple[list[dict], int]:
    """Mean 1-5 per question over the testers who gave consent."""
    consenting = [r for r in rows if r.get("consent", "").strip().lower() == "yes"]
    summary = []
    for key, text in FEEDBACK_QUESTIONS.items():
        values = [int(r[key]) for r in consenting if r.get(key, "").strip().isdigit()]
        values = [v for v in values if 1 <= v <= 5]
        summary.append({"question": key, "text": text, "n": len(values),
                        "mean": round(sum(values) / len(values), 2) if values else None})
    return summary, len(consenting)


def _pct(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


# ---------- charts ----------


def _style(ax) -> None:  # noqa: ANN001
    ax.set_facecolor(SURFACE)
    ax.tick_params(axis="x", colors=INK_2, labelsize=8)
    ax.tick_params(axis="y", length=0, labelsize=9, labelcolor=INK)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)


def draw_answers_chart(summary: list[dict], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    groups = [g for g in summary if g["n"]]
    fig, ax = plt.subplots(figsize=(8, 0.75 * len(groups) + 1.6), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    for y, group in enumerate(groups):
        left = 0.0
        for score in SCORES:
            share = 100 * group[score] / group["n"]
            if not share:
                continue
            # white edge = the 2 px gap between segments
            ax.barh(y, share, left=left, height=0.55, color=SCORE_COLORS[score],
                    edgecolor=SURFACE, linewidth=1.5,
                    label=SCORE_NAMES[score] if y == 0 else None)
            if share >= 7:
                ax.text(left + share / 2, y, str(group[score]), ha="center", va="center",
                        fontsize=8, color=INK if score in DARK_TEXT_ON else "#ffffff")
            left += share
    ax.set_yticks(range(len(groups)),
                  [f"{LANGUAGE_NAMES[g['group']]} ({g['n']})" for g in groups])
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of questions (numbers inside = how many)", color=INK_2, fontsize=9)
    ax.set_title("Answer quality per language", loc="left", fontsize=11, color=INK, pad=24)
    # one legend entry per score, even if the first group lacks it
    handles = [plt.Rectangle((0, 0), 1, 1, color=SCORE_COLORS[s]) for s in SCORES]
    ax.legend(handles, [SCORE_NAMES[s] for s in SCORES], frameon=False, fontsize=8, ncol=4,
              loc="lower left", bbox_to_anchor=(0, 1.0), labelcolor=INK, borderaxespad=0.2)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def draw_feedback_chart(summary: list[dict], testers: int, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = [r for r in summary if r["mean"] is not None]
    fig, ax = plt.subplots(figsize=(8, 0.45 * len(rows) + 1.3), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    bars = ax.barh(range(len(rows)), [r["mean"] for r in rows], height=0.55, color=BAR_COLOR)
    for bar, row in zip(bars, rows, strict=True):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, f"  {row['mean']:.1f}",
                va="center", fontsize=8, color=INK)
    ax.set_yticks(range(len(rows)), [r["text"] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(1, 5.4)
    ax.set_xticks([1, 2, 3, 4, 5])
    ax.set_xlabel("mean score: 1 = strongly disagree … 5 = strongly agree", color=INK_2,
                  fontsize=9)
    ax.set_title(f"Tester feedback ({testers} consenting testers)", loc="left", fontsize=11,
                 color=INK)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


# ---------- markdown ----------


def write_markdown(path: Path, summary: list[dict], unscored: int, feedback, testers: int,
                   comments: list[str]) -> None:
    lines = [
        "# Answer accuracy and user feedback (Student B, task B13)",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `eval/answer_eval.py report` from "
        "`answers.csv` (scored by hand by a person who saw each scene).",
        "",
        "| Language | Questions | Correct | Partly | Honest \"not sure\" | Wrong (confident) "
        "| Correct + partly | Question heard right |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for g in summary:
        lines.append(
            f"| {LANGUAGE_NAMES[g['group']]} | {g['n']} | {g['correct']} | {g['partial']} | "
            f"{g['honest_unsure']} | {g['wrong']} | {_fmt_pct(g['useful_pct'])} | "
            f"{_fmt_pct(g['heard_ok_pct'])} |"
        )
    missing = [f"{LANGUAGE_NAMES[g['group']]} {g['n']}/{GOAL_PER_LANGUAGE}" for g in summary
               if g["group"] in LANGUAGES and g["n"] < GOAL_PER_LANGUAGE]
    lines += ["", "![Answer quality per language](answers.png)", ""]
    if missing:
        lines.append(f"Goal not reached yet (10 per language): {', '.join(missing)}.")
    if unscored:
        lines.append(f"{unscored} exported questions are not scored yet.")
    lines += ["", "**Wrong (confident)** is the number to keep at zero: a false fact said "
              "without \"I'm not sure\". An honest \"not sure\" is not an error."]
    if feedback is not None:
        lines += ["", f"## User feedback ({testers} consenting testers)", "",
                  "| Statement | Answers | Mean (1–5) |", "|---|---|---|"]
        for row in feedback:
            mean = f"{row['mean']:.1f}" if row["mean"] is not None else "–"
            lines.append(f"| {row['text']} | {row['n']} | {mean} |")
        lines += ["", "![Tester feedback](feedback.png)"]
        if comments:
            lines += ["", "Comments:", ""] + [f"- \"{c}\"" for c in comments]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fmt_pct(value: float | None) -> str:
    return "–" if value is None else f"{value:.0f} %"


def report(results: Path) -> None:
    answers_path = results / "answers.csv"
    if not answers_path.exists():
        sys.exit(f"{answers_path} not found: run 'export' first, then score the answers.")
    all_rows = read_csv(answers_path)
    rows, problems = scored_rows(all_rows)
    for problem in problems:
        print("check:", problem)
    if not rows:
        sys.exit("No scored answers yet: fill in the 'score' column of answers.csv.")

    summary = summarize_answers(rows)
    write_csv(results / "answers_summary.csv", summary, list(summary[0]))
    draw_answers_chart(summary, results / "answers.png")

    feedback, testers, comments = None, 0, []
    feedback_path = results / "feedback.csv"
    if feedback_path.exists():
        feedback_rows = read_csv(feedback_path)
        feedback, testers = summarize_feedback(feedback_rows)
        comments = [r["comment"].strip() for r in feedback_rows
                    if r.get("consent", "").strip().lower() == "yes"
                    and r.get("comment", "").strip()]
        write_csv(results / "feedback_summary.csv", feedback, list(feedback[0]))
        if any(r["mean"] is not None for r in feedback):
            draw_feedback_chart(feedback, testers, results / "feedback.png")

    write_markdown(results / "answers.md", summary, len(all_rows) - len(rows) - len(problems),
                   feedback, testers, comments)
    for g in summary:
        print(f"{LANGUAGE_NAMES[g['group']]:<8} n={g['n']:<3} correct {g['correct']:<3} "
              f"partly {g['partial']:<3} not-sure {g['honest_unsure']:<3} wrong {g['wrong']}")
    if feedback is not None:
        print(f"Feedback from {testers} consenting testers summarised.")
    print(f"Written to {results}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="qa_log -> answers.csv (to score by hand)")
    exp.add_argument("--since", type=date.fromisoformat, help="only questions from this day")
    rep = sub.add_parser("report", help="scored answers.csv (+ feedback.csv) -> summary, charts")
    for p in (exp, rep):
        p.add_argument("--results", type=Path, default=RESULTS)
    args = parser.parse_args()

    if args.command == "export":
        n = export(args.since, args.results / "answers.csv")
        print(f"{n} questions written to {args.results / 'answers.csv'}: "
              "fill in truth, heard_ok (yes/no) and score, then run 'report'.")
    else:
        report(args.results)


if __name__ == "__main__":
    main()
