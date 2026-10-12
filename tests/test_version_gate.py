"""Tests for the version gate."""

import json
import tempfile
from pathlib import Path

from claude_browser_gateway.version_gate import VersionGate


def test_no_known_fingerprint_records_and_passes():
    with tempfile.TemporaryDirectory() as tmp:
        gate = VersionGate(fingerprint_file=Path(tmp) / "fp.json")
        assert gate.check("abc123") is True
        assert gate.known_fingerprint == "abc123"
        data = json.loads((Path(tmp) / "fp.json").read_text())
        assert data["known_fingerprint"] == "abc123"


def test_matching_fingerprint_passes():
    with tempfile.TemporaryDirectory() as tmp:
        fp = Path(tmp) / "fp.json"
        fp.write_text(json.dumps({"known_fingerprint": "deadbeef"}))
        gate = VersionGate(fingerprint_file=fp)
        assert gate.check("deadbeef") is True


def test_mismatched_fingerprint_fails():
    with tempfile.TemporaryDirectory() as tmp:
        fp = Path(tmp) / "fp.json"
        fp.write_text(json.dumps({"known_fingerprint": "deadbeef"}))
        gate = VersionGate(fingerprint_file=fp)
        assert gate.check("different") is False
        assert gate.current_fingerprint == "different"


def test_acknowledge_accepts_current():
    with tempfile.TemporaryDirectory() as tmp:
        fp = Path(tmp) / "fp.json"
        fp.write_text(json.dumps({"known_fingerprint": "old"}))
        gate = VersionGate(fingerprint_file=fp)
        gate.check("new")
        assert gate.known_fingerprint == "old"
        gate.acknowledge()
        assert gate.known_fingerprint == "new"
        data = json.loads(fp.read_text())
        assert data["known_fingerprint"] == "new"