"""Self-check for the status logic: python test_collect.py"""
import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import collect


def iso(sec_ago):
    return datetime.fromtimestamp(time.time() - sec_ago, timezone.utc).isoformat().replace("+00:00", "Z")


def status(entries):
    root = Path(tempfile.mkdtemp())
    (root / "proj").mkdir()
    (root / "proj" / "s.jsonl").write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    collect.PROJECTS = root
    return collect.collect()["session"]["status"]


done = {"type": "assistant", "timestamp": iso(900), "message": {"role": "assistant", "stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]}}
# Resuming a finished session writes records and command output: still waiting, not "thinking".
assert status([done, {"type": "user", "timestamp": iso(5), "message": {"content": "<local-command-stdout>Compacted</local-command-stdout>"}},
               {"type": "ai-title"}, {"type": "mode"}]) == "waiting"
# A fresh prompt with no answer yet: working.
assert status([done, {"type": "user", "timestamp": iso(5), "message": {"content": "hi"}}]) == "working"
# A prompt left unanswered for 10 minutes (e.g. interrupted): not working any more.
assert status([done, {"type": "user", "timestamp": iso(600), "message": {"content": "hi"}}, {"type": "mode"}]) == "waiting"
print("ok")
