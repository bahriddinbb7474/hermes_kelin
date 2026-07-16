-- Hermes/Mariyam — Stage 5.3 product monthly plans (ТЗ v3.17)
-- Idempotent: safe to re-run. Apply AFTER 001_init.sql and
-- 002_stage51_quantity_budget.sql. Existing transactions and category plans are
-- intentionally untouched.

-- ---------------------------------------------------------------------------
-- monthly_budget_items: immutable reference-price snapshot per saved item plan
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS monthly_budget_items (
    id                        SERIAL PRIMARY KEY,
    user_id                   INTEGER NOT NULL REFERENCES users (id),
    month                     DATE NOT NULL,
    category_code             TEXT NOT NULL REFERENCES expense_categories (code),
    item_name_normalized      TEXT NOT NULL,
    item_name_display         TEXT NOT NULL,
    planned_quantity          NUMERIC(14, 3) NULL,
    unit                      TEXT NULL,
    planned_amount_uzs        NUMERIC(14, 2) NULL,
    reference_unit_price_uzs  NUMERIC(14, 4) NULL,
    price_basis               TEXT NULL,
    price_as_of               TIMESTAMPTZ NULL,
    note                      TEXT NULL,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT monthly_budget_items_user_month_category_item_key
        UNIQUE (user_id, month, category_code, item_name_normalized),
    CONSTRAINT monthly_budget_items_month_first_day
        CHECK (date_trunc('month', month)::date = month),
    CONSTRAINT monthly_budget_items_name_normalized_nonempty
        CHECK (btrim(item_name_normalized) <> ''),
    CONSTRAINT monthly_budget_items_name_display_nonempty
        CHECK (btrim(item_name_display) <> ''),
    CONSTRAINT monthly_budget_items_quantity_or_amount
        CHECK (planned_quantity IS NOT NULL OR planned_amount_uzs IS NOT NULL),
    CONSTRAINT monthly_budget_items_quantity_positive
        CHECK (planned_quantity IS NULL OR planned_quantity > 0),
    CONSTRAINT monthly_budget_items_amount_nonnegative
        CHECK (planned_amount_uzs IS NULL OR planned_amount_uzs >= 0),
    CONSTRAINT monthly_budget_items_unit_canonical
        CHECK (unit IS NULL OR unit IN ('kg', 'g', 'l', 'ml', 'pcs', 'pack')),
    CONSTRAINT monthly_budget_items_unit_with_quantity
        CHECK (unit IS NULL OR planned_quantity IS NOT NULL),
    CONSTRAINT monthly_budget_items_price_nonnegative
        CHECK (reference_unit_price_uzs IS NULL OR reference_unit_price_uzs >= 0),
    CONSTRAINT monthly_budget_items_price_basis_valid
        CHECK (price_basis IS NULL OR price_basis IN ('last', 'average', 'manual')),
    CONSTRAINT monthly_budget_items_price_with_unit
        CHECK (reference_unit_price_uzs IS NULL OR unit IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_mbi_user_month
    ON monthly_budget_items (user_id, month);

-- ---------------------------------------------------------------------------
-- monthly_plan_cycles: Stage 5.3A schema preparation only.
-- No approval tool, status transitions or cron runtime are implemented here.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS monthly_plan_cycles (
    id                   SERIAL PRIMARY KEY,
    user_id              INTEGER NOT NULL REFERENCES users (id),
    month                DATE NOT NULL,
    status               TEXT NOT NULL,
    household_size       INTEGER NULL,
    source               TEXT NOT NULL,
    proposed_at          TIMESTAMPTZ NULL,
    approved_at          TIMESTAMPTZ NULL,
    approved_by_user_id  INTEGER NULL REFERENCES users (id),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT monthly_plan_cycles_user_month_key UNIQUE (user_id, month),
    CONSTRAINT monthly_plan_cycles_month_first_day
        CHECK (date_trunc('month', month)::date = month),
    CONSTRAINT monthly_plan_cycles_status_valid
        CHECK (status IN (
            'draft',
            'waiting_oyijon',
            'waiting_admin',
            'approved_by_oyijon',
            'approved_by_admin',
            'auto_approved'
        )),
    CONSTRAINT monthly_plan_cycles_household_size_positive
        CHECK (household_size IS NULL OR household_size > 0),
    CONSTRAINT monthly_plan_cycles_source_valid
        CHECK (source IN ('calculated', 'copied_previous', 'manually_created'))
);

CREATE INDEX IF NOT EXISTS idx_mpc_user_month
    ON monthly_plan_cycles (user_id, month);
