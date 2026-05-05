#!/usr/bin/env bash
# Apply versioned Syncthing settings to the local instance.
#
# Manages four endpoints, each driven by a generic file in
# $XDG_CONFIG_HOME/syncthing-sync/ (committed to dotfiles, no instance state):
#
#   stignore-shared       -> POST /rest/db/ignores?folder=<id> for every folder
#   options.json          -> PATCH /rest/config/options
#   gui.json              -> PATCH /rest/config/gui  (apikey/user/password preserved)
#   defaults-folder.json  -> PATCH /rest/config/defaults/folder
#
# "PATCH" is GET current -> overlay only top-level keys present in our file -> PUT,
# so every field we don't manage (apikey, gui password, listen addresses, the
# device list on the folder default, etc.) is left untouched.
#
# Optional per-folder ignore overrides live in
#   $XDG_CONFIG_HOME/syncthing-sync/overrides.json (NOT committed):
#       { "*": ["everywhere"], "<folder-id>": ["only/here"] }
#
# Usage: scripts/syncthing-apply.sh [--dry-run]

set -euo pipefail

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
CONF_DIR="$XDG_CONFIG_HOME/syncthing-sync"
SHARED_FILE="$CONF_DIR/stignore-shared"
OVERRIDES_FILE="$CONF_DIR/overrides.json"
OPTIONS_FILE="$CONF_DIR/options.json"
GUI_FILE="$CONF_DIR/gui.json"
DEFAULTS_FOLDER_FILE="$CONF_DIR/defaults-folder.json"

if [[ "$(uname)" == "Darwin" ]]; then
  ST_CONFIG="$HOME/Library/Application Support/Syncthing/config.xml"
else
  ST_CONFIG="${XDG_CONFIG_HOME}/syncthing/config.xml"
fi

API_URL="${SYNCTHING_URL:-http://localhost:8384}"

if [[ ! -f "$ST_CONFIG" ]]; then
  echo "syncthing config not found: $ST_CONFIG" >&2
  exit 1
fi

API_KEY="$(grep -o '<apikey>[^<]*' "$ST_CONFIG" | head -1 | sed 's|<apikey>||')"
if [[ -z "$API_KEY" ]]; then
  echo "could not extract apikey from $ST_CONFIG" >&2
  exit 1
fi

api() { curl -fsS -H "X-API-Key: $API_KEY" "$@"; }

apply_ignores() {
  if [[ ! -f "$SHARED_FILE" ]]; then
    echo "skip ignores: $SHARED_FILE missing"
    return
  fi

  local folder_ids fid payload count
  mapfile -t folder_ids < <(api "$API_URL/rest/config/folders" \
    | python3 -c 'import sys,json; [print(f["id"]) for f in json.load(sys.stdin)]')

  if [[ ${#folder_ids[@]} -eq 0 ]]; then
    echo "ignores: no folders configured"
    return
  fi

  for fid in "${folder_ids[@]}"; do
    payload=$(SHARED="$SHARED_FILE" OVR="$OVERRIDES_FILE" FID="$fid" python3 -c '
import json, os, re
patterns, seen = [], set()
def add(p):
    p = p.rstrip()
    if p and p not in seen:
        seen.add(p); patterns.append(p)
with open(os.environ["SHARED"]) as f:
    for line in f:
        line = re.sub(r"//.*$", "", line).rstrip()
        if line.strip(): add(line)
ovr_path = os.environ["OVR"]
if os.path.exists(ovr_path):
    with open(ovr_path) as f:
        data = json.load(f)
    for key in ("*", os.environ["FID"]):
        for pat in (data.get(key) or []):
            add(pat)
print(json.dumps({"ignore": patterns}))
')
    count=$(echo "$payload" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["ignore"]))')
    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "[ignores:$fid] would apply $count patterns (dry-run)"
    else
      api -X POST -H 'Content-Type: application/json' -d "$payload" \
        "$API_URL/rest/db/ignores?folder=$fid" >/dev/null
      echo "[ignores:$fid] applied $count patterns"
    fi
  done
}

# GET endpoint, overlay only top-level keys present in $file, PUT.
merge_patch() {
  local label="$1" endpoint="$2" file="$3"
  if [[ ! -f "$file" ]]; then
    echo "skip $label: $file missing"
    return
  fi

  local current merged keys
  current=$(api "$API_URL$endpoint")
  merged=$(CUR="$current" FILE="$file" python3 -c '
import json, os
cur = json.loads(os.environ["CUR"])
with open(os.environ["FILE"]) as f:
    overlay = json.load(f)
for k, v in overlay.items():
    cur[k] = v
print(json.dumps(cur))
')

  keys=$(python3 -c 'import json,sys; print(", ".join(json.load(open(sys.argv[1])).keys()))' "$file")
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[$label] would PATCH keys: $keys (dry-run)"
    return
  fi
  api -X PUT -H 'Content-Type: application/json' -d "$merged" "$API_URL$endpoint" >/dev/null
  echo "[$label] applied keys: $keys"
}

apply_ignores
merge_patch options "/rest/config/options" "$OPTIONS_FILE"
merge_patch gui "/rest/config/gui" "$GUI_FILE"
merge_patch defaults-folder "/rest/config/defaults/folder" "$DEFAULTS_FOLDER_FILE"

echo "done."
