"""SQLite-хранилище точек трека. Одна строка = одна геопозиция сущности в момент ts.

Дедуп по (entity_id, ts): один и тот же отчёт Apple, полученный повторно, не плодит строки.
Скользящее окно держим prune() — старше retentionH удаляется.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

_LOCK = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS points (
  entity_id TEXT NOT NULL,
  kind      TEXT NOT NULL,
  name      TEXT,
  lat       REAL NOT NULL,
  lon       REAL NOT NULL,
  ts        INTEGER NOT NULL,
  accuracy  REAL,
  battery   REAL,
  extra     TEXT,
  PRIMARY KEY (entity_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_points_ts ON points(ts);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def add(self, entity_id, kind, name, lat, lon, ts, accuracy=None, battery=None, extra=None) -> bool:
        """Добавляет точку. Возвращает True, если она новая (ещё не было такой ts у сущности)."""
        with _LOCK, self._conn() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO points"
                "(entity_id,kind,name,lat,lon,ts,accuracy,battery,extra) VALUES(?,?,?,?,?,?,?,?,?)",
                (entity_id, kind, name, float(lat), float(lon), int(ts),
                 accuracy, battery, json.dumps(extra) if extra else None),
            )
            return cur.rowcount > 0

    def prune(self, older_than_ts: float) -> int:
        with _LOCK, self._conn() as c:
            cur = c.execute("DELETE FROM points WHERE ts < ?", (int(older_than_ts),))
            return cur.rowcount

    def entities(self, since_ts: float) -> list[dict]:
        """Все сущности с их точками за окно [since_ts, now], точки по возрастанию ts."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM points WHERE ts >= ? ORDER BY entity_id, ts",
                (int(since_ts),),
            ).fetchall()
        out: dict[str, dict] = {}
        for r in rows:
            e = out.setdefault(r["entity_id"], {
                "id": r["entity_id"], "kind": r["kind"], "name": r["name"], "points": [],
            })
            if r["name"]:
                e["name"] = r["name"]
            e["points"].append({
                "lat": r["lat"], "lon": r["lon"], "ts": r["ts"],
                "acc": r["accuracy"], "batt": r["battery"],
            })
        return list(out.values())
