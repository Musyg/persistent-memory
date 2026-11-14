"""Stand-ins used only when Hermes Agent is not importable.

The provider normally runs inside Hermes Agent and uses its MemoryProvider base class,
RecallStatus record, trivial-prompt check and tool_error helper. These minimal local
equivalents let the package import, and its tests run, in an environment without Hermes
Agent (plain library use, this repository's installed-distribution checks).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

HERMES_AGENT_AVAILABLE = False


class MemoryProvider:
    """Empty base: Hermes Agent's real ABC replaces it when Hermes Agent is installed."""

    pre_compress_checkpoint_api_version = 1


@dataclass(frozen=True)
class RecallStatus:
    provider_label: str
    count: int
    glyph: str = "*"


_TRIVIAL = re.compile(
    r"^(yes|no|ok|okay|sure|thanks|thank you|hi|hello|hey|continue|go ahead|done|next|lgtm)[\s!?.,:;]*$",
    re.IGNORECASE,
)


def is_trivial_prompt(text: str | None) -> bool:
    stripped = (text or "").strip()
    return not stripped or stripped.startswith("/") or bool(_TRIVIAL.match(stripped))


def tool_error(message: object, **extra: object) -> str:
    return json.dumps({"error": str(message)[:500], **extra}, ensure_ascii=False)
