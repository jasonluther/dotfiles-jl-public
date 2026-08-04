"""Tests for sync-gh.py WIP snapshot engine. Run: pytest -q test_sync_gh.py"""

import importlib.util
import os
import subprocess
import time
from pathlib import Path

SRC = (
    Path(__file__).resolve().parents[1] / "dot_local" / "bin" / "executable_sync-gh.py"
)
spec = importlib.util.spec_from_file_location("sync_gh", SRC)
sg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sg)


def git(dest, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(dest), *args], capture_output=True, text=True, check=check
    )


def init_repo(path, *, origin=None):
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", "t@t.test")
    git(path, "config", "user.name", "Test")
    if origin:
        git(path, "remote", "add", "origin", str(origin))
    return path


def commit_file(path, name, content, msg="c"):
    (path / name).write_text(content)
    git(path, "add", name)
    git(path, "commit", "-q", "-m", msg)


def tree_of(dest, ref):
    return git(dest, "rev-parse", f"{ref}^{{tree}}").stdout.strip()


def ls_tree_files(dest, ref):
    out = git(dest, "ls-tree", "-r", "--name-only", ref).stdout.strip()
    return set(out.splitlines()) if out else set()


# ---------- snapshot_commit ----------


def test_snapshot_clean_returns_none(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "hello")
    assert sg.snapshot_commit(r, "m") is None


def test_snapshot_captures_modified_tracked(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "hello")
    (r / "a.txt").write_text("changed")
    sha = sg.snapshot_commit(r, "m")
    assert sha
    blob = git(r, "show", f"{sha}:a.txt").stdout
    assert blob == "changed"
    # HEAD parent preserved, real tree untouched
    assert (
        git(r, "rev-parse", f"{sha}^").stdout.strip()
        == git(r, "rev-parse", "HEAD").stdout.strip()
    )
    assert git(r, "status", "--porcelain").stdout.strip() == "M a.txt"


def test_snapshot_includes_untracked_new_file(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "hello")
    (r / "brand_new.txt").write_text("wip")  # never git-added
    sha = sg.snapshot_commit(r, "m")
    assert sha
    assert "brand_new.txt" in ls_tree_files(r, sha)
    # real index untouched — file still untracked afterwards
    assert "?? brand_new.txt" in git(r, "status", "--porcelain").stdout


def test_snapshot_excludes_gitignored(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "hello")
    (r / ".gitignore").write_text("junk/\n*.log\n")
    git(r, "add", ".gitignore")
    git(r, "commit", "-q", "-m", "ignore")
    (r / "junk").mkdir()
    (r / "junk" / "big.bin").write_text("x")
    (r / "debug.log").write_text("noise")
    (r / "keep.py").write_text("real")
    sha = sg.snapshot_commit(r, "m")
    files = ls_tree_files(r, sha)
    assert "keep.py" in files
    assert "debug.log" not in files
    assert not any(f.startswith("junk/") for f in files)


def test_snapshot_no_head_unborn(tmp_path):
    r = init_repo(tmp_path / "r")  # no commits yet
    (r / "first.txt").write_text("x")
    sha = sg.snapshot_commit(r, "m")
    assert sha
    assert git(r, "rev-parse", f"{sha}^", check=False).returncode != 0  # no parent
    assert "first.txt" in ls_tree_files(r, sha)


def test_snapshot_leaves_no_temp_index(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "hello")
    (r / "a.txt").write_text("changed")
    sg.snapshot_commit(r, "m")
    leftovers = list((r / ".git").glob("wip-index-*"))
    assert leftovers == []


# ---------- push_wip ----------


def test_push_wip_creates_branch_with_new_file(tmp_path):
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare), check=False)
    r = init_repo(tmp_path / "r", origin=bare)
    commit_file(r, "a.txt", "hello")
    git(r, "push", "-q", "origin", "main")
    (r / "wip_new.txt").write_text("in progress")
    sg.push_wip("r", r, "hostx")
    files = ls_tree_files(bare, "refs/heads/wip/hostx")
    assert "wip_new.txt" in files and "a.txt" in files


