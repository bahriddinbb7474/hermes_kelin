-- Hermes/Mariyam — инициализация БД
-- Источник истины: TZ_Hermes_Mariyam_FINAL_v3_0.md, раздел 13
-- Все метки времени — UTC (TIMESTAMPTZ). Границы дня считаются в Asia/Tashkent (UTC+5).
-- Тийины не используются: amount — целое число в сумах.

-- ---------------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    telegram_id   BIGINT UNIQUE NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('oyijon','admin')),
    display_name  TEXT NOT NULL,
    language      TEXT DEFAULT 'uz-Cyrl',
    timezone      TEXT DEFAULT 'Asia/Tashkent',
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- expense_categories (фиксированный список из раздела 7.4)
-- parent_code ссылается на code той же таблицы (подкатегории еды).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS expense_categories (
    id           SERIAL PRIMARY KEY,
    code         TEXT UNIQUE NOT NULL,
    name_uz      TEXT NOT NULL,
    parent_code  TEXT REFERENCES expense_categories(code),
    active       BOOLEAN DEFAULT true
);

INSERT INTO expense_categories (code, name_uz, parent_code) VALUES
    ('food',            'Озиқ-овқат',                  NULL),
    ('food.meat',       'Гўшт',                        'food'),
    ('food.oil',        'Ёғ',                          'food'),
    ('food.vegetables', 'Сабзавот',                    'food'),
    ('food.fruits',     'Мевалар',                     'food'),
    ('food.bread',      'Нон',                         'food'),
    ('food.grains',     'Дон / ғалла',                 'food'),
    ('food.sweets',     'Ширинликлар',                 'food'),
    ('food.ready_food', 'Тайёр овқат',                 'food'),
    ('food.wholesale',  'Оптом / улуғ бозор',          'food'),
    ('medicine',        'Дори-дармон / саломатлик',    NULL),
    ('transport',       'Йўл / транспорт',             NULL),
    ('utilities',       'Коммунал тўловлар',           NULL),
    ('home',            'Уй / хўжалик',                NULL),
    ('clothes',         'Кийим-кечак',                 NULL),
    ('relatives_gifts', 'Қариндошлар / совға',         NULL),
    ('education',       'Ўқиш / таълим',               NULL),
    ('tax',             'Солиқ / расмий тўловлар',     NULL),
    ('other',           'Бошқа',                       NULL)
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- transactions (расходы и доходы)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transactions (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id),
    type          TEXT NOT NULL CHECK (type IN ('expense','income')),
    amount        NUMERIC(14,2) NOT NULL CHECK (amount >= 0),
    currency      TEXT NOT NULL CHECK (currency IN ('UZS','USD')),
    category_code TEXT REFERENCES expense_categories(code),
    item_name     TEXT,
    description   TEXT,
    source_text   TEXT,
    source_type   TEXT CHECK (source_type IN ('text','voice','admin')),
    occurred_at   TIMESTAMPTZ NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tx_user_time   ON transactions(user_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_tx_category    ON transactions(category_code);

-- ---------------------------------------------------------------------------
-- quran_progress
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quran_progress (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    surah       TEXT,
    juz         INTEGER,
    page        INTEGER,
    note        TEXT,
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- health_notes (без диагноза; severity для сортировки/фильтра)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS health_notes (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    note        TEXT NOT NULL,
    severity    TEXT CHECK (severity IN ('info','low','medium','high','critical')) DEFAULT 'info',
    source_text TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- alert_events (срочные / safety уведомления)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alert_events (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id),
    alert_type    TEXT NOT NULL,
    severity      TEXT NOT NULL CHECK (severity IN ('low','medium','high','critical')),
    source_text   TEXT NOT NULL,
    bot_response  TEXT,
    detected_by   TEXT CHECK (detected_by IN ('llm','keyword','both')),
    sent_to_admin BOOLEAN DEFAULT false,
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- plan_notes (планы, заметки, счётчики, если нужно как факт)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS plan_notes (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    kind        TEXT,           -- plan/counter/custom
    text        TEXT NOT NULL,
    value_int   INTEGER,        -- для счётчиков, опционально
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- usage_costs (оценка стоимости STT/TTS/LLM)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usage_costs (
    id                 SERIAL PRIMARY KEY,
    provider           TEXT,
    service_type       TEXT CHECK (service_type IN ('stt','tts','llm')),
    units              NUMERIC(14,4),
    estimated_cost_usd NUMERIC(10,4),
    created_at         TIMESTAMPTZ DEFAULT now()
);
