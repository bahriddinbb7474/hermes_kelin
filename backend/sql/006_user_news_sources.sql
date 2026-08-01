-- User-owned RSS/Atom sources.  Defaults remain in news_sources.json.
-- Idempotent and intentionally numbered 006 (004 remains reserved/no-go).

CREATE TABLE IF NOT EXISTS user_news_sources (
    id             SERIAL PRIMARY KEY,
    user_id        INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    source_key     TEXT NOT NULL,
    display_name   TEXT NOT NULL,
    url            TEXT NOT NULL,
    topics         TEXT[] NOT NULL DEFAULT '{}',
    active         BOOLEAN NOT NULL DEFAULT true,
    added_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    added_by       TEXT NOT NULL,
    disabled_at    TIMESTAMPTZ NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT user_news_sources_key_valid
        CHECK (source_key ~ '^[a-z0-9_]{2,40}$'),
    CONSTRAINT user_news_sources_name_nonempty CHECK (btrim(display_name) <> ''),
    CONSTRAINT user_news_sources_https CHECK (url ~ '^https://'),
    CONSTRAINT user_news_sources_added_by_valid CHECK (added_by IN ('oyijon','admin')),
    CONSTRAINT user_news_sources_active_coherent
        CHECK ((active AND disabled_at IS NULL) OR (NOT active AND disabled_at IS NOT NULL)),
    CONSTRAINT user_news_sources_user_key UNIQUE (user_id, source_key),
    CONSTRAINT user_news_sources_user_url UNIQUE (user_id, url)
);

CREATE INDEX IF NOT EXISTS idx_user_news_sources_user_active
    ON user_news_sources (user_id, active, id);
