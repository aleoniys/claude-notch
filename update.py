"""Updates from GitHub. Checks version.json once a day; installs only when the user clicks Update."""
import io
import json
import shutil
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = "aleoniys/claude-notch"
BRANCH = "main"
HERE = Path(__file__).resolve().parent
KEEP = {"config.json", "notch.log", ".update-check"}          # never overwritten
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def local_version():
    try:
        return json.loads((HERE / "version.json").read_text(encoding="utf-8"))["version"]
    except Exception:
        return "0.0.0"


def _num(v):
    return tuple(int(x) for x in str(v).split(".") if x.isdigit())


def _get(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "claude-notch-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def check(force=False):
    """Newer version string, or None. Network at most once a day unless forced."""
    stamp = HERE / ".update-check"
    try:
        cached = json.loads(stamp.read_text(encoding="utf-8"))
    except Exception:
        cached = {}
    if not force and time.time() - cached.get("at", 0) < 86400:
        latest = cached.get("latest")
    else:
        try:
            latest = json.loads(_get(f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/version.json"))["version"]
        except Exception:
            return None
        stamp.write_text(json.dumps({"at": time.time(), "latest": latest}), encoding="utf-8")
    return latest if latest and _num(latest) > _num(local_version()) else None


def apply():
    """Bring the files up to date. Git checkout: git pull. Otherwise: the branch ZIP from GitHub."""
    git = shutil.which("git")
    if (HERE / ".git").exists() and git:
        r = subprocess.run([git, "-C", str(HERE), "pull", "--ff-only"], capture_output=True, text=True,
                           timeout=120, creationflags=NO_WINDOW)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or r.stdout.strip())
    else:
        data = _get(f"https://codeload.github.com/{REPO}/zip/refs/heads/{BRANCH}", timeout=60)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                parts = Path(info.filename).parts[1:]          # drop "claude-notch-main/"
                if not parts or info.is_dir() or parts[0] in KEEP or parts[0].startswith("custom-icon"):
                    continue
                target = HERE.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(info))
    (HERE / ".update-check").unlink(missing_ok=True)
    req = HERE / "requirements.txt"
    exe = Path(shutil.which("python") or "python")
    subprocess.run([str(exe), "-m", "pip", "install", "--user", "-q", "-r", str(req)],
                   capture_output=True, timeout=300, creationflags=NO_WINDOW)
