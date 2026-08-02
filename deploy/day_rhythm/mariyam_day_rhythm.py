"""Deterministic prayer templates and non-critical delivery quiet gate."""

from __future__ import annotations

import json
import os
import re
import stat
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TASHKENT = ZoneInfo("Asia/Tashkent")
STATE_VERSION = 1
PRAYER_WINDOW_MINUTES = 20
QURAN_QUIET_MINUTES = 90
SLEEP_END_HOUR = 8
DEFAULT_STATE_PATH = Path("/opt/hermes-mariyam/var/day-rhythm/quiet-state.json")
DEFAULT_CACHE_PATH = Path("/opt/hermes-mariyam/var/external-data-cache.json")
SLOTS = ("fajr", "dhuhr", "asr", "maghrib", "isha")
SLOT_NAMES = {
    "fajr": "Бомдод",
    "dhuhr": "Пешин",
    "asr": "Аср",
    "maghrib": "Шом",
    "isha": "Хуфтон",
}

PRAYER_TEMPLATES = {
    "fajr": (
        "Ассалому алайкум ва роҳматуллоҳи ва барокатуҳ, Ойижон. Бомдод намозига оз қолди. Намоз уйқудан афзал. Ҳаммаси яхшими? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум ва роҳматуллоҳи ва барокатуҳ, Ойижон. Тонгги бомдод вақти яқинлашди. Намоз уйқудан афзал. Кўнглингиз тинчми? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум ва роҳматуллоҳи ва барокатуҳ, Ойижон. Бомдодга тайёрланадиган пайт бўлди. Намоз уйқудан афзал. Ўзингиз яхшимисиз? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум ва роҳматуллоҳи ва барокатуҳ, Ойижон. Бомдод намозига ўн дақиқа қолди. Намоз уйқудан афзал. Ҳолингиз яхшими? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум ва роҳматуллоҳи ва барокатуҳ, Ойижон. Баракали тонгда бомдод вақти яқин. Намоз уйқудан афзал. Ҳаммаси жойидами? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум ва роҳматуллоҳи ва барокатуҳ, Ойижон. Бомдод намози яқинлашиб қолди. Намоз уйқудан афзал. Кайфиятингиз яхшими? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум ва роҳматуллоҳи ва барокатуҳ, Ойижон. Тонг ибодати — бомдодга оз вақт қолди. Намоз уйқудан афзал. Тинчмисиз? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум ва роҳматуллоҳи ва барокатуҳ, Ойижон. Бомдод вақтига яқинлашдик. Намоз уйқудан афзал. Ўзингизни яхши ҳис қиляпсизми? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум ва роҳматуллоҳи ва барокатуҳ, Ойижон. Бомдодга туриб оладиган пайт яқин. Намоз уйқудан афзал. Ҳаммаси тинчми? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум ва роҳматуллоҳи ва барокатуҳ, Ойижон. Бугунги бомдод намозига оз қолди. Намоз уйқудан афзал. Кўнглингиз жойидами? Бирор хизмат бўлса, шу ердаман.",
    ),
    "dhuhr": (
        "Ассалому алайкум, Ойижон. Пешин намозига оз қолди. Кунингиз тинч ўтяптими? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Пешинга тайёрланадиган пайт яқинлашди. Ҳаммаси яхшими? Бирор хизмат бўлса, шу ердаман.",
        "Хайрли кун, Ойижон. Пешин намозига ўн дақиқа қолди. Ўзингиз яхшимисиз? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Пешин вақти яқин. Ишларингиз жойидами? Бирор хизмат бўлса, шу ердаман.",
        "Хайрли кун, Ойижон. Пешин намози яқинлашиб қолди. Кўнглингиз тинчми? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Пешинга озгина вақт қолди. Чарчамадингизми? Бирор хизмат бўлса, шу ердаман.",
        "Хайрли кун, Ойижон. Пешин ибодати вақти яқинлашди. Ҳолингиз яхшими? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Бугунги пешин намозига оз қолди. Ҳаммаси тинчми? Бирор хизмат бўлса, шу ердаман.",
        "Хайрли кун, Ойижон. Пешин вақтига яқинлашдик. Ўзингизни яхши ҳис қиляпсизми? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Пешин намозига тайёрланиб оладиган пайт бўлди. Кунингиз яхшими? Бирор хизмат бўлса, шу ердаман.",
    ),
    "asr": (
        "Хайрли кун, Ойижон. Аср намозига оз қолди. Ҳаммаси яхшими? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Аср вақти яқинлашди. Чарчамадингизми? Бирор хизмат бўлса, шу ердаман.",
        "Хайрли кун, Ойижон. Аср намозига ўн дақиқа қолди. Кўнглингиз тинчми? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Асрга тайёрланадиган пайт яқин. Ўзингиз яхшимисиз? Бирор хизмат бўлса, шу ердаман.",
        "Хайрли кун, Ойижон. Бугунги аср намози яқинлашиб қолди. Ишларингиз жойидами? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Аср ибодатига оз вақт қолди. Ҳолингиз яхшими? Бирор хизмат бўлса, шу ердаман.",
        "Хайрли кун, Ойижон. Аср вақтига яқинлашдик. Ҳаммаси тинчми? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Аср намози учун тайёрланиб оладиган пайт бўлди. Кайфиятингиз яхшими? Бирор хизмат бўлса, шу ердаман.",
        "Хайрли кун, Ойижон. Аср намозига озгина қолди. Ўзингизни яхши ҳис қиляпсизми? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Аср вақти яқин. Кунингиз яхши ўтяптими? Бирор хизмат бўлса, шу ердаман.",
    ),
    "maghrib": (
        "Хайрли оқшом, Ойижон. Шом намозига оз қолди. Ҳаммаси яхшими? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Шом вақти яқинлашди. Кунингиз тинч ўтдими? Бирор хизмат бўлса, шу ердаман.",
        "Хайрли оқшом, Ойижон. Шом намозига ўн дақиқа қолди. Чарчамадингизми? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Шомга тайёрланадиган пайт яқин. Кўнглингиз тинчми? Бирор хизмат бўлса, шу ердаман.",
        "Хайрли оқшом, Ойижон. Бугунги шом намози яқинлашди. Ўзингиз яхшимисиз? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Шом ибодатига оз вақт қолди. Ҳолингиз яхшими? Бирор хизмат бўлса, шу ердаман.",
        "Хайрли оқшом, Ойижон. Шом вақтига яқинлашдик. Ҳаммаси тинчми? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Шом намози учун тайёрланиб оладиган пайт бўлди. Кайфиятингиз яхшими? Бирор хизмат бўлса, шу ердаман.",
        "Хайрли оқшом, Ойижон. Шом намозига озгина қолди. Ўзингизни яхши ҳис қиляпсизми? Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Шом вақти яқин. Оқшомингиз тинчми? Бирор хизмат бўлса, шу ердаман.",
    ),
    "isha": (
        "Хайрли кеч, Ойижон. Хуфтон намозига оз қолди. Бугун қон босимингизни ўлчадингизми? Айтсангиз, ёзиб қўяман. Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Хуфтон вақти яқинлашди. Қон босимингизни бугун текшириб кўрдингизми? Натижасини айтсангиз, кундаликка қайд қиламан. Бирор хизмат бўлса, шу ердаман.",
        "Хайрли кеч, Ойижон. Хуфтон намозига ўн дақиқа қолди. Бугун босимингизни ўлчашга улгурдингизми? Рақамларини айтсангиз, ёзиб қўяман. Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Хуфтонга тайёрланадиган пайт яқин. Қон босими ўлчовини бугун қилдингизми? Натижасини айтсангиз, қайд этиб қўяман. Бирор хизмат бўлса, шу ердаман.",
        "Хайрли кеч, Ойижон. Бугунги хуфтон намози яқинлашди. Босимингизни кечқурун ўлчаб кўрдингизми? Айтганингизни кундаликка ёзиб қўяман. Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Хуфтон ибодатига оз вақт қолди. Бугунги қон босими ўлчовингиз борми? Айтсангиз, кундаликка киритиб қўяман. Бирор хизмат бўлса, шу ердаман.",
        "Хайрли кеч, Ойижон. Хуфтон вақтига яқинлашдик. Қон босимингизни текшириб қўйдингизми? Натижасини айтсангиз, сақлаб қўяман. Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Хуфтон намози учун тайёрланиб оладиган пайт бўлди. Бугун босим ҳақида ўлчов қилдингизми? Натижасини айтсангиз, қайд қиламан. Бирор хизмат бўлса, шу ердаман.",
        "Хайрли кеч, Ойижон. Хуфтон намозига озгина қолди. Қон босимингизни ўлчаб, натижасини ёзиб қўйдингизми? Айтсангиз, мен ҳам кундаликка киритаман. Бирор хизмат бўлса, шу ердаман.",
        "Ассалому алайкум, Ойижон. Хуфтон вақти яқин. Босим ўлчовини бугун амалга оширдингизми? Натижасини айтсангиз, ёзиб қўяман. Бирор хизмат бўлса, шу ердаман.",
    ),
}


