#!/usr/bin/env bash
# Install the Tidephase (观势) board and Soft UI theme into a DeepSeek Harness profile.
#   ./dsh/scripts/install.sh clean     official DSH profile "web" under $DSH_HOME
#   DSH_HOME=... PNPM_BIN=... ./dsh/scripts/install.sh workdsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MODE="${1:-clean}"
STAGE="$ROOT/dsh/.packs"
mkdir -p "$STAGE"

pack() {
  local dir="$1"
  local name
  name="$(node -p "require('$dir/package.json').name + '-' + require('$dir/package.json').version + '.tgz'")"
  (cd "$dir" && npm pack --pack-destination "$STAGE" >/dev/null)
  echo "$STAGE/$name"
}

ensure_bundle() {
  local profile_json="$1"
  local name="$2"
  python3 - "$profile_json" "$name" <<'PY'
import json, sys
path, name = sys.argv[1], sys.argv[2]
data = json.load(open(path))
bundles = data.setdefault("dsh", {}).setdefault("profile", {}).setdefault("bundles", [])
if name not in bundles:
    bundles.append(name)
json.dump(data, open(path, "w"), ensure_ascii=False, indent=2)
open(path, "a").write("\n")
PY
}

set_dep() {
  local profile_json="$1"
  local name="$2"
  local value="$3"
  python3 - "$profile_json" "$name" "$value" <<'PY'
import json, sys
path, name, value = sys.argv[1], sys.argv[2], sys.argv[3]
data = json.load(open(path))
data.setdefault("dependencies", {})[name] = value
# Never let plugin packages overwrite core DSH pins.
if name.startswith("@deepseek-ai/") and value.endswith(".tgz"):
    raise SystemExit(f"refusing to pin {name} to a local tarball")
json.dump(data, open(path, "w"), ensure_ascii=False, indent=2)
open(path, "a").write("\n")
PY
}

echo "Packing plugins..."
BOARD_TGZ="$(pack "$ROOT/dsh/guanshi-board")"
THEME_TGZ="$(pack "$ROOT/dsh/guanshi-theme")"

if [[ "$MODE" == "workdsh" ]]; then
  if [[ -z "${DSH_HOME:-}" || -z "${PNPM_BIN:-}" ]]; then
    echo "workdsh mode needs DSH_HOME and PNPM_BIN. Do not bake a machine path into this script." >&2
    exit 1
  fi
  PROFILE="${DSH_PROFILE:-preview}"
  PROFILE_JSON="$DSH_HOME/profiles/$PROFILE/package.json"
  if [[ ! -f "$PROFILE_JSON" ]]; then
    echo "Missing profile package.json: $PROFILE_JSON" >&2
    exit 1
  fi
  # Keep official pins intact. Only rewrite Guanshi deps and bundle list.
  set_dep "$PROFILE_JSON" "guanshi-board" "file:$BOARD_TGZ"
  set_dep "$PROFILE_JSON" "guanshi-theme" "file:$THEME_TGZ"
  ensure_bundle "$PROFILE_JSON" "guanshi-board"
  ensure_bundle "$PROFILE_JSON" "guanshi-theme"
  echo "Installing into workdsh profile $PROFILE with pnpm..."
  (cd "$DSH_HOME/profiles/$PROFILE" && "$PNPM_BIN" install --no-frozen-lockfile)
else
  DSH_HOME="${DSH_HOME:-$HOME/.guanshi-dsh}"
  PROFILE="${DSH_PROFILE:-web}"
  DSH_BIN="${DSH_BIN:-$(command -v dsh || true)}"
  if [[ -z "$DSH_BIN" ]]; then
    echo "dsh is not on PATH. Install DeepSeek Harness 0.2.0-rc.2 first." >&2
    exit 1
  fi
  if [[ ! -f "$DSH_HOME/profiles/$PROFILE/package.json" ]]; then
    echo "Profile $PROFILE is missing under $DSH_HOME." >&2
    exit 1
  fi
  echo "Installing into $DSH_HOME profile $PROFILE"
  DSH_HOME="$DSH_HOME" "$DSH_BIN" plugin --profile "$PROFILE" add "$BOARD_TGZ" "$THEME_TGZ"
fi

SKILL_HOME="$DSH_HOME/agents/skills"
mkdir -p "$SKILL_HOME"
rm -rf "$SKILL_HOME/market-data" "$SKILL_HOME/board-edit"
cp -a "$ROOT/dsh/skills/market-data" "$SKILL_HOME/market-data"
cp -a "$ROOT/dsh/skills/board-edit" "$SKILL_HOME/board-edit"

echo "Installed guanshi-board and guanshi-theme."
echo "Skills are in $SKILL_HOME."
echo "Restart that Harness profile, then open 观势."
