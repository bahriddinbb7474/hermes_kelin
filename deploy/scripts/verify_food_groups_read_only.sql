-- imp01, stage 2, case 2: read-only check of the August 007 migration.
-- STRICTLY SELECT — no INSERT/UPDATE/DELETE, safe to run more than once.
-- Scoped to the real Oyijon (role='oyijon'), expense transactions, UZS,
-- August 2026 in Asia/Tashkent (occurred_at is TIMESTAMPTZ, so the
-- +05:00 offset bounds below are correct regardless of session timezone).
--
-- Expected: food.ready_food row_count = 0; food.drinks = 51490;
-- food.dairy = 26000; food.sauces = 17890; food.semi = 50000;
-- TOTAL group_total = 1712208 (whole month, all categories).

WITH month_scope AS (
    SELECT t.category_code, t.amount
    FROM transactions t
    JOIN users u ON u.id = t.user_id
    WHERE u.role = 'oyijon'
      AND t.type = 'expense'
      AND t.currency = 'UZS'
      AND t.occurred_at >= '2026-08-01T00:00:00+05:00'
      AND t.occurred_at <  '2026-09-01T00:00:00+05:00'
),
categories(code) AS (
    VALUES ('food.ready_food'), ('food.drinks'), ('food.dairy'),
           ('food.sauces'), ('food.semi')
)
SELECT c.code                       AS category_code,
       ec.name_uz                   AS category_name,
       COUNT(m.amount)              AS row_count,
       COALESCE(SUM(m.amount), 0)   AS group_total
FROM categories c
JOIN expense_categories ec ON ec.code = c.code
LEFT JOIN month_scope m ON m.category_code = c.code
GROUP BY c.code, ec.name_uz

UNION ALL

SELECT 'TOTAL', 'ИТОГО (весь месяц)', COUNT(*), COALESCE(SUM(amount), 0)
FROM month_scope

ORDER BY category_code;