def test_push_wip_clean_pushes_unpushed_commit(tmp_path):
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare), check=False)
    r = init_repo(tmp_path / "r", origin=bare)
    commit_file(r, "a.txt", "hello")
    git(r, "push", "-q", "origin", "main")
    commit_file(r, "b.txt", "second", msg="unpushed")  # committed, not pushed
    git(r, "fetch", "-q", "origin")  # refresh remote-tracking (like the real pull)
    sg.push_wip("r", r, "hostx")
    assert tree_of(bare, "refs/heads/wip/hostx") == tree_of(r, "HEAD")


def test_push_wip_clean_synced_is_noop(tmp_path):
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare), check=False)
    r = init_repo(tmp_path / "r", origin=bare)
    commit_file(r, "a.txt", "hello")
    git(r, "push", "-q", "origin", "main")
    git(r, "push", "-q", "--force", "origin", "HEAD:refs/heads/wip/hostx")
    git(r, "fetch", "-q", "origin")
    before = git(bare, "rev-parse", "refs/heads/wip/hostx").stdout.strip()
    sg.push_wip("r", r, "hostx")  # nothing changed
    after = git(bare, "rev-parse", "refs/heads/wip/hostx").stdout.strip()
    assert before == after


def test_push_wip_skips_detached_head(tmp_path):
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare), check=False)
    r = init_repo(tmp_path / "r", origin=bare)
    commit_file(r, "a.txt", "hello")
    commit_file(r, "b.txt", "two")
    git(r, "push", "-q", "origin", "main")
    git(r, "checkout", "-q", "HEAD~1")  # detached
    sg.push_wip("r", r, "hostx")
    assert git(bare, "rev-parse", "refs/heads/wip/hostx", check=False).returncode != 0


def test_push_wip_skips_in_progress(tmp_path):
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare), check=False)
    r = init_repo(tmp_path / "r", origin=bare)
    commit_file(r, "a.txt", "hello")
    git(r, "push", "-q", "origin", "main")
    (r / ".git" / "MERGE_HEAD").write_text("deadbeef\n")
    sg.push_wip("r", r, "hostx")
    assert git(bare, "rev-parse", "refs/heads/wip/hostx", check=False).returncode != 0


# ---------- bundle_wip ----------


def test_bundle_wip_creates_and_restores(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "hello")
    (r / "wip_new.txt").write_text("in progress")
    bundles = tmp_path / "bundles"
    sg.bundle_wip("r", r, "hostx", bundles)
    bundle = bundles / f"{sg.bundle_key(r)}@hostx.bundle"
    assert bundle.is_file()
    # restore: fetch the wip ref from the bundle into a fresh clone
    clone = init_repo(tmp_path / "clone")
    git(clone, "fetch", str(bundle), "refs/wip/hostx:refs/wip/hostx")
    assert "wip_new.txt" in ls_tree_files(clone, "refs/wip/hostx")


def test_bundle_wip_per_host_filename(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "hello")
    bundles = tmp_path / "bundles"
    sg.bundle_wip("r", r, "hostA", bundles)
    sg.bundle_wip("r", r, "hostB", bundles)
    names = {p.name for p in bundles.iterdir()}
    k = sg.bundle_key(r)
    assert {f"{k}@hostA.bundle", f"{k}@hostB.bundle"} <= names


def test_bundle_wip_skips_when_unchanged(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "hello")
    bundles = tmp_path / "bundles"
    sg.bundle_wip("r", r, "hostx", bundles)
    bundle = bundles / f"{sg.bundle_key(r)}@hostx.bundle"
    mtime1 = bundle.stat().st_mtime_ns
    sg.bundle_wip("r", r, "hostx", bundles)  # no changes → should skip rewrite
    assert bundle.stat().st_mtime_ns == mtime1
    # after a change, it re-bundles
    (r / "more.txt").write_text("x")
    sg.bundle_wip("r", r, "hostx", bundles)
    assert bundle.stat().st_mtime_ns != mtime1