def _state_path() -> Path:
    return Path(os.environ.get("MARIYAM_QUIET_STATE_FILE") or DEFAULT_STATE_PATH)


def _cache_path() -> Path:
    return Path(os.environ.get("MARIYAM_EXTERNAL_CACHE_FILE") or DEFAULT_CACHE_PATH)


def _normalize(text: str) -> str:
    value = text.casefold().replace("’", "'").replace("ʻ", "'").replace("`", "'")
    return re.sub(r"\s+", " ", value).strip(" .,!?:;—-")


def quiet_kind(text: object) -> str | None:
    if not isinstance(text, str):
        return None
    normalized = _normalize(text)
    if re.search(r"(?:^|\s)(сплю|ухлаяпман|ухлайман)(?:$|\s)", normalized):
        return "sleep"
    if re.search(
        r"(?:қуръон|куръон)\s+(?:ўқияпман|укияпман|ўқиб\s+турибман)",
        normalized,
    ):
        return "quran"
    return None


def _quiet_until(kind: str, now: datetime) -> datetime:
    local = now.astimezone(TASHKENT)
    if kind == "quran":
        return local + timedelta(minutes=QURAN_QUIET_MINUTES)
    morning = datetime.combine(local.date(), time(SLEEP_END_HOUR), TASHKENT)
    return morning if local < morning else morning + timedelta(days=1)


