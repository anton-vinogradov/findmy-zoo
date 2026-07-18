#!/usr/bin/env bash
# findmy-zoo — установка/обновление на Linux-сервере как systemd-сервис.
#
# Однострочником (публичный репо):
#   curl -fsSL https://raw.githubusercontent.com/anton-vinogradov/findmy-zoo/main/install.sh | bash
#   # или от root:  … | sudo bash
#
# Либо из клона:
#   git clone <repo> findmy-zoo && cd findmy-zoo && ./install.sh
#
# Обновление: повторить ту же команду (идемпотентно; git pull делается сам).
#
# ВАЖНО: после установки один раз залогинься в Apple (пароль в репо/конфиг не попадает):
#   cd <DIR> && .venv/bin/python collector/login.py apple   # устройства
#   cd <DIR> && .venv/bin/python collector/login.py tags    # метки (AirTag/DIY)
set -euo pipefail

REPO_URL="${FZ_REPO:-https://github.com/anton-vinogradov/findmy-zoo.git}"
SVC=findmy-zoo
PORT=8815
ANISETTE_PORT=6969

# --- где код ---
SELF="${BASH_SOURCE[0]:-}"
if [ -n "$SELF" ] && [ -f "$(dirname -- "$SELF")/collector/hub.py" ]; then
  DIR="$(cd "$(dirname -- "$SELF")" && pwd)"
else
  command -v git >/dev/null || { echo "✗ нужен git"; exit 1; }
  DIR="${FZ_DIR:-/opt/findmy-zoo}"
  echo "→ код в $DIR"
  if [ -d "$DIR/.git" ]; then git -C "$DIR" pull --ff-only
  else sudo -n true 2>/dev/null && sudo mkdir -p "$DIR" && sudo chown "$(id -un)": "$DIR" || mkdir -p "$DIR"
       git clone --depth 1 "$REPO_URL" "$DIR"; fi
fi

# --- от кого работает сервис ---
if [ "$(id -u)" -eq 0 ]; then RUN_USER="${SUDO_USER:-root}"; SUDO=""; else RUN_USER="$(id -un)"; SUDO="sudo"; fi
asuser() { if [ "$(id -un)" = "$RUN_USER" ]; then "$@"; else sudo -u "$RUN_USER" -- "$@"; fi; }
[ "$(id -u)" -eq 0 ] && chown -R "$RUN_USER": "$DIR"

command -v python3 >/dev/null || { echo "✗ нужен python3"; exit 1; }

echo "→ venv и зависимости…"
asuser python3 -m venv "$DIR/.venv"
asuser "$DIR/.venv/bin/pip" install -q --upgrade pip
asuser "$DIR/.venv/bin/pip" install -q -r "$DIR/requirements.txt"

echo "→ конфиг и папка данных…"
[ -f "$DIR/collector/config.json" ] || asuser cp "$DIR/collector/config.example.json" "$DIR/collector/config.json"
asuser mkdir -p "$DIR/data/tags"

# --- macless anisette-контейнер для меток (FindMy.py -> http://127.0.0.1:6969) ---
CT=""
command -v docker >/dev/null && CT=docker
[ -z "$CT" ] && command -v podman >/dev/null && CT=podman
if [ -n "$CT" ]; then
  echo "→ anisette-сервер ($CT, порт $ANISETTE_PORT)…"
  if ! $SUDO $CT ps --format '{{.Names}}' 2>/dev/null | grep -qx anisette; then
    $SUDO $CT run -d --restart always --name anisette \
      -p 127.0.0.1:$ANISETTE_PORT:6969 \
      -v anisette-data:/home/Alcoholic/.config/anisette-v3 \
      dadoum/anisette-v3-server >/dev/null 2>&1 \
      && echo "  ✓ anisette поднят" \
      || echo "  ⚠ не удалось поднять anisette-контейнер — либо подними вручную, либо в config.json выставь anisetteUrl:null (встроенный генератор)"
  else echo "  ✓ anisette уже запущен"; fi
else
  echo "⚠ docker/podman не найдены. Для меток либо поставь контейнер dadoum/anisette-v3-server,"
  echo "  либо в collector/config.json выставь sources.tags.anisetteUrl: null (встроенный генератор FindMy.py)."
fi

echo "→ systemd-сервис $SVC…"
$SUDO tee "/etc/systemd/system/$SVC.service" >/dev/null <<UNIT
[Unit]
Description=findmy-zoo hub
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$DIR
ExecStart=$DIR/.venv/bin/python $DIR/collector/hub.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

$SUDO systemctl daemon-reload
$SUDO systemctl enable "$SVC" >/dev/null 2>&1 || true
$SUDO systemctl restart "$SVC"

echo "→ команда-мастер findmy-zoo-setup…"
$SUDO tee /usr/local/bin/findmy-zoo-setup >/dev/null <<WRAP
#!/usr/bin/env bash
exec "$DIR/.venv/bin/python" "$DIR/collector/setup.py" "\$@"
WRAP
$SUDO chmod +x /usr/local/bin/findmy-zoo-setup

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "✓ установлено. Карта: http://${IP:-<этот-сервер>}:$PORT"
echo
echo "  ОСТАЛСЯ ОДИН ШАГ — запусти мастер (спросит Apple ID + пароль + код 2FA, один раз):"
echo "      findmy-zoo-setup"
echo
echo "  логи:     journalctl -u $SVC -f"
echo "  обновить: повтори ту же команду установки"
