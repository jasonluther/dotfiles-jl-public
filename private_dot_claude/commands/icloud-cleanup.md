# iCloud Cleanup

Diagnose and fix iCloud Drive sync inconsistencies in the current directory tree.

## What to look for

### " 2" conflict duplicates

iCloud creates files like `foo 2.txt` or `.env 2` when it detects sync conflicts.
Find them and report what they are. Do NOT delete without confirming — the " 2" copy
may be the newer version.

### Dataless / evicted files

Files evicted to iCloud have the `compressed,dataless` flag. They appear in `ls` but
have no local content. Directories may show entries but `find` can't descend into them.

### Broken git worktrees

Orphaned worktree directories where `.git` points to missing metadata, or directories
that lost their `.git` entirely. Check if they have real content or are just iCloud stubs.

## Diagnostic commands

```bash
# Find " 2" conflict files (iCloud duplicates)
find . -name '* 2' -o -name '* 2.*' 2>/dev/null

# Check file flags — look for "compressed,dataless" (iCloud evicted)
ls -lO <file>

# Check numeric flags (dataless = large number like 1073741920)
stat -f '%f %N' <file>

# Check disk usage — evicted dirs are tiny (8-20KB for a full repo)
du -sk <directory>

# Check extended attributes for iCloud metadata
xattr <file>
xattr -p com.apple.metadata:com_apple_backup_excludeItem <file> 2>/dev/null

# brctl (Bird control) — iCloud Drive status
brctl status <path>              # iCloud zone status
brctl log --path=<path> -c 5     # recent sync events
brctl evict <path>               # force evict to iCloud (free local space)
brctl download <path>            # force download from iCloud

# Diagnose an entire directory tree
brctl diagnose                   # generates full iCloud diagnostic bundle
```

## Procedure

1. **Scan** the target directory for problems:
   - `find . -name '* 2' -o -name '* 2.*'` for conflict duplicates
   - `find . -flags dataless -maxdepth 3` for evicted files (may not work in all contexts; fall back to `ls -lO` spot checks)
   - Check `du -sk` on suspicious directories — real repos are 100MB+, iCloud stubs are <1MB

2. **Report findings** as a table: path, problem type, size, recommendation

3. **For " 2" files**: compare with the original using `diff` or `md5`. If identical, the " 2" is safe to delete. If different, show the diff and ask which to keep.

4. **For evicted/broken worktrees**: check if the branch exists locally (`git branch --contains` or `git log`), whether it's merged to main, and whether the worktree metadata still exists in `.git/worktrees/`. If the branch is merged and metadata is gone, safe to delete.

5. **For broken permissions or stuck downloads**: try `brctl download <path>` to re-download, or `xattr -d com.apple.quarantine <path>` if quarantine is blocking.

6. **Clean up** only after user confirms. Use `rm -rf` for directories (iCloud may make `rm` on individual evicted files slow or hang).

## Notes

- File operations on iCloud-managed directories can be very slow or hang. Use timeouts.
- `rm -rf` on large evicted directories may trigger iCloud downloads. If it hangs, try again — iCloud eventually gives up.
- Piping (`|`) inside `for` loops in zsh can fail with `command not found` for builtins. Use standalone commands or subshells instead.
- The `.nosync` extension or `com.apple.metadata:com_apple_backup_excludeItem` xattr prevents iCloud sync for specific files.
