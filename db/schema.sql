-- pgvector extension for embedding-based RAG
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. user_profiles
CREATE TABLE IF NOT EXISTS user_profiles (
    -- WhatsApp phone number in E.164 format e.g. +919876543210
    user_id             TEXT PRIMARY KEY,
    language            TEXT NOT NULL DEFAULT 'hi',
    persona_type        TEXT CHECK (
                            persona_type IN ('salaried', 'gig', 'farmer', 'freelancer')
                        ),
    monthly_income      NUMERIC(14, 2)  DEFAULT 0,
    monthly_expense     NUMERIC(14, 2)  DEFAULT 0,
    savings             NUMERIC(14, 2)  DEFAULT 0,

    -- Array of loan objects: [{source, amount, monthly_emi, detected_at}]
    loans               JSONB           DEFAULT '[]'::jsonb,

    last_nudge_at       TIMESTAMPTZ,
    seekho_level        INTEGER         DEFAULT 0,

    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     DEFAULT NOW()
);

-- 2. financial_events
--    Separate table (not JSONB) so we can query/aggregate events
CREATE TABLE IF NOT EXISTS financial_events (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT            NOT NULL
                        REFERENCES user_profiles(user_id) ON DELETE CASCADE,
    event_type      TEXT            NOT NULL
                        CHECK (event_type IN ('income', 'expense', 'loan', 'savings', 'query')),
    amount          NUMERIC(14, 2),
    description     TEXT,
    raw_message     TEXT,           -- original user message (kept for audit; never surfaced)
    occurred_at     TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS financial_events_user_id_idx
    ON financial_events (user_id, occurred_at DESC);

-- 3. profile_embeddings  (for RAG — Gemini text-embedding-004)
--    768-dim vectors from Gemini text-embedding-004
CREATE TABLE IF NOT EXISTS profile_embeddings (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT        NOT NULL
                    REFERENCES user_profiles(user_id) ON DELETE CASCADE,
    content     TEXT        NOT NULL,   -- the text that was embedded
    embedding   vector(768) NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS profile_embeddings_vector_idx
    ON profile_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);


--4. auto-update updated_at on user_profiles
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER user_profiles_updated_at
    BEFORE UPDATE ON user_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
