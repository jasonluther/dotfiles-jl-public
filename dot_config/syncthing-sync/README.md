# syncthing-sync

Tools for keeping Syncthing settings consistent across hosts without leaking
instance-specific identifiers (device IDs, folder IDs, paths, hostnames) into
a public dotfiles repo.

## What's versioned

- `stignore-shared` — generic ignore patterns applied to every Syncthing folder.
- `options.json` — desired values for `/rest/config/options` (telemetry,
  discovery, NAT, relays, browser-on-start, concurrency, etc.).
- `gui.json` — desired values for `/rest/config/gui` (theme, TLS, auth flags).
  `apikey`, `user`, `password`, and `address` are never managed here — the
  apply script preserves whatever the host already has.
- `defaults-folder.json` — desired values for `/rest/config/defaults/folder`
  (rescan interval, fs watcher, versioning policy, ignorePerms, etc.). The
  per-host `devices` list on this template is preserved.
- `../../scripts/syncthing-apply.sh` — discovers folder IDs from the local API
  and applies all of the above. For each `/rest/config/*` endpoint it does a
  GET → overlay-only-our-keys → PUT, so anything we don't manage is left intact.

## What's local-only (NOT committed)

- `~/.config/syncthing-sync/overrides.json` — optional per-folder ignore
  additions:

  ```json
  {
    "*": ["everywhere/pattern"],
    "abcde-12345": ["only/this/folder"]
  }
  ```

  Sync this file via Syncthing itself, a private repo, or 1Password if you
  want it on multiple hosts.

## Apply

```sh
scripts/syncthing-apply.sh           # apply
scripts/syncthing-apply.sh --dry-run # preview
```

The script reads the API key from the local Syncthing config; it never reads
or writes anything host-specific to this repo. Run it on each host after
editing the versioned files.
