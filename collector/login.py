#!/usr/bin/env python3
"""Интерактивный разовый логин в Apple. Запускать РУКАМИ на сервере — пароль
вводится с клавиатуры (getpass) и в конфиг/репу не попадает; кэш-сессия
сохраняется в data/ (в .gitignore).

  python collector/login.py apple   # iCloud web-сессия для устройств (pyicloud)
  python collector/login.py tags    # аккаунт FindMy.py для меток (AirTag/DIY)

После успешного логина hub.py работает на кэш-сессии; заново нужно только когда
Apple её протухнет.
"""
from __future__ import annotations

import getpass
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _cfg() -> dict:
    p = ROOT / "collector" / "config.json"
    if not p.exists():
        p = ROOT / "collector" / "config.example.json"
    return json.loads(p.read_text())


def _resolve(p: str) -> str:
    pp = Path(p)
    return str(pp if pp.is_absolute() else ROOT / pp)


def login_apple() -> int:
    from pyicloud import PyiCloudService

    ic = _cfg().get("sources", {}).get("icloud", {})
    apple_id = ic.get("appleId") or input("Apple ID (email): ").strip()
    session_dir = _resolve(ic.get("sessionDir") or "data/icloud-session")
    Path(session_dir).mkdir(parents=True, exist_ok=True)

    password = ic.get("applePassword") or getpass.getpass(f"Пароль для {apple_id}: ")
    api = PyiCloudService(apple_id, password, cookie_directory=session_dir)

    if getattr(api, "requires_2fa", False):
        code = input("Код 2FA (с доверенного устройства): ").strip()
        if not api.validate_2fa_code(code):
            print("✗ код не принят", file=sys.stderr)
            return 1
        if not api.is_trusted_session:
            api.trust_session()
    elif getattr(api, "requires_2sa", False):
        devs = api.trusted_devices
        for i, d in enumerate(devs):
            print(f"{i}: {d.get('deviceName', d.get('phoneNumber', d))}")
        d = devs[int(input("Устройство? > "))]
        api.send_verification_code(d)
        code = input("Код: ").strip()
        if not api.validate_verification_code(d, code):
            print("✗ код не принят", file=sys.stderr)
            return 1

    n = len(list(api.devices))
    print(f"✓ iCloud ок, сессия в {session_dir}. Видно устройств: {n}")
    return 0


def login_tags() -> int:
    from findmy import (
        AppleAccount, LocalAnisetteProvider, RemoteAnisetteProvider, LoginState,
        SmsSecondFactorMethod, TrustedDeviceSecondFactorMethod,
    )

    tc = _cfg().get("sources", {}).get("tags", {})
    store_path = _resolve(tc.get("accountStore") or "data/tag-account.json")
    libs = _resolve(tc.get("anisetteLibs") or "data/ani_libs.bin")
    url = tc.get("anisetteUrl")
    Path(store_path).parent.mkdir(parents=True, exist_ok=True)

    ani = RemoteAnisetteProvider(url) if url else LocalAnisetteProvider(libs_path=libs)
    acc = AppleAccount(ani)

    email = input("Apple ID (email): ").strip()
    password = getpass.getpass("Пароль: ")
    state = acc.login(email, password)

    if state == LoginState.REQUIRE_2FA:
        methods = acc.get_2fa_methods()
        for i, m in enumerate(methods):
            if isinstance(m, TrustedDeviceSecondFactorMethod):
                print(f"{i}: доверенное устройство")
            elif isinstance(m, SmsSecondFactorMethod):
                print(f"{i}: SMS ({m.phone_number})")
        m = methods[int(input("Метод? > "))]
        m.request()
        m.submit(input("Код? > ").strip())

    acc.to_json(store_path)
    print(f"✓ FindMy аккаунт ок: {acc.account_name}. Сессия в {store_path}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in ("apple", "tags"):
        print(__doc__)
        return 2
    return login_apple() if argv[1] == "apple" else login_tags()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