def test_bundle_wip_no_tmp_left(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "hello")
    (r / "n.txt").write_text("x")
    bundles = tmp_path / "bundles"
    sg.bundle_wip("r", r, "hostx", bundles)
    assert list(bundles.glob("*.tmp")) == []


# ---------- classify_repo / iter_local_repos ----------


def test_classify(tmp_path, monkeypatch):
    gh = tmp_path / "gh"
    pub = gh / "public"
    arch = gh / "archived"
    monkeypatch.setattr(sg, "GH_DIR", gh)
    monkeypatch.setattr(sg, "PUBLIC_DIR", pub)
    monkeypatch.setattr(sg, "ARCHIVED_DIR", arch)
    monkeypatch.setattr(sg, "ARCHIVED_PUBLIC_DIR", arch / "public")

    priv = init_repo(gh / "priv", origin=tmp_path / "o.git")
    pubrepo = init_repo(pub / "pubrepo", origin=tmp_path / "o2.git")
    archrepo = init_repo(arch / "old")
    localonly = init_repo(gh / "localonly")  # under GH_DIR but no origin
    proj = init_repo(tmp_path / "Projects" / "thing", origin=tmp_path / "o3.git")

    assert sg.classify_repo(priv) == "push"
    assert sg.classify_repo(pubrepo) == "bundle"
    assert sg.classify_repo(archrepo) == "skip"
    assert sg.classify_repo(localonly) == "bundle"  # no origin → bundle, never push
    assert sg.classify_repo(proj) == "bundle"
    assert sg.classify_repo(tmp_path / "nope") == "skip"


def test_iter_local_repos(tmp_path):
    root = tmp_path / "root"
    init_repo(root / "a")
    init_repo(root / "b")
    (root / "not_a_repo").mkdir(parents=True)
    (root / "file.txt").parent.mkdir(exist_ok=True)
    (root / "file.txt").write_text("x")
    found = {p.name for p in sg.iter_local_repos([root, tmp_path / "missing"])}
    assert found == {"a", "b"}


# ---------- --wip-only makes no GitHub API calls ----------


