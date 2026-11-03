#!/bin/sh
set -eu
cd /opt/guanshi
marker="/data/.guanshi-plugins-$(node -p "require('/opt/guanshi/dsh/guanshi-board/package.json').version")"
if [ ! -f "$marker" ]; then
  ./dsh/scripts/install.sh clean
  mkdir -p /data
  touch "$marker"
fi
exec dsh web --host 0.0.0.0 --port 3080 --no-open --trusted-host 127.0.0.1:3080
