#!/usr/bin/env python3
"""findmy-zoo hub: опрашивает источники в фоне, копит точки в SQLite (окно retentionH)
и раздаёт статику + /api/points. Один процесс, только stdlib для HTTP.
Запуск: python collector/hub.py (WorkingDirectory = корень репо)."""
from __future__ import annotations

import json
import logging
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CFG_PATH = ROOT / "collector" / "config.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("hub")


def load_cfg() -> dict:
    return json.loads(CFG_PATH.read_text())


def _resolve(p: str) -> str:
    pp = Path(p)
    return str(pp if pp.is_absolute() else ROOT / pp)


def build_sources(cfg: dict):
    from sources import IcloudSource, TagSource

    out = []
    s = cfg.get("sources", {})

    t = s.get("tags", {})
    if t.get("enabled"):
        tc = dict(t)
        for k in ("accountStore", "anisetteLibs"):
            if tc.get(k):
                tc[k] = _resolve(tc[k])
        tc["accessories"] = [
            {**a, "file": _resolve(a["file"])} if a.get("file") else a
            for a in tc.get("accessories", [])
        ]
        out.append(("tags", TagSource(tc, DATA)))

    ic = s.get("icloud", {})
    if ic.get("enabled"):
        icc = dict(ic)
        if icc.get("sessionDir"):
            icc["sessionDir"] = _resolve(icc["sessionDir"])
        out.append(("icloud", IcloudSource(icc, DATA)))

    return out


def poller(name: str, src, store, interval: int, retention_s: int):
    while True:
        try:
            added = src.poll(store)
            store.prune(time.time() - retention_s)
            log.info("poll %s: +%d точек", name, added)
        except Exception as e:
            log.warning("poll %s упал: %s", name, e)
        time.sleep(interval)


def make_handler(store, cfg):
    retention_s = int(cfg.get("retentionH", 24)) * 3600

    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(ROOT), **k)

        def log_message(self, *a):
            pass

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            # секреты наружу не отдаём
            if path.startswith("/collector") or path.startswith("/data"):
                self.send_error(404)
                return
            if path == "/api/points":
                body = json.dumps({
                    "generated": int(time.time()),
                    "retentionH": cfg.get("retentionH", 24),
                    "colors": cfg.get("colors", {}),
                    "names": cfg.get("names", {}),
                    "entities": store.entities(time.time() - retention_s),
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

    return H


def main() -> int:
    cfg = load_cfg()
    from store import Store

    store = Store(DATA / "history.db")
    retention_s = int(cfg.get("retentionH", 24)) * 3600

    sources = build_sources(cfg)
    if not sources:
        log.warning("нет включённых источников — правь collector/config.json")
    for name, src in sources:
        interval = int(cfg["sources"][name].get("pollEveryS", 300))
        threading.Thread(target=poller, args=(name, src, store, interval, retention_s), daemon=True).start()
        log.info("источник %s: опрос каждые %dс", name, interval)

    port = int(cfg.get("port", 8815))
    httpd = ThreadingHTTPServer(("0.0.0.0", port), make_handler(store, cfg))
    log.info("карта на http://0.0.0.0:%d", port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
