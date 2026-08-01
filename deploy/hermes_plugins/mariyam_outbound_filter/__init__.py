"""Outbound status hygiene for the Mariyam profile.

Root cause (live, 2026-08-01 02:27, profile mariyam_oyijon):
  ``agent/chat_completion_helpers.py`` records a one-shot notice when the
  primary model is swapped for a fallback provider::

      🔄 Switched to fallback model: <old> via <old_provider> → <new> via <new_provider>

  ``run_agent.py::_emit_pending_fallback_notice`` pushes it through
  ``_emit_status`` on the successful turn, and the gateway status rail
  (``gateway/run.py::_prepare_gateway_status_message``) forwards it to chat:
  its noisy-status filter ``_TELEGRAM_NOISY_STATUS_RE`` has no pattern for a
  provider switch. Hermes exposes no config key for that notice, so an English
  line reached Oyijon, who does not read Latin script.

Fix (profile-scoped, no Hermes core edit):
  At ``register()`` time — inside the gateway process only — the status rail
  function is wrapped in-process. Everything Hermes would still deliver is
  passed through the wrapper, and any line that still carries Latin letters is
  dropped for human chat surfaces. Programmatic surfaces (``local``,
  ``api_server``, ``webhook``, ``msgraph_webhook``) keep raw diagnostics.

Scope: only the status/lifecycle rail. Assistant replies, cron deliveries and
health-guard admin messages travel other paths and are not touched.
"""

from __future__ import annotations

import logging
import re
import sys

LOG = logging.getLogger("mariyam_outbound_filter")

GATEWAY_RUN_MODULE = "gateway.run"
STATUS_FN = "_prepare_gateway_status_message"
RAW_SURFACE_FN = "_gateway_surface_passes_raw_text"
WRAPPED_FLAG = "_mariyam_outbound_filter_wrapped"

LATIN_RE = re.compile(r"[A-Za-z]")

# English framework lines observed on the status rail for this profile. Kept
# for documentation and regression tests; the runtime rule is script-based,
# not marker-based, so an unseen English string is suppressed as well.
KNOWN_ENGLISH_STATUS_MARKERS = (
    "Switched to fallback model",
    "Primary model failed — switching to fallback",
    "Interrupting current task",
    "Working —",
)

_installed = False


def should_suppress(prepared: str | None, *, raw_surface: bool) -> bool:
    """Return True when a prepared status line must not reach the chat.

    ``prepared`` is what Hermes' own filter already decided to deliver
    (``None`` means Hermes suppressed it itself). Programmatic surfaces keep
    everything; human chat surfaces lose any line containing Latin letters,
    which for this profile means every framework string — Mariyam speaks only
    Uzbek Cyrillic.
    """
    if prepared is None:
        return True
    if raw_surface:
        return False
    return bool(LATIN_RE.search(str(prepared)))


def install_status_filter() -> bool:
    """Wrap the gateway status rail in this process. Idempotent.

    Returns True once the wrapper is in place (or already was). No-op outside
    the gateway process, where ``gateway.run`` is not imported.
    """
    global _installed
    if _installed:
        return True

    module = sys.modules.get(GATEWAY_RUN_MODULE)
    if module is None:
        return False

    original = getattr(module, STATUS_FN, None)
    if original is None:
        LOG.warning(
            "mariyam_outbound_filter: %s.%s missing; status rail left untouched",
            GATEWAY_RUN_MODULE, STATUS_FN,
        )
        _installed = True
        return True
    if getattr(original, WRAPPED_FLAG, False):
        _installed = True
        return True

    raw_surface_fn = getattr(module, RAW_SURFACE_FN, None)

    def _filtered_status_message(platform, event_type, message):
        try:
            prepared = original(platform, event_type, message)
        except Exception:
            LOG.warning(
                "mariyam_outbound_filter: upstream status filter failed; "
                "dropping status (%s)", event_type, exc_info=True,
            )
            return None

        try:
            raw_surface = bool(raw_surface_fn(platform)) if raw_surface_fn else False
            if should_suppress(prepared, raw_surface=raw_surface):
                if prepared is not None:
                    LOG.info(
                        "mariyam_outbound_filter: suppressed non-Cyrillic status "
                        "(event=%s, chars=%d)", event_type, len(str(prepared)),
                    )
                return None
            return prepared
        except Exception:
            LOG.warning(
                "mariyam_outbound_filter: filter error; dropping status (%s)",
                event_type, exc_info=True,
            )
            return None

    setattr(_filtered_status_message, WRAPPED_FLAG, True)
    setattr(module, STATUS_FN, _filtered_status_message)
    _installed = True
    LOG.info("mariyam_outbound_filter: gateway status rail wrapped")
    return True


def on_pre_llm_call(**kwargs):
    """Late installation hook.

    ``register()`` runs during plugin discovery; if that happened before
    ``gateway.run`` was imported, install on the first agent turn instead.
    Returns None so no context is injected into the user message.
    """
    install_status_filter()
    return None


def register(ctx) -> None:  # pragma: no cover - exercised at runtime on VPS
    """Install the filter now if possible, otherwise on the first turn."""
    if not install_status_filter():
        ctx.register_hook("pre_llm_call", on_pre_llm_call)
