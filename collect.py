"""Reads Claude Code's local files and returns what the widget shows. Nothing leaves the PC."""
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
CLAUDE = HOME / ".claude"
PROJECTS = CLAUDE / "projects"
STATE = HOME / ".claude.json"

MODEL_NAMES = {"opus": "Opus", "sonnet": "Sonnet", "haiku": "Haiku", "fable": "Fable"}


def model_name(raw):
    if not raw:
        return "—"
    s = str(raw).lower().replace("claude-", "")
    for key, name in MODEL_NAMES.items():
        if key in s:
            ver = s.split(key)[-1].strip("-").split("[")[0].replace("-", ".")
            return f"{name} {ver}".strip()
    return str(raw)


def _ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _tokens(u):
    return (u.get("input_tokens") or 0) + (u.get("output_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)


class TodayIndex:
    """Today's token totals, read incrementally so the 100 MB logs are parsed once."""

    def __init__(self):
        self.day = None
        self.offsets = {}
        self.seen = set()
        self.tokens = 0
        self.cache_read = 0
        self.sessions = set()

    def update(self):
        today = datetime.now().date()
        if today != self.day:
            self.__init__()
            self.day = today
        midnight = datetime.combine(today, datetime.min.time()).timestamp()
        for f in PROJECTS.glob("*/**/*.jsonl"):
            try:
                st = f.stat()
            except OSError:
                continue
            if st.st_mtime < midnight:
                continue
            off = self.offsets.get(f, 0)
            if st.st_size < off:
                off = 0
            if st.st_size == off:
                continue
            with f.open("rb") as fh:
                fh.seek(off)
                data = fh.read()
            cut = data.rfind(b"\n") + 1
            self.offsets[f] = off + cut
            for line in data[:cut].splitlines():
                if b'"usage"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                m = d.get("message") or {}
                u = m.get("usage") if isinstance(m, dict) else None
                if not u or _ts(d.get("timestamp", "")) < midnight:
                    continue
                key = (m.get("id"), d.get("requestId"))
                if key in self.seen:
                    continue
                self.seen.add(key)
                self.tokens += _tokens(u)
                self.cache_read += u.get("cache_read_input_tokens") or 0
                if "subagents" not in f.parts:
                    self.sessions.add(f.stem)


def _tail_entries(path, size=600_000):
    with path.open("rb") as fh:
        fh.seek(0, 2)
        end = fh.tell()
        start = max(0, end - size)
        fh.seek(start)
        data = fh.read()
    out = []
    for line in data.splitlines()[1 if start else 0:]:   # the first line is partial only when we started mid-file
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def _activity(entries):
    """What Claude is doing right now, in a few words."""
    for d in reversed(entries):
        t = d.get("type")
        if t == "user":
            c = (d.get("message") or {}).get("content")
            if isinstance(c, str) or (isinstance(c, list) and any(x.get("type") == "text" for x in c if isinstance(x, dict))):
                return {"kind": "think", "text": ""}
            continue
        if t != "assistant":
            continue
        content = (d.get("message") or {}).get("content") or []
        for block in reversed(content):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                inp = block.get("input") or {}
                name = block.get("name", "")
                detail = inp.get("description") or inp.get("file_path") or inp.get("pattern") or inp.get("query") or inp.get("skill") or ""
                if isinstance(detail, str) and ("\\" in detail or "/" in detail) and len(detail) > 30:
                    detail = Path(detail).name
                return {"kind": "tool", "tool": name, "text": str(detail)[:90]}
            if block.get("type") == "text" and block.get("text", "").strip():
                return {"kind": "text", "text": block["text"].strip().splitlines()[0][:90]}
    return {"kind": "idle", "text": ""}


def _branch(cwd, fallback):
    try:
        r = subprocess.run(["git", "-C", cwd, "branch", "--show-current"], capture_output=True, text=True, timeout=2,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout.strip() or fallback
    except Exception:
        return fallback


def _agents(session_dir):
    out = []
    sub = session_dir / "subagents"
    if not sub.is_dir():
        return out
    for meta in sorted(sub.glob("*.meta.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:6]:
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
        except Exception:
            continue
        log = meta.with_name(meta.name.replace(".meta.json", ".jsonl"))
        tokens, first, last, seen, used_model = 0, 0, 0, set(), ""
        if log.exists():
            for line in log.open("rb"):
                if b'"timestamp"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                ts = _ts(d.get("timestamp", ""))
                first = first or ts
                last = max(last, ts)
                msg = d.get("message") or {}
                u = msg.get("usage") if isinstance(msg, dict) else None
                if u and (msg.get("id"), d.get("requestId")) not in seen:
                    seen.add((msg.get("id"), d.get("requestId")))
                    used_model = msg.get("model") or used_model
                    tokens += _tokens(u) + (u.get("cache_read_input_tokens") or 0)
        mtime = log.stat().st_mtime if log.exists() else meta.stat().st_mtime
        running = not m.get("finished") and time.time() - mtime < 900
        out.append({
            "name": m.get("description") or m.get("agentType") or "agent",
            "type": m.get("agentType", ""),
            "model": model_name(used_model or m.get("model")),   # the model that actually answered
            "running": running,
            "tokens": tokens,
            "seconds": int((time.time() if running else last) - first) if first else 0,
            "ago": int(time.time() - mtime),
        })
    return out


def _installed(cwd, state):
    skills = sorted(p.name for p in (CLAUDE / "skills").glob("*") if p.is_dir() and not p.name.startswith(".") and p.name != "synced")
    plugins = []
    try:
        ip = json.loads((CLAUDE / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        for name, rows in (ip.get("plugins") or {}).items():
            plugins.append(f"{name.split('@')[0]} {rows[0].get('version', '')}".strip())
    except Exception:
        pass
    mcp = set((state.get("mcpServers") or {}).keys())
    if cwd:
        want = cwd.replace("\\", "/").lower().rstrip("/")
        for p, v in (state.get("projects") or {}).items():
            if p.replace("\\", "/").lower().rstrip("/") == want:
                mcp |= set((v.get("mcpServers") or {}).keys())
    agents = set(p.stem for p in (CLAUDE / "agents").glob("*.md"))
    if cwd:
        agents |= set(p.stem for p in (Path(cwd) / ".claude" / "agents").glob("*.md"))
    return {"skills": skills, "plugins": plugins, "mcp": sorted(mcp), "agents": sorted(agents)}


def _limits(state):
    u = state.get("cachedUsageUtilization") or {}
    util = u.get("utilization") or {}

    def one(key):
        v = util.get(key) or {}
        if v.get("utilization") is None:
            return None
        return {"pct": v["utilization"], "resets": _ts(v.get("resets_at") or "")}

    return {"five": one("five_hour"), "week": one("seven_day"), "fetched": (u.get("fetchedAtMs") or 0) / 1000}


_today = TodayIndex()


def collect():
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    # Only these keys are used; the login token in the same file is never read further.
    state = {k: state.get(k) for k in ("cachedUsageUtilization", "mcpServers", "projects")}
    try:
        _today.update()
    except Exception:
        pass

    mains = [p for p in PROJECTS.glob("*/*.jsonl")]
    active = max(mains, key=lambda p: p.stat().st_mtime) if mains else None
    session = {}
    if active:
        entries = _tail_entries(active)
        cwd = next((d.get("cwd") for d in reversed(entries) if d.get("cwd")), "")
        model = next((m.get("model") for d in reversed(entries)
                      if d.get("type") == "assistant" and not d.get("isSidechain")
                      for m in [d.get("message") or {}] if m.get("model")), "")
        ctx = 0
        for d in reversed(entries):
            m = d.get("message") or {}
            if d.get("type") == "assistant" and not d.get("isSidechain") and isinstance(m, dict) and m.get("usage"):
                u = m["usage"]
                ctx = (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
                break
        window = 1_000_000 if ctx > 200_000 or "[1m]" in str(model) else 200_000
        idle = time.time() - active.stat().st_mtime
        # The turn is over when the last real main-thread message is Claude's with stop_reason end_turn.
        # Opening or resuming a session writes title/mode records and local-command output; they are not work,
        # so the age of the last real message decides, not the file's modified time.
        turn_done, last_ts = False, 0.0
        for d in reversed(entries):
            if d.get("isSidechain") or d.get("isMeta") or d.get("type") not in ("assistant", "user"):
                continue
            m = d.get("message") or {}
            c = m.get("content") if isinstance(m, dict) else None
            if isinstance(c, str) and c.lstrip().startswith(("<local-command", "<command-")):
                continue
            turn_done = d.get("type") == "assistant" and m.get("stop_reason") == "end_turn"
            last_ts = _ts(d.get("timestamp", ""))
            break
        since = time.time() - last_ts if last_ts else 1e9   # no real message yet: nothing is running
        if idle >= 1800:
            status = "sleeping"
        elif turn_done or since >= 300:
            status = "waiting"
        else:
            status = "working"
        cwd_path = Path(cwd) if cwd else None
        session = {
            "project": cwd_path.name if cwd_path else active.parent.name,
            "parent": cwd_path.parent.name if cwd_path else "",
            "cwd": cwd,
            "branch": _branch(cwd, next((d.get("gitBranch") for d in reversed(entries) if d.get("gitBranch")), "")) if cwd else "",
            "model": model_name(model),
            "context": ctx,
            "window": window,
            "status": status,
            "idle": int(idle),
            "activity": _activity(entries) if status == "working" else {"kind": "idle", "text": ""},
            "agents": _agents(active.with_suffix("")),
        }
    return {
        "now": time.time(),
        "limits": _limits(state),
        "session": session,
        "today": {"tokens": _today.tokens, "cache_read": _today.cache_read, "sessions": len(_today.sessions)},
        "installed": _installed(session.get("cwd"), state),
    }


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, indent=1))
