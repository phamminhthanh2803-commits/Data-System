#!/usr/bin/env bash
# Cai rclone tren runner GitHub Actions, co du phong (15/10/2026: rclone.org timeout 135 s -> job Shipping AM chet exit 127).
#   1. script chinh thuc rclone.org (timeout ngan)
#   2. ban moi nhat tu GitHub releases (linux-amd64.zip)
#   3. apt (ban cu hon nhung du dung)
set -u
if command -v rclone >/dev/null 2>&1; then rclone version | head -1; exit 0; fi

try_official() {
  curl -fsSL --connect-timeout 20 --max-time 120 https://rclone.org/install.sh -o /tmp/rclone-install.sh \
    && sudo bash /tmp/rclone-install.sh
}

try_github() {
  url=$(curl -fsSL --connect-timeout 20 --max-time 60 https://api.github.com/repos/rclone/rclone/releases/latest \
        | grep -o '"browser_download_url": *"[^"]*linux-amd64\.zip"' | head -1 | sed 's/.*"\(https[^"]*\)"/\1/')
  [ -n "${url:-}" ] || return 1
  curl -fsSL --connect-timeout 20 --max-time 180 "$url" -o /tmp/rclone.zip || return 1
  rm -rf /tmp/rclone-x && mkdir -p /tmp/rclone-x && unzip -q /tmp/rclone.zip -d /tmp/rclone-x || return 1
  sudo install -m 755 /tmp/rclone-x/*/rclone /usr/bin/rclone
}

try_apt() {
  sudo apt-get install -y -qq rclone
}

for f in try_official try_github try_apt; do
  echo "== cai rclone: $f"
  if $f && command -v rclone >/dev/null 2>&1; then rclone version | head -1; exit 0; fi
  echo "   $f that bai"
done
echo "::error::Khong cai duoc rclone (rclone.org, GitHub releases va apt deu loi)"
exit 1