def test_wip_only_makes_no_github_calls(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("GitHub API called in --wip-only mode")

    monkeypatch.setattr(sg, "get_repos", boom)
    monkeypatch.setattr(sg, "get_orgs", boom)
    monkeypatch.setattr(sg, "WIP_SCAN_ROOTS", [tmp_path / "empty"])
    monkeypatch.setattr(sg, "WIP_BUNDLE_DIR", tmp_path / "b")
    monkeypatch.setattr(sg, "WIP_STATUS_FILE", tmp_path / "var" / "wip-sync.status")
    monkeypatch.setattr(sg.sys, "argv", ["sync-gh.py", "--wip-only"]) if hasattr(
        sg, "sys"
    ) else None
    import sys

    monkeypatch.setattr(sys, "argv", ["sync-gh.py", "--wip-only"])
    sg.main()  # must not raise


# ---------- fixes from code review ----------


def test_bundle_key_distinguishes_same_basename(tmp_path):
    a = tmp_path / "Code" / "gh" / "public" / "notes"
    b = tmp_path / "Projects" / "notes"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    assert sg.bundle_key(a) != sg.bundle_key(b)  # same basename, different key


def test_bundle_wip_same_basename_no_collision(tmp_path, monkeypatch):
    # Two 'bundle'-routed repos sharing a basename must not overwrite each other.
    monkeypatch.setenv("HOME", str(tmp_path))
    a = init_repo(tmp_path / "Code" / "gh" / "public" / "notes")
    b = init_repo(tmp_path / "Projects" / "notes")
    commit_file(a, "a.txt", "from-public")
    (a / "wip_a.txt").write_text("A-wip")
    commit_file(b, "b.txt", "from-projects")
    (b / "wip_b.txt").write_text("B-wip")
    bundles = tmp_path / "bundles"
    sg.bundle_wip("notes", a, "hostx", bundles)
    sg.bundle_wip("notes", b, "hostx", bundles)
    files = {p.name for p in bundles.iterdir() if p.suffix == ".bundle"}
    assert len(files) == 2  # distinct files, no clobber
    # each bundle carries its own repo's WIP
    ca = init_repo(tmp_path / "check_a")
    git(
        ca,
        "fetch",
        str(bundles / f"{sg.bundle_key(a)}@hostx.bundle"),
        "refs/wip/hostx:refs/wip/hostx",
    )
    assert "wip_a.txt" in ls_tree_files(ca, "refs/wip/hostx")
    assert "wip_b.txt" not in ls_tree_files(ca, "refs/wip/hostx")


def test_wip_only_continues_past_failing_repo(tmp_path, monkeypatch):
    root = tmp_path / "root"
    r1 = init_repo(root / "aaa")
    commit_file(r1, "a", "1")
    (r1 / "new1").write_text("x")
    r2 = init_repo(root / "bbb")
    commit_file(r2, "b", "1")
    (r2 / "new2").write_text("y")
    bundles = tmp_path / "bundles"
    status = tmp_path / "var" / "wip.status"
    monkeypatch.setattr(sg, "WIP_STATUS_FILE", status)

    real_bundle = sg.bundle_wip

    def flaky(name, dest, host, bdir):
        if dest.name == "aaa":
            raise RuntimeError("boom")
        return real_bundle(name, dest, host, bdir)

    monkeypatch.setattr(sg, "bundle_wip", flaky)
    sg.wip_only_main("hostx", [root], bundles)  # r1 raises inside the loop

    assert status.is_file()  # heartbeat still written despite r1 failure
    assert (bundles / f"{sg.bundle_key(r2)}@hostx.bundle").is_file()  # r2 processed


# ---------- linked worktrees (per-worktree wip refs) ----------
#
# Sibling worktrees share the repo's origin, so without a per-worktree suffix
# every worktree of a repo force-pushes the SAME wip/<host> branch — the
# alphabetically-last one scanned silently replaces the main checkout's
# snapshot (observed clobbering 16k+ lines of main-checkout WIP).


def test_wip_ref_suffix_main_vs_worktree(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "hello")
    wt = tmp_path / "r-feature"
    git(r, "worktree", "add", "-q", "-b", "feature", str(wt))
    assert sg.wip_ref_suffix(r) == ""
    assert sg.wip_ref_suffix(wt) == "@r-feature"


def test_push_wip_worktree_does_not_clobber_main_snapshot(tmp_path):
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare), check=False)
    r = init_repo(tmp_path / "r", origin=bare)
    commit_file(r, "a.txt", "hello")
    git(r, "push", "-q", "origin", "main")
    wt = tmp_path / "r-zzz"
    git(r, "worktree", "add", "-q", "-b", "zzz", str(wt))
    (r / "main_wip.txt").write_text("main checkout WIP")
    (wt / "wt_wip.txt").write_text("worktree WIP")

    sg.push_wip("r", r, "hostx")
    sg.push_wip("r-zzz", wt, "hostx")  # scanned later (sorts after main checkout)

    main_files = ls_tree_files(bare, "refs/heads/wip/hostx")
    assert "main_wip.txt" in main_files  # the regression: this got clobbered
    assert "wt_wip.txt" not in main_files
    wt_files = ls_tree_files(bare, "refs/heads/wip/hostx@r-zzz")
    assert "wt_wip.txt" in wt_files
    assert "main_wip.txt" not in wt_files


