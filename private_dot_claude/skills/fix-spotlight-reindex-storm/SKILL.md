---
name: fix-spotlight-reindex-storm
description: Use when macOS Spotlight reindexes constantly - many mdworker_shared processes spawning and dying, mds or mds_stores burning CPU for days, a Mac sluggish with no obvious cause, or a sync/backup job pointed at iCloud Drive, Dropbox, or OneDrive. Also use when investigating why files show a recent ctime but an old mtime.
---

# Fix Spotlight Reindex Storm

## Overview

A scanner (rsync, backup agent, indexer) walking a **cloud-backed folder** makes the
file-provider daemon rewrite sync-state xattrs on every item it enumerates. On
file-provider storage those xattr writes trigger a Spotlight re-import. A job on a
timer therefore re-imports the whole tree forever, with no file ever changing.

**Merely enumerating is enough.** The scanner need not write, transfer, or re-apply
anything: a run that transfers 0 bytes and changes 0 mtimes still stamps the whole
tree. So it is not rsync re-applying permissions, not `--delete`'s destination scan,
and not temp-file+rename - those are the plausible stories, and all three are wrong.

**Core insight: the destination is the problem, not the scanner's flags.**
No rsync flag combination avoids this. Fix it by reducing what gets scanned.

## When to Use

- Many `mdworker_shared` processes; `mds_stores` has days of accumulated CPU time
- Machine sluggish, fans up, but `mdfind` returns correct results (index is fine)
- Files under iCloud Drive / Dropbox / OneDrive show **recent ctime, old mtime**
- A launchd/cron job syncs into a cloud folder on a short interval

Not this skill: a genuinely corrupt index (`mdutil -as` reports errors, `mdfind`
returns nothing) - that needs `mdutil -E`, not this.

## The Mechanism (measured, not assumed)

Identical operations, local folder vs iCloud folder, watching
`mdls -name kMDItemAttributeChangeDate`:

| operation | ctime | mtime | reindex (local) | reindex (cloud) |
|---|---|---|---|---|
| `chmod`   | moves | -     | no  | no  |
| `xattr -w`| moves | -     | **no**  | **YES** |
| write     | moves | moves | yes | yes |
| rsync scan, no content change | moves | **no** | no | **YES** |

Spotlight's `kMDItemAttributeChangeDate` normally tracks **mtime**. ctime alone does
not drive it. On cloud storage the provider's xattr writes do. So:

**ctime is the fingerprint you detect, not the cause you fix.**

## Diagnose

```bash
# 1. Confirm a storm: PID *turnover*, not count. All-new PIDs each sample = storm.
for i in 1 2 3; do ps aux | grep '[m]dworker_shared' | awk '{print $2}' | tr '\n' ' '; echo; sleep 3; done

# 2. What is being re-imported, and where does it live?
mdfind 'kMDItemAttributeChangeDate >= $time.now(-300)' | sed "s|$HOME/||" | cut -d/ -f1-3 | sort | uniq -c | sort -rn | head

# 3. The signature: recent ctime, old mtime = metadata churn, not real edits.
stat -f 'mtime=%Sm ctime=%Sc' -t '%F %T' <a churning file>

# 4. Find the scanner. Correlate its schedule with the churn.
launchctl list | grep -v '^-.*com\.apple' ; crontab -l
plutil -p ~/Library/LaunchAgents/<label>.plist   # StartInterval

# 5. Prove causation: run the scanner by hand, wait, count.
MARK=$(mktemp); sleep 1; <run the sync job>; sleep 90
find <dest> -type f -newercm "$MARK" | wc -l   # ctime bumped
find <dest> -type f -newermm "$MARK" | wc -l   # mtime bumped (expect 0)
```

## Fix

In order of effect:

1. **Stop mirroring what does not need mirroring.** Git repos already on a remote,
   trees covered by another backup, anything with a `.git` excluded (a history-less
   copy cannot restore a repo anyway). This is the whole fix in most cases.
2. **Delete the orphaned destination** after narrowing the job - `--delete` only
   prunes inside paths the job still syncs, so dropped subtrees linger and keep
   getting indexed.
3. **Exclude the destination from Spotlight - rename it to end in `.noindex`.**
   Measured on iCloud with a control, 40 files each, after one scan:

   | folder | ctime bumped | Spotlight re-imports |
   |---|---|---|
   | `.metadata_never_index` inside | 40 | 41 (same as control - **no effect**) |
   | name ends in `.noindex` | 40 | **0** |
   | control, no exclusion | 40 | 41 |

   **`.metadata_never_index` does not work on file-provider storage**, despite being
   the commonly cited fix. Only the `.noindex` name suffix does. Neither stops the
   provider stamping ctime - they stop Spotlight reacting to it - and neither
   retroactively purges entries already indexed. Always verify with a control.
4. **Lengthen the interval** only after the above. It divides the pain, not removes it.

`sudo mdutil -E /` rebuilds the index. It does not fix the cause, costs hours of
reindexing, and is rarely needed - the index is usually healthy, just never idle.

## Measurement Pitfalls

These produce confidently wrong conclusions. Every one of them was hit in practice:

| Trap | Reality |
|---|---|
| `find -newerct "$file"` | `t` means a **time string**, not a path. Use `-newercm` (file ctime vs reference mtime). |
| Measuring right after the job exits | Provider stamping is **asynchronous**, lagging 60-90s. Measuring at 2s reports 0 and looks like exoneration. |
| `rsync --dry-run --itemize-changes` shows nothing | Itemize predicts **transfers**. It cannot see provider side effects. "Nothing to transfer" does not exonerate the scanner. |
| Steady `mdworker_shared` count = healthy | Check PID **turnover**. A constant count of constantly-recycled workers is a storm. |
| `du -sh <path>` reporting a huge index | If output says `.`, the argument was lost (line wrap) and it measured `$PWD`. A number identical on two machines is a measurement bug, not a finding. |

## Common Mistakes

- **Reaching for rsync flags.** `--inplace`, dropping `-p/-g/-o`, `--omit-dir-times`,
  `--size-only`, dropping `--delete`: all measured, none help. Tested flag sets
  stamped 675/675 files every time.
- **Inventing a plausible mechanism.** "temp-file + rename makes the provider see new
  items" is wrong when mtime is bumped on **0** files - nothing was written.
- **Blaming `--delete` for the enumeration.** With and without it: identical.
- **Blaming attribute preservation.** `--no-p --no-g --no-o` stamped every file too.
- **Assuming ctime drives Spotlight.** It does not, even on cloud storage. The xattr
  write does. Test with `mdls`, do not reason from the timestamp name.
- **Trusting `.metadata_never_index`.** Measured ineffective on cloud storage. Use the
  `.noindex` suffix, and confirm against a control folder rather than assuming.

## Verify

```bash
ps aux | grep -c '[m]dworker_shared'                                  # settles to ~1
mdfind 'kMDItemAttributeChangeDate >= $time.now(-300)' | wc -l        # drops sharply
```
Confirm across a **scheduled** run you did not trigger.
