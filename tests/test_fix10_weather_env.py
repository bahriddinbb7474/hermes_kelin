"""fix10 regression: the gateway must pass private profile env to MCP children."""
import importlib.util
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "deploy" / "hermes-gateway-mariyam_oyijon.service"
DROP_IN = (
    ROOT
    / "deploy"
    / "hermes-gateway-mariyam_oyijon.service.d"
    / "10-profile-env.conf"
)
PATCHER = ROOT / "deploy" / "fix10_patch_mcp_env.py"


def _patcher_module():
    spec = importlib.util.spec_from_file_location("fix10_patch_mcp_env", PATCHER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_family_gateway_loads_private_profile_environment():
    unit_text = UNIT.read_text(encoding="utf-8")
    text = DROP_IN.read_text(encoding="utf-8")
    expected = (
        "EnvironmentFile=/home/timeagent/.hermes/profiles/"
        "mariyam_oyijon/.env"
    )
    assert text.count(expected) == 1
    assert "[Service]" in text
    assert "OPENWEATHER_API_KEY=" not in text
    assert expected not in unit_text  # Hermes may regenerate the main unit.


def test_mcp_openweather_placeholder_patch_is_narrow_and_idempotent(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "model: gpt-5.6-luna\n"
        "mcp_servers:\n"
        "  mariyam_backend:\n"
        "    command: python\n"
        "    env:\n"
        "      PYTHONPATH: /opt/hermes-mariyam\n"
        "      DATABASE_URL: ${DATABASE_URL}\n"
        "session_reset:\n"
        "  mode: daily\n",
        encoding="utf-8",
    )
    patcher = _patcher_module()
    assert patcher.patch_config(config) is True
    assert patcher.patch_config(config) is False
    value = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert value["mcp_servers"]["mariyam_backend"]["env"]["OPENWEATHER_API_KEY"] == (
        "${OPENWEATHER_API_KEY}"
    )
    assert value["model"] == "gpt-5.6-luna"
    assert value["session_reset"] == {"mode": "daily"}
