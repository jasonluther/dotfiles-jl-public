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
FOLDERS_REMOVE_FILE="$CONF_DIR/folders-remove"
FOLDERS_ENSURE_FILE="$CONF_DIR/folders-ensure.json"

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

# Reconcile folder membership from two optional, generic config files:
#   folders-remove       -> folders (by path or id) to delete from this instance
#   folders-ensure.json  -> folders to create if absent, shared with every device
#                           already known to this instance (no fleet IDs needed),
#                           inheriting versioning from /rest/config/defaults/folder.
# Both are optional; absent files mean "do nothing", so this is a no-op for a
# freshly-scaffolded instance. Removing a folder only stops syncing it — local
# files stay put.
reconcile_folders() {
  if [[ ! -f "$FOLDERS_REMOVE_FILE" && ! -f "$FOLDERS_ENSURE_FILE" ]]; then
    return
  fi

  local folders devices defaults plan
  folders=$(api "$API_URL/rest/config/folders")
  devices=$(api "$API_URL/rest/config/devices")
  defaults=$(api "$API_URL/rest/config/defaults/folder")

  # Python planner emits one JSON action per line: {"op":"DEL"|"PUT", ...}.
  plan=$(
    FOLDERS="$folders" DEVICES="$devices" DEFAULTS="$defaults" \
      REMOVE_FILE="$FOLDERS_REMOVE_FILE" ENSURE_FILE="$FOLDERS_ENSURE_FILE" \
      HOME="$HOME" python3 <<'PY'
import json, os, re

home = os.environ["HOME"]


def norm(p):
    return home + p[1:] if p.startswith("~") else p


folders = json.loads(os.environ["FOLDERS"])
by_id = {f["id"]: f for f in folders}
by_path = {norm(f.get("path", "")): f for f in folders}
actions = []

remove_file = os.environ["REMOVE_FILE"]
if os.path.exists(remove_file):
    with open(remove_file) as fh:
        for line in fh:
            entry = re.sub(r"//.*", "", line).strip()
            if not entry:
                continue
            f = by_id.get(entry) or by_path.get(norm(entry))
            if f:
                actions.append({"op": "DEL", "id": f["id"]})

removed = {a["id"] for a in actions}

ensure_file = os.environ["ENSURE_FILE"]
if os.path.exists(ensure_file):
    with open(ensure_file) as fh:
        ensure = json.load(fh)
    devices = json.loads(os.environ["DEVICES"])
    defaults = json.loads(os.environ["DEFAULTS"])
    dev_list = [{"deviceID": d["deviceID"]} for d in devices]
    for e in ensure:
        fid, path = e["id"], e["path"]
        hit = by_id.get(fid) or by_path.get(norm(path))
        if hit and hit["id"] not in removed:
            continue  # already present
        folder = dict(defaults)
        folder.update(
            {"id": fid, "label": e.get("label", fid), "path": path, "devices": dev_list}
        )
        actions.append({"op": "PUT", "id": fid, "path": path, "body": folder})

for a in actions:
    print(json.dumps(a))
PY
  )

  if [[ -z "$plan" ]]; then
    echo "[folders] nothing to reconcile"
    return
  fi

  local action op fid path body
  while IFS= read -r action; do
    [[ -z "$action" ]] && continue
    op=$(echo "$action" | python3 -c 'import json,sys; print(json.load(sys.stdin)["op"])')
    fid=$(echo "$action" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
    if [[ "$op" == "DEL" ]]; then
      if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "[folders] would remove id $fid (dry-run)"
      else
        api -X DELETE "$API_URL/rest/config/folders/$fid" >/dev/null
        echo "[folders] removed id $fid"
      fi
    else
      path=$(echo "$action" | python3 -c 'import json,sys; print(json.load(sys.stdin)["path"])')
      if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "[folders] would add id $fid at $path (dry-run)"
      else
        # Syncthing needs the folder dir to exist to drop its .stfolder marker.
        mkdir -p "${path/#\~/$HOME}"
        body=$(echo "$action" | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["body"]))')
        api -X PUT -H 'Content-Type: application/json' -d "$body" \
          "$API_URL/rest/config/folders/$fid" >/dev/null
        echo "[folders] added id $fid at $path"
      fi
    fi
  done <<<"$plan"
}

apply_ignores() {
  if [[ ! -f "$SHARED_FILE" ]]; then
    echo "skip ignores: $SHARED_FILE missing"
    return
  fi

  local fid payload count folder_ids_raw
  folder_ids_raw=$(api "$API_URL/rest/config/folders" \
    | python3 -c 'import sys,json; [print(f["id"]) for f in json.load(sys.stdin)]')

  if [[ -z "$folder_ids_raw" ]]; then
    echo "ignores: no folders configured"
    return
  fi

  while IFS= read -r fid; do
    [[ -z "$fid" ]] && continue
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
  done <<<"$folder_ids_raw"
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

reconcile_folders
apply_ignores
merge_patch options "/rest/config/options" "$OPTIONS_FILE"
merge_patch gui "/rest/config/gui" "$GUI_FILE"
merge_patch defaults-folder "/rest/config/defaults/folder" "$DEFAULTS_FOLDER_FILE"

echo "done."
