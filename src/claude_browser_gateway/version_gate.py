"""Version gate: the gateway is tied to claude.ai's DOM and API.

On startup, the gateway fingerprints the page it depends on and compares it
against the last known-good fingerprint. If they differ, it warns and refuses
to run until the operator acknowledges or upgrades the gateway.

This is the contract that protects the gateway from silent breakage when
claude.ai changes its UI.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .auth import SELECTORS


# The set of selectors the gateway depends on. If claude.ai changes its DOM,
# at least one of these will break — that is the version-gate trigger.
CRITICAL_SELECTORS = list(SELECTORS.values())


@dataclass
class VersionGate:
    fingerprint_file: Path
    known_fingerprint: str = ""
    current_fingerprint: str = ""

    def __post_init__(self) -> None:
        if self.fingerprint_file.is_file():
            try:
                data = json.loads(self.fingerprint_file.read_text())
                self.known_fingerprint = data.get("known_fingerprint", "")
            except Exception:
                pass

    def fingerprint_selectors(self, page) -> str:
        """Compute a fingerprint from the page's DOM structure.

        Uses the presence and count of critical selectors as a structural
        signature. This is stable across cosmetic changes but sensitive to
        selector changes.
        """
        parts: list[str] = []
        for selector in CRITICAL_SELECTORS:
            try:
                count = page.locator(selector).count()
                parts.append(f"{selector}:{count}")
            except Exception:
                parts.append(f"{selector}:error")
        raw = "\n".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def check(self, current: str) -> bool:
        """Return True if the current fingerprint matches the known good one."""
        if not self.known_fingerprint:
            # No known fingerprint yet — record it and pass
            self.known_fingerprint = current
            self._save()
            return True
        self.current_fingerprint = current
        return current == self.known_fingerprint

    def _save(self) -> None:
        self.fingerprint_file.parent.mkdir(parents=True, exist_ok=True)
        self.fingerprint_file.write_text(json.dumps({
            "known_fingerprint": self.known_fingerprint,
        }))

    def acknowledge(self) -> None:
        """Accept the current fingerprint as the new known-good."""
        self.known_fingerprint = self.current_fingerprint
        self._save()