-- Hermes/Mariyam — Stage 6 recurring obligations (TZ v3.19).
-- Idempotent: safe to re-run. Apply after 001_init.sql. Migration 004 is
-- intentionally absent while the utility-portal gate remains NO-GO.

CREATE TABLE IF NOT EXISTS recurring_obligations (
    id                       SERIAL PRIMARY KEY,
    user_id                  INTEGER NOT NULL REFERENCES users (id),
    obligation_type          TEXT NOT NULL,
    name                     TEXT NOT NULL,
    expected_amount_uzs      NUMERIC(14, 2) NOT NULL,
    due_date                 DATE NOT NULL,
    repeat_rule              TEXT NOT NULL,
    repeat_interval_days     INTEGER NULL,
    repeat_anchor_month      INTEGER NOT NULL,
    repeat_anchor_day        INTEGER NOT NULL,
    reminder_lead_days       INTEGER NOT NULL DEFAULT 3,
    active                   BOOLEAN NOT NULL DEFAULT true,
    paid                     BOOLEAN NOT NULL DEFAULT false,
    last_paid_due_date       DATE NULL,
    last_paid_at             TIMESTAMPTZ NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT recurring_obligations_type_valid
        CHECK (obligation_type IN ('internet', 'loan', 'tax', 'utility', 'other')),
    CONSTRAINT recurring_obligations_name_nonempty
        CHECK (btrim(name) <> ''),
    CONSTRAINT recurring_obligations_amount_nonnegative
        CHECK (expected_amount_uzs >= 0),
    CONSTRAINT recurring_obligations_repeat_rule_valid
        CHECK (repeat_rule IN ('none', 'monthly', 'yearly', 'interval_days')),
    CONSTRAINT recurring_obligations_interval_coherent
        CHECK (
            (repeat_rule = 'interval_days' AND repeat_interval_days > 0)
            OR
            (repeat_rule <> 'interval_days' AND repeat_interval_days IS NULL)
        ),
    CONSTRAINT recurring_obligations_anchor_month_valid
        CHECK (repeat_anchor_month BETWEEN 1 AND 12),
    CONSTRAINT recurring_obligations_anchor_day_valid
        CHECK (repeat_anchor_day BETWEEN 1 AND 31),
    CONSTRAINT recurring_obligations_reminder_lead_valid
        CHECK (reminder_lead_days BETWEEN 0 AND 365),
    CONSTRAINT recurring_obligations_paid_state_coherent
        CHECK (
            (paid AND NOT active AND repeat_rule = 'none')
            OR
            (NOT paid)
        ),
    CONSTRAINT recurring_obligations_user_type_name_key
        UNIQUE (user_id, obligation_type, name)
);

CREATE INDEX IF NOT EXISTS idx_recurring_obligations_user_due
    ON recurring_obligations (user_id, active, due_date);
