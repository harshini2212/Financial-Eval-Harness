"""Launch the tieout web UI:  python -m tieout.web   ->  http://localhost:8000

  --precompute   analyze the demo filings and cache them, then exit
  --port N       serve on a different port
"""

from __future__ import annotations

import os
import sys

from . import service


def main() -> None:
    # service import already attempted to load the key; report the result clearly.
    has_key = service.load_api_key()
    if has_key:
        print("[tieout] ANTHROPIC_API_KEY loaded — live company runs enabled.")
    else:
        print("[tieout] No ANTHROPIC_API_KEY found — cached filings work, but "
              "live runs are disabled. Set the key or use run.ps1.")

    if "--precompute" in sys.argv:
        for f in service.filings_index():
            print(f"analyzing {f['ticker']} ...", flush=True)
            service.analyze(f["ticker"], force=True)
        print("done.")
        return

    # Port: --port flag, else the platform's $PORT (Render/Railway), else 8000.
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    else:
        port = int(os.environ.get("PORT", 8000))
    # Bind all interfaces when deployed (PORT set by the host); localhost otherwise.
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"

    import uvicorn
    print(f"tieout UI -> http://{host}:{port}")
    uvicorn.run("tieout.web.app:app", host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
