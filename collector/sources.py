"""Источники геопозиции. Каждый умеет poll(store) — подтянуть текущие/исторические
точки и сложить их в SQLite. Импорты тяжёлых либ — внутри методов, чтобы отсутствие
одной либы не ломало другой источник.

Слои:
  TagSource    — AirTag'и и DIY-метки (OpenHaystack) через FindMy.py (+ anisette).
                 Единственный слой с настоящей историей: fetch_location_history().
  IcloudSource — устройства из Find My (iPhone/Mac/Watch/AirPods) через pyicloud.
                 Apple отдаёт только ТЕКУЩУЮ точку — трек копится нашими опросами.

Слоя «люди» (Find My Friends) здесь нет намеренно: в поддерживаемых открытых
библиотеках 2026 он недоступен. См. README.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("sources")


def _epoch(dt) -> int:
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    return int(dt)


# грубый уровень батарейки метки из статус-байта FindMy (старшие 2 бита)
_BATT_PCT = {0b00: 100, 0b01: 60, 0b10: 30, 0b11: 10}


def _tag_battery(status: int):
    try:
        return _BATT_PCT.get((int(status) >> 6) & 0b11)
    except Exception:
        return None


class TagSource:
    """AirTag'и / DIY-метки OpenHaystack через FindMy.py."""

    kind = "tag"

    def __init__(self, cfg: dict, data_dir):
        self.cfg = cfg
        self.data_dir = Path(data_dir)
        self.store_path = cfg.get("accountStore") or str(self.data_dir / "tag-account.json")
        self.anisette_url = cfg.get("anisetteUrl")  # None => встроенный локальный генератор
        self.anisette_libs = cfg.get("anisetteLibs") or str(self.data_dir / "ani_libs.bin")
        self.accessories = cfg.get("accessories", [])
        self._acc = None
        self._items = None  # [(name, obj)]

    def _account(self):
        from findmy import AppleAccount
        if self._acc is None:
            self._acc = AppleAccount.from_json(self.store_path, anisette_libs_path=self.anisette_libs)
        return self._acc

    def _load_items(self):
        from findmy import FindMyAccessory, KeyPair
        items = []
        for a in self.accessories:
            name = a.get("name") or a.get("file") or "tag"
            if a.get("file"):
                items.append((name, FindMyAccessory.from_json(a["file"])))
            elif a.get("b64key"):
                items.append((name, KeyPair.from_b64(a["b64key"])))
            else:
                log.warning("tag %s: нет ни file, ни b64key — пропуск", name)
        return items

    def poll(self, store) -> int:
        acc = self._account()
        if self._items is None:
            self._items = self._load_items()
        added = 0
        for name, obj in self._items:
            try:
                history = acc.fetch_location_history(obj)  # list[LocationReport]
            except Exception as e:
                log.warning("tag %s: fetch failed: %s", name, e)
                continue
            eid = f"tag:{name}"
            for rep in history or []:
                try:
                    if store.add(eid, self.kind, name,
                                 float(rep.latitude), float(rep.longitude), _epoch(rep.timestamp),
                                 accuracy=getattr(rep, "horizontal_accuracy", None),
                                 battery=_tag_battery(getattr(rep, "status", 0))):
                        added += 1
                except Exception as e:
                    log.debug("tag %s: битый отчёт: %s", name, e)
        try:
            acc.to_json(self.store_path)  # сессия ротируется — сохраняем
        except Exception:
            pass
        return added


class IcloudSource:
    """Устройства из Find My через iCloud web API (pyicloud)."""

    kind = "device"

    def __init__(self, cfg: dict, data_dir):
        self.cfg = cfg
        self.data_dir = Path(data_dir)
        self.session_dir = cfg.get("sessionDir") or str(self.data_dir / "icloud-session")
        self.apple_id = cfg.get("appleId")
        self.password = cfg.get("applePassword") or ""
        self.want_devices = cfg.get("devices", True)
        self._api = None

    def _connect(self):
        from pyicloud import PyiCloudService
        Path(self.session_dir).mkdir(parents=True, exist_ok=True)
        api = PyiCloudService(self.apple_id, self.password, cookie_directory=self.session_dir)
        if getattr(api, "requires_2fa", False) or getattr(api, "requires_2sa", False):
            raise RuntimeError("iCloud требует 2FA — выполни: python collector/login.py apple")
        return api

    def poll(self, store) -> int:
        if self._api is None:
            self._api = self._connect()
        added = 0
        if self.want_devices:
            for dev in self._api.devices:
                try:
                    loc = dev.location()
                except Exception as e:
                    log.debug("device loc err: %s", e)
                    loc = None
                if not loc or loc.get("latitude") is None:
                    continue
                content = getattr(dev, "content", {}) or {}
                name = content.get("name") or content.get("deviceDisplayName") or str(content.get("id"))
                ts = loc.get("timeStamp") or loc.get("timestamp") or time.time() * 1000
                ts = ts / 1000 if ts > 1e12 else ts  # мс -> с
                batt = content.get("batteryLevel")
                if isinstance(batt, (int, float)) and batt <= 1:
                    batt = round(batt * 100)
                if store.add(f"dev:{name}", self.kind, name,
                             float(loc["latitude"]), float(loc["longitude"]), int(ts),
                             accuracy=loc.get("horizontalAccuracy"), battery=batt):
                    added += 1
        return added
