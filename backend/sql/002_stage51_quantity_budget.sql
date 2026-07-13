-- Hermes/Mariyam — Stage 5.1 analytics / monthly plan (ТЗ v3.7 §0.7, §13)
-- Idempotent: safe to re-run. Old transactions remain valid (new cols NULL).
-- Apply AFTER 001_init.sql.

-- ---------------------------------------------------------------------------
-- transactions: optional item normalization + physical quantity
-- ---------------------------------------------------------------------------
ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS item_name_normalized TEXT NULL;

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS quantity NUMERIC(14, 3) NULL;

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS unit TEXT NULL;

-- quantity > 0 when set (NULL allowed for legacy / unknown qty)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'transactions_quantity_positive'
    ) THEN
        ALTER TABLE transactions
            ADD CONSTRAINT transactions_quantity_positive
            CHECK (quantity IS NULL OR quantity > 0);
    END IF;
END $$;

-- unit only with quantity; canonical units for MVP
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'transactions_unit_with_quantity'
    ) THEN
        ALTER TABLE transactions
            ADD CONSTRAINT transactions_unit_with_quantity
            CHECK (unit IS NULL OR quantity IS NOT NULL);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'transactions_unit_canonical'
    ) THEN
        ALTER TABLE transactions
            ADD CONSTRAINT transactions_unit_canonical
            CHECK (
                unit IS NULL
                OR unit IN ('kg', 'g', 'l', 'ml', 'pcs', 'pack')
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_tx_item_norm
    ON transactions (user_id, item_name_normalized);

-- ---------------------------------------------------------------------------
-- monthly_budget_plans: one plan row per user + month + category
-- month = DATE (convention: first day of calendar month; app enforces)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS monthly_budget_plans (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users (id),
    month               DATE NOT NULL,
    category_code       TEXT NOT NULL REFERENCES expense_categories (code),
    planned_amount_uzs  NUMERIC(14, 2) NOT NULL CHECK (planned_amount_uzs >= 0),
    note                TEXT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, month, category_code)
);

CREATE INDEX IF NOT EXISTS idx_mbp_user_month
    ON monthly_budget_plans (user_id, month);