def activate_quiet(text: object, *, now: datetime | None = None) -> str | None:
    kind = quiet_kind(text)
    if kind is None:
        return None
    local_now = (now or datetime.now(TASHKENT)).astimezone(TASHKENT)
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": STATE_VERSION,
        "kind": kind,
        "set_at": local_now.isoformat(),
        "until": _quiet_until(kind, local_now).isoformat(),
    }
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    old_umask = os.umask(0o077)
    try:
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if os.name == "posix":
            os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        os.umask(old_umask)
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
    return kind


def _read_private_state(path: Path) -> dict | None:
    try:
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            return None
        if os.name == "posix" and stat.S_IMODE(info.st_mode) != 0o600:
            return None
        if info.st_size > 16 * 1024:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or value.get("version") != STATE_VERSION
            or value.get("kind") not in {"sleep", "quran"}
            or not isinstance(value.get("until"), str)
        ):
            return None
        return value
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _quiet_active(now: datetime) -> bool:
    state = _read_private_state(_state_path())
    if state is None:
        return False
    try:
        until = datetime.fromisoformat(state["until"])
    except ValueError:
        return False
    return until.tzinfo is not None and now.astimezone(TASHKENT) < until.astimezone(TASHKENT)


def _cached_prayer_times(now: datetime) -> dict[str, str] | None:
    try:
        raw = _cache_path().read_bytes()
        if len(raw) > 2_000_000:
            return None
        cache = json.loads(raw.decode("utf-8"))
        entry = cache.get("entries", {}).get("prayer_tashkent_fatvo_v1")
        fetched_at = datetime.fromisoformat(entry["fetched_at"].replace("Z", "+00:00"))
        data = entry["data"]
        if fetched_at.astimezone(TASHKENT).date() != now.astimezone(TASHKENT).date():
            return None
        result = {slot: data[slot] for slot in SLOTS}
        if not all(re.fullmatch(r"\d{2}:\d{2}", value) for value in result.values()):
            return None
        return result
    except (KeyError, OSError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _inside_prayer_window(now: datetime) -> bool:
    local = now.astimezone(TASHKENT)
    timings = _cached_prayer_times(local)
    if timings is None:
        return False
    for value in timings.values():
        hour, minute = map(int, value.split(":"))
        start = datetime.combine(local.date(), time(hour, minute), TASHKENT)
        if start <= local < start + timedelta(minutes=PRAYER_WINDOW_MINUTES):
            return True
    return False


def should_deliver_noncritical(
    *, now: datetime | None = None, critical: bool = False
) -> bool:
    if critical:
        return True
    local_now = (now or datetime.now(TASHKENT)).astimezone(TASHKENT)
    return not _quiet_active(local_now) and not _inside_prayer_window(local_now)


def emit_noncritical(message: str) -> None:
    if should_deliver_noncritical():
        print(message, flush=True)


def render_prayer_reminder(slot: str, day: date) -> str:
    templates = PRAYER_TEMPLATES[slot]
    return templates[day.toordinal() % len(templates)]


def render_prayer_times(
    timings: dict[str, str], hijri_display_uz: str | None = None
) -> str:
    lines = ["Ойижон, бугунги намоз вақтлари:"]
    if hijri_display_uz:
        lines.append(hijri_display_uz)
    lines.extend(f"• {SLOT_NAMES[slot]} — {timings[slot]}" for slot in SLOTS)
    lines.append("Ҳар намоздан 10 дақиқа олдин эслатаман.")
    return "\n".join(lines)


def reminder_times(day: date, timings: dict[str, str]) -> dict[str, datetime]:
    result = {}
    for slot in SLOTS:
        hour, minute = map(int, timings[slot].split(":"))
        prayer = datetime.combine(day, time(hour, minute), TASHKENT)
        result[slot] = prayer - timedelta(minutes=10)
    return result
