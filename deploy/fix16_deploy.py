"""Controlled profile-only deploy for fix16 (run as timeagent on the VPS).

The script never prints secrets.  It creates a private rollback bundle before
changing config/.env/auth/routing state or installing the profile plugin.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml


PROFILE = Path.home() / ".hermes" / "profiles" / "mariyam_oyijon"
PLUGIN_SOURCE = Path("/tmp/fix16-runtime-guard")
PLUGIN_TARGET = PROFILE / "plugins" / "mariyam_runtime_guard"
CONFIG = PROFILE / "config.yaml"
ENV_FILE = PROFILE / ".env"
AUTH = PROFILE / "auth.json"
TMP_CACHE = PROFILE / ".models_dev_cache_wb3y4ug4.tmp"


def _atomic_text(path: Path, text: str) -> None:
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.fix16-", dir=path.parent)
    tmp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _backup() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = PROFILE / "backups" / f"fix16-{stamp}"
    target.mkdir(parents=True, mode=0o700)
    os.chmod(target, 0o700)
    paths = (
        CONFIG,
        ENV_FILE,
        AUTH,
        PROFILE / "sessions" / "sessions.json",
        PROFILE / "state.db",
        TMP_CACHE,
    )
    for source in paths:
        if source.is_file() and not source.is_symlink():
            destination = target / source.name
            shutil.copy2(source, destination)
            os.chmod(destination, 0o600)
    if PLUGIN_TARGET.is_dir() and not PLUGIN_TARGET.is_symlink():
        destination = target / "mariyam_runtime_guard"
        shutil.copytree(PLUGIN_TARGET, destination)
        for item in destination.rglob("*"):
            if item.is_file():
                os.chmod(item, 0o600)
    return target


def _patch_config() -> None:
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RuntimeError("config.yaml root must be a mapping")

    data["model"] = {"default": "gpt-5.6-luna", "provider": "custom:n1n"}
    providers = data.setdefault("providers", {})
    if not isinstance(providers, dict):
        raise RuntimeError("config providers must be a mapping")
    providers["n1n"] = {
        "name": "n1n",
        "base_url": "https://api.n1n.ai/v1",
        "key_env": "N1N_API_KEY",
        "default_model": "gpt-5.6-luna",
        "transport": "chat_completions",
    }
    data["fallback_providers"] = [
        {"provider": "openrouter", "model": "openai/gpt-5.6-luna"}
    ]
    # Remove the incomplete legacy selector that caused bare custom to use the
    # OpenRouter default.  Secrets remain in .env, never in config.yaml.
    for key in ("provider", "base_url", "api_key"):
        data.pop(key, None)

    plugins = data.setdefault("plugins", {})
    enabled = plugins.setdefault("enabled", [])
    if not isinstance(enabled, list):
        raise RuntimeError("plugins.enabled must be a list")
    enabled = [name for name in enabled if name != "mariyam_runtime_guard"]
    try:
        outbound_index = enabled.index("mariyam_outbound_filter")
    except ValueError:
        outbound_index = len(enabled)
    enabled.insert(outbound_index, "mariyam_runtime_guard")
    plugins["enabled"] = enabled

    reset = data.setdefault("session_reset", {})
    reset.update({"mode": "daily", "at_hour": 2, "notify": False})
    _atomic_text(CONFIG, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))


def _clean_env_command_prefix() -> bool:
    text = ENV_FILE.read_text(encoding="utf-8")
    marker = "sudo nano /home/timeagent/.hermes/profiles/mariyam_oyijon/.env"
    if text.startswith(marker):
        text = text[len(marker):]
        if not text.startswith("#"):
            text = "\n" + text
        _atomic_text(ENV_FILE, text)
        return True
    return False


def _clean_auth() -> list[str]:
    data = json.loads(AUTH.read_text(encoding="utf-8"))
    pool = data.get("credential_pool")
    removed: list[str] = []
    if isinstance(pool, dict) and "openai-api" in pool:
        pool.pop("openai-api", None)
        removed.append("openai-api")
    _atomic_text(AUTH, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return removed


def _install_plugin() -> None:
    if not (PLUGIN_SOURCE / "__init__.py").is_file():
        raise RuntimeError(f"missing staged plugin: {PLUGIN_SOURCE}")
    if not (PLUGIN_SOURCE / "plugin.yaml").is_file():
        raise RuntimeError("staged plugin has no plugin.yaml")
    staged = PLUGIN_TARGET.with_name(".mariyam_runtime_guard.fix16-new")
    if staged.exists():
        shutil.rmtree(staged)
    shutil.copytree(PLUGIN_SOURCE, staged)
    for item in staged.rglob("*"):
        if item.is_file():
            os.chmod(item, 0o600)
    if PLUGIN_TARGET.exists():
        shutil.rmtree(PLUGIN_TARGET)
    os.replace(staged, PLUGIN_TARGET)


def main() -> int:
    if os.geteuid() == 0:
        raise RuntimeError("run as timeagent, not root")
    if not PROFILE.is_dir():
        raise RuntimeError(f"missing profile: {PROFILE}")
    backup = _backup()
    _install_plugin()
    _patch_config()
    env_cleaned = _clean_env_command_prefix()
    removed_pools = _clean_auth()
    tmp_removed = False
    if TMP_CACHE.is_file() and not TMP_CACHE.is_symlink():
        TMP_CACHE.unlink()
        tmp_removed = True

    for path in (CONFIG, ENV_FILE, AUTH):
        os.chmod(path, 0o600)
    print(f"backup={backup}")
    print(f"env_command_prefix_removed={str(env_cleaned).lower()}")
    print("auth_pools_removed=" + (",".join(removed_pools) or "none"))
    print(f"tmp_cache_removed={str(tmp_removed).lower()}")
    print("plugin_installed=mariyam_runtime_guard")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