def test_wip_only_main_covers_main_and_worktree(tmp_path, monkeypatch):
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare), check=False)
    gh = tmp_path / "gh"
    monkeypatch.setattr(sg, "GH_DIR", gh)
    monkeypatch.setattr(sg, "PUBLIC_DIR", gh / "public")
    monkeypatch.setattr(sg, "ARCHIVED_DIR", gh / "archived")
    monkeypatch.setattr(sg, "ARCHIVED_PUBLIC_DIR", gh / "archived" / "public")
    monkeypatch.setattr(sg, "WIP_STATUS_FILE", tmp_path / "var" / "wip.status")
    r = init_repo(gh / "r", origin=bare)
    commit_file(r, "a.txt", "hello")
    git(r, "push", "-q", "origin", "main")
    wt = gh / "r-zzz"
    git(r, "worktree", "add", "-q", "-b", "zzz", str(wt))
    (r / "main_wip.txt").write_text("m")
    (wt / "wt_wip.txt").write_text("w")

    sg.wip_only_main("hostx", [gh], tmp_path / "bundles")

    assert "main_wip.txt" in ls_tree_files(bare, "refs/heads/wip/hostx")
    assert "wt_wip.txt" in ls_tree_files(bare, "refs/heads/wip/hostx@r-zzz")


def test_bundle_wip_worktree_suffixed_ref_no_shared_ref_race(tmp_path):
    # refs/wip/<host> lives in the SHARED repo storage, so an unsuffixed ref
    # would let a sibling worktree move it between the main repo's update-ref
    # and its bundle write, bundling the wrong tree under the main repo's key.
    r = init_repo(tmp_path / "Projects" / "notes")
    commit_file(r, "a.txt", "hello")
    wt = tmp_path / "Projects" / "notes-fix"
    git(r, "worktree", "add", "-q", "-b", "fix", str(wt))
    (r / "main_wip.txt").write_text("m")
    (wt / "wt_wip.txt").write_text("w")
    bundles = tmp_path / "bundles"

    sg.bundle_wip("notes", r, "hostx", bundles)
    sg.bundle_wip("notes-fix", wt, "hostx", bundles)

    # the worktree's bundle run must not have moved the main repo's wip ref
    main_ref = ls_tree_files(r, "refs/wip/hostx")
    assert "main_wip.txt" in main_ref
    assert "wt_wip.txt" not in main_ref
    # the worktree's own WIP restores from its bundle under the suffixed ref
    check = init_repo(tmp_path / "check")
    git(
        check,
        "fetch",
        str(bundles / f"{sg.bundle_key(wt)}@hostx.bundle"),
        "refs/wip/hostx@notes-fix:refs/x",
    )
    assert "wt_wip.txt" in ls_tree_files(check, "refs/x")


# ---------- pruning orphaned wip refs / bundles ----------
#
# Removing a worktree (typically after its branch merges) or deleting a repo
# leaves its last wip snapshot behind forever — a ref on origin, or a bundle
# file Syncthing replicates to every machine. Each host prunes its OWN
# orphans after a grace period (WIP_PRUNE_GRACE_DAYS — recovery window for a
# worktree removed while still carrying unmerged WIP).


def push_wip_ref(repo, bare, ref, *, days_old):
    """Force-push a snapshot commit with a backdated committer date."""
    date = f"{int(time.time()) - days_old * 86400}"
    tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    sha = subprocess.run(
        ["git", "-C", str(repo), "commit-tree", tree, "-m", "old snapshot"],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "GIT_COMMITTER_DATE": date, "GIT_AUTHOR_DATE": date},
    ).stdout.strip()
    git(repo, "push", "-q", "origin", f"+{sha}:{ref}")


def remote_refs(bare):
    out = git(bare, "for-each-ref", "--format=%(refname)").stdout
    return set(out.splitlines())


def test_prune_deletes_orphaned_worktree_ref_after_grace(tmp_path):
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare), check=False)
    r = init_repo(tmp_path / "r", origin=bare)
    commit_file(r, "a.txt", "hello")
    git(r, "push", "-q", "origin", "main")
    push_wip_ref(r, bare, "refs/heads/wip/hostx@r-gone", days_old=40)

    sg.prune_wip_refs(r, "hostx")

    assert "refs/heads/wip/hostx@r-gone" not in remote_refs(bare)


