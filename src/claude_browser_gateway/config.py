"""Configuration for claude-browser-gateway."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    host: str = "127.0.0.1"
    port: int = 8315
    session_dir: Path = field(
        default_factory=lambda: Path.home() / ".claude-browser-gateway"
    )
    session_file: Path = field(default_factory=lambda: Path("session.json"))
    claude_url: str = "https://claude.ai/"
    probe_interval: float = 300.0
    request_timeout: float = 120.0
    max_concurrent: int = 4
    headless: bool = False
    user_data_dir: Path | None = None

    @property
    def session_path(self) -> Path:
        return self.session_dir / self.session_file

    @property
    def storage_state_path(self) -> Path:
        return self.session_dir / "storage_state.json"

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from environment variables (all optional)."""
        kwargs: dict = {}
        if v := os.environ.get("CBG_HOST"):
            kwargs["host"] = v
        if v := os.environ.get("CBG_PORT"):
            kwargs["port"] = int(v)
        if v := os.environ.get("CBG_SESSION_DIR"):
            kwargs["session_dir"] = Path(v)
        if v := os.environ.get("CBG_CLAUDE_URL"):
            kwargs["claude_url"] = v
        if v := os.environ.get("CBG_PROBE_INTERVAL"):
            kwargs["probe_interval"] = float(v)
        if v := os.environ.get("CBG_REQUEST_TIMEOUT"):
            kwargs["request_timeout"] = float(v)
        if v := os.environ.get("CBG_MAX_CONCURRENT"):
            kwargs["max_concurrent"] = int(v)
        if v := os.environ.get("CBG_HEADLESS"):
            kwargs["headless"] = v.lower() in {"1", "true", "yes"}
        return cls(**kwargs)