#!/usr/bin/env python3
"""Мастер первичной настройки в одну команду.

Спрашивает Apple ID + пароль + код 2FA (один раз — это защита Apple, обойти нельзя),
логинит устройства (pyicloud) и по желанию метки (FindMy.py), сам прописывает appleId
в config.json, включает/выключает слой меток и перезапускает сервис.

Пароль вводится с клавиатуры (getpass) — в конфиг/репо не пишется, остаётся только
кэш-сессия в data/. Запуск:  findmy-zoo-setup   (или .venv/bin/python collector/setup.py)
"""
from __future__ import annotations

import getpass
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "collector" / "config.json"
EXAMPLE = ROOT / "collector" / "config.example.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _resolve(p: str) -> str:
    pp = Path(p)
    return str(pp if pp.is_absolute() else ROOT / pp)


def load_cfg() -> dict:
    if not CFG.exists():
        CFG.write_text(EXAMPLE.read_text())
    return json.loads(CFG.read_text())


def save_cfg(cfg: dict) -> None:
    CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")


def yes(prompt: str, default: bool = False) -> bool:
    d = "Y/n" if default else "y/N"
    a = input(f"{prompt} [{d}] ").strip().lower()
    return default if not a else a in ("y", "yes", "д", "да")


def login_devices(cfg: dict, apple_id: str, password: str) -> bool:
    """iCloud-сессия для устройств. True при успехе."""
    from pyicloud import PyiCloudService

    ic = cfg["sources"].setdefault("icloud", {})
    session_dir = _resolve(ic.get("sessionDir") or "data/icloud-session")
    Path(session_dir).mkdir(parents=True, exist_ok=True)

    print("→ вход в iCloud (устройства)…")
    api = PyiCloudService(apple_id, password, cookie_directory=session_dir)

    if getattr(api, "requires_2fa", False):
        if not api.validate_2fa_code(input("   код 2FA (с доверенного устройства): ").strip()):
            print("   ✗ код не принят")
            return False
        if not api.is_trusted_session:
            api.trust_session()
    elif getattr(api, "requires_2sa", False):
        devs = api.trusted_devices
        for i, d in enumerate(devs):
            print(f"   {i}: {d.get('deviceName', d.get('phoneNumber', d))}")
        d = devs[int(input("   устройство? > "))]
        api.send_verification_code(d)
        if not api.validate_verification_code(d, input("   код: ").strip()):
            print("   ✗ код не принят")
            return False

    n = len(list(api.devices))
    print(f"   ✓ ок, видно устройств: {n}")
    return True


def login_tags(cfg: dict, apple_id: str, password: str) -> bool:
    """Аккаунт FindMy.py для меток. True при успехе."""
    from findmy import (
        AppleAccount, LocalAnisetteProvider, LoginState, RemoteAnisetteProvider,
        SmsSecondFactorMethod, TrustedDeviceSecondFactorMethod,
    )

    tc = cfg["sources"].setdefault("tags", {})
    store_path = _resolve(tc.get("accountStore") or "data/tag-account.json")
    libs = _resolve(tc.get("anisetteLibs") or "data/ani_libs.bin")
    url = tc.get("anisetteUrl")
    Path(store_path).parent.mkdir(parents=True, exist_ok=True)

    print("→ вход для меток (FindMy.py)…")
    ani = RemoteAnisetteProvider(url) if url else LocalAnisetteProvider(libs_path=libs)
    acc = AppleAccount(ani)
    state = acc.login(apple_id, password)

    if state == LoginState.REQUIRE_2FA:
        methods = acc.get_2fa_methods()
        for i, m in enumerate(methods):
            if isinstance(m, TrustedDeviceSecondFactorMethod):
                print(f"   {i}: доверенное устройство")
            elif isinstance(m, SmsSecondFactorMethod):
                print(f"   {i}: SMS ({m.phone_number})")
        m = methods[int(input("   метод? > "))]
        m.request()
        m.submit(input("   код? > ").strip())

    acc.to_json(store_path)
    print(f"   ✓ ок: {acc.account_name}")
    return True


def restart_service() -> None:
    try:
        r = subprocess.run(["sudo", "-n", "systemctl", "restart", "findmy-zoo"],
                           capture_output=True, timeout=30)
        if r.returncode == 0:
            print("→ сервис перезапущен.")
            return
    except Exception:
        pass
    print("→ перезапусти сервис вручную:  sudo systemctl restart findmy-zoo")


def main() -> int:
    print("=== findmy-zoo · мастер настройки ===")
    print("Пароль Apple вводится один раз, в конфиг/репо не пишется.\n")

    cfg = load_cfg()
    ic = cfg["sources"].setdefault("icloud", {})

    cur = ic.get("appleId")
    default = cur if cur and cur != "you@icloud.com" else ""
    apple_id = input(f"Apple ID (email){f' [{default}]' if default else ''}: ").strip() or default
    if not apple_id:
        print("✗ нужен Apple ID")
        return 1
    password = getpass.getpass("Пароль Apple: ")

    ok_dev = login_devices(cfg, apple_id, password)
    ic["appleId"] = apple_id
    ic["enabled"] = ok_dev or ic.get("enabled", True)

    tc = cfg["sources"].setdefault("tags", {})
    if yes("\nНастроить метки (AirTag/DIY)? нужны будут файлы ключей", default=False):
        if login_tags(cfg, apple_id, password):
            tc["enabled"] = True
            print("   положи ключи меток в data/tags/*.json и перечисли их в")
            print("   collector/config.json → sources.tags.accessories")
    else:
        tc["enabled"] = False
        print("   слой меток выключен (включишь позже — прогони мастер снова).")

    save_cfg(cfg)
    print("\n→ конфиг сохранён.")
    restart_service()

    port = cfg.get("port", 8815)
    print(f"\n✓ готово. Карта: http://<этот-сервер>:{port}")
    print("  данные устройств набегут за 1–2 цикла опроса; метки подтянут историю сразу.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nотменено.")
        raise SystemExit(130)
