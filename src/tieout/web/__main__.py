"""Launch the tieout web UI:  python -m tieout.web   ->  http://localhost:8000

  --precompute   analyze the demo filings and cache them, then exit
  --port N       serve on a different port
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import service


def _load_env() -> None:
    """Make live runs work out of the box: if ANTHROPIC_API_KEY isn't already
    set, load it from ./.env or the out-of-repo credentials file."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    candidates = [Path(".env"),
                  Path(os.environ.get("LOCALAPPDATA", "")) / "tieout" / "credentials.env"]
    for p in candidates:
        try:
            if p and p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())
        except Exception:
            pass


def main() -> None:
    _load_env()
    if "--precompute" in sys.argv:
        for f in service.filings_index():
            print(f"analyzing {f['ticker']} ...", flush=True)
            service.analyze(f["ticker"], force=True)
        print("done.")
        return

    port = 8000
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])

    import uvicorn
    print(f"tieout UI -> http://localhost:{port}")
    uvicorn.run("tieout.web.app:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
