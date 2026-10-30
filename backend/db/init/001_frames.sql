-- Frames table: the multimedia database (owner: Student A, task A1).
-- Runs automatically the FIRST time the Postgres container starts with an empty volume.
-- To re-run it: docker compose down -v  then  docker compose up -d  (this erases all data).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE frames (
  id SERIAL PRIMARY KEY,
  captured_at TIMESTAMPTZ NOT NULL,
  image_path TEXT NOT NULL,            -- relative to FRAMES_DIR, e.g. "frames/123.jpg"
  thumb_path TEXT NOT NULL,            -- relative to FRAMES_DIR, e.g. "thumbs/123.jpg"
  width INT, height INT,
  sharpness REAL, brightness REAL,
  enhanced BOOLEAN DEFAULT FALSE,
  dhash BIGINT,                        -- 64-bit perceptual hash (stored signed)
  ocr_text TEXT DEFAULT '',
  ocr_blocks JSONB DEFAULT '[]',
  objects JSONB DEFAULT '[]',
  caption_text TEXT DEFAULT '',        -- OCR + objects, used for the text embedding
  image_emb vector(512),               -- CLIP image embedding
  text_emb vector(512),                -- multilingual CLIP embedding of caption_text
  ocr_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', ocr_text)) STORED
);

-- Time window queries and the Timeline (newest first)
CREATE INDEX frames_time_idx ON frames (captured_at DESC);
-- Search by meaning: approximate nearest neighbours with cosine distance
CREATE INDEX frames_img_hnsw ON frames USING hnsw (image_emb vector_cosine_ops);
CREATE INDEX frames_txt_hnsw ON frames USING hnsw (text_emb vector_cosine_ops);
-- Search by exact words read on signs
CREATE INDEX frames_ocr_gin ON frames USING gin (ocr_tsv);