def test_prune_keeps_young_orphan_and_other_hosts(tmp_path):
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare), check=False)
    r = init_repo(tmp_path / "r", origin=bare)
    commit_file(r, "a.txt", "hello")
    git(r, "push", "-q", "origin", "main")
    push_wip_ref(r, bare, "refs/heads/wip/hostx@r-young", days_old=5)
    push_wip_ref(r, bare, "refs/heads/wip/otherhost@r-gone", days_old=40)

    sg.prune_wip_refs(r, "hostx")

    kept = remote_refs(bare)
    assert "refs/heads/wip/hostx@r-young" in kept  # inside grace window
    assert "refs/heads/wip/otherhost@r-gone" in kept  # never touch other hosts


def test_prune_keeps_ref_for_existing_worktree(tmp_path):
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare), check=False)
    r = init_repo(tmp_path / "r", origin=bare)
    commit_file(r, "a.txt", "hello")
    git(r, "push", "-q", "origin", "main")
    wt = tmp_path / "r-live"
    git(r, "worktree", "add", "-q", "-b", "live", str(wt))
    push_wip_ref(r, bare, "refs/heads/wip/hostx@r-live", days_old=40)

    sg.prune_wip_refs(r, "hostx")

    assert "refs/heads/wip/hostx@r-live" in remote_refs(bare)


def test_prune_throttled_to_daily(tmp_path):
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare), check=False)
    r = init_repo(tmp_path / "r", origin=bare)
    commit_file(r, "a.txt", "hello")
    git(r, "push", "-q", "origin", "main")

    sg.prune_wip_refs(r, "hostx")  # first run writes the stamp
    push_wip_ref(r, bare, "refs/heads/wip/hostx@r-gone", days_old=40)
    sg.prune_wip_refs(r, "hostx")  # within interval — must skip
    assert "refs/heads/wip/hostx@r-gone" in remote_refs(bare)

    git_dir = Path(git(r, "rev-parse", "--absolute-git-dir").stdout.strip())
    (git_dir / "wip-prune-hostx.stamp").unlink()
    sg.prune_wip_refs(r, "hostx")  # stamp gone — prunes
    assert "refs/heads/wip/hostx@r-gone" not in remote_refs(bare)


def test_bundle_prune_deletes_orphan_after_grace(tmp_path):
    live = init_repo(tmp_path / "root" / "alive")
    commit_file(live, "a.txt", "x")
    bundles = tmp_path / "bundles"
    bundles.mkdir()
    old = time.time() - 40 * 86400
    for name in ("root-gone@hostx.bundle", "root-gone@otherhost.bundle"):
        (bundles / name).write_bytes(b"stub")
        os.utime(bundles / name, (old, old))
    (bundles / "root-gone@hostx-young.bundle").write_bytes(b"stub")  # young orphan
    sg.bundle_wip("alive", live, "hostx", bundles)  # live repo's own bundle
    live_bundle = bundles / f"{sg.bundle_key(live)}@hostx.bundle"
    os.utime(live_bundle, (old, old))  # old mtime but repo still exists

    sg.prune_wip_bundles("hostx", [tmp_path / "root"], bundles)
    names = {p.name for p in bundles.iterdir()}

    assert "root-gone@hostx.bundle" not in names  # orphan past grace: pruned
    assert "root-gone@otherhost.bundle" in names  # other host: never touched
    assert "root-gone@hostx-young.bundle" in names  # different host token
    assert live_bundle.name in names  # repo exists: kept regardless of age


def test_bundle_prune_keeps_young_orphan(tmp_path):
    bundles = tmp_path / "bundles"
    bundles.mkdir()
    (bundles / "root-gone@hostx.bundle").write_bytes(b"stub")  # fresh mtime
    sg.prune_wip_bundles("hostx", [tmp_path / "empty"], bundles)
    assert (bundles / "root-gone@hostx.bundle").is_file()
