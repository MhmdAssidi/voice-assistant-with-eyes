-- Questions and answers history (owner: Student B, task B11).
-- Runs automatically the FIRST time the Postgres container starts with an empty volume.
-- The API also runs it on first use (qa_repository._ensure_schema), so an existing
-- database gets the table without "docker compose down -v". Hence IF NOT EXISTS.
--
-- No foreign key to frames: retention deletes old frames, the Q&A history stays.

CREATE TABLE IF NOT EXISTS qa_log (
  id SERIAL PRIMARY KEY,
  asked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  question TEXT NOT NULL,
  language VARCHAR(2) NOT NULL,
  answer TEXT NOT NULL,
  confident BOOLEAN NOT NULL,
  evidence JSONB DEFAULT '[]',
  timings_ms JSONB DEFAULT '{}'
);

-- History page: newest first
CREATE INDEX IF NOT EXISTS qa_log_time_idx ON qa_log (asked_at DESC);
