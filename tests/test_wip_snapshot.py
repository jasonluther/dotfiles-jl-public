"""Tests for sync-gh.py WIP snapshot engine. Run: pytest -q test_sync_gh.py"""

import importlib.util
import os
import subprocess
import time
from pathlib import Path

import pytest

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
    sg.push_wip("r", r, "hostx")  # nothing origin lacks: the old ref goes
    assert git(bare, "rev-parse", "refs/heads/wip/hostx", check=False).returncode


def test_push_wip_skips_empty_origin(tmp_path):
    # A just-created remote: a wip push would become its default branch.
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare), check=False)
    r = init_repo(tmp_path / "r", origin=bare)
    commit_file(r, "a.txt", "hello")
    (r / "wip_new.txt").write_text("in progress")
    sg.push_wip("r", r, "hostx")
    assert git(bare, "for-each-ref", "refs/heads/").stdout.strip() == ""


def test_push_wip_skips_origin_with_only_wip_branches(tmp_path):
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare), check=False)
    r = init_repo(tmp_path / "r", origin=bare)
    commit_file(r, "a.txt", "hello")
    git(r, "push", "-q", "origin", "HEAD:refs/heads/wip/otherhost")
    (r / "wip_new.txt").write_text("in progress")
    sg.push_wip("r", r, "hostx")
    heads = git(
        bare, "for-each-ref", "--format=%(refname)", "refs/heads/"
    ).stdout.split()
    assert heads == ["refs/heads/wip/otherhost"]


def test_push_wip_proceeds_once_main_pushed_without_fetch(tmp_path):
    # Pushed main but never fetched: no local origin refs, so origin is asked.
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare), check=False)
    r = init_repo(tmp_path / "r", origin=bare)
    commit_file(r, "a.txt", "hello")
    git(
        bare, "fetch", "-q", str(r), "main:main"
    )  # main lands without a local origin/main
    assert git(r, "for-each-ref", "refs/remotes/").stdout.strip() == ""
    (r / "wip_new.txt").write_text("in progress")
    sg.push_wip("r", r, "hostx")
    assert "wip_new.txt" in ls_tree_files(bare, "refs/heads/wip/hostx")


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

    cfg = tmp_path / "cfg"
    (cfg / "sync-gh").mkdir(parents=True)
    (cfg / "sync-gh" / "wip-exclude").write_text("# private\nAcme-Corp\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg))
    excluded = init_repo(gh / "excl")
    sg._git(excluded, ["remote", "add", "origin", "https://github.com/acme-corp/x.git"])
    assert sg.classify_repo(excluded) == "skip"
    monkeypatch.setattr(sg, "_probe_visibility", lambda slug: "private")
    ssh = init_repo(gh / "ssh")
    sg._git(ssh, ["remote", "add", "origin", "git@github.com:kilotronic/x.git"])
    assert sg.classify_repo(ssh) == "push"


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


def test_push_wip_dirty_unchanged_does_not_repush(tmp_path):
    # A snapshot commit gets a fresh timestamp (so a fresh SHA) every run;
    # re-pushing it every 5 minutes made every dirty repo look updated on GitHub.
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare), check=False)
    r = init_repo(tmp_path / "r", origin=bare)
    commit_file(r, "a.txt", "hello")
    git(r, "push", "-q", "origin", "main")
    (r / "wip_new.txt").write_text("in progress")
    sg.push_wip("r", r, "hostx")
    first = git(bare, "rev-parse", "refs/heads/wip/hostx").stdout.strip()
    time.sleep(1.1)  # commit timestamps have 1s resolution
    sg.push_wip("r", r, "hostx")
    assert git(bare, "rev-parse", "refs/heads/wip/hostx").stdout.strip() == first
    (r / "wip_new.txt").write_text("more progress")
    sg.push_wip("r", r, "hostx")
    assert git(bare, "rev-parse", "refs/heads/wip/hostx").stdout.strip() != first


# ---------- never push WIP to a public GitHub repo ----------


@pytest.fixture(autouse=True)
def _fresh_probe_state(monkeypatch):
    # _probe_failed lasts one process (one sweep); each test is a fresh sweep.
    monkeypatch.setattr(sg, "_probe_failed", False)


def _gh_repo(path, slug):
    r = init_repo(path)
    sg._git(r, ["remote", "add", "origin", f"https://github.com/{slug}.git"])
    return r


def test_classify_bundles_a_public_github_repo_under_gh_dir(tmp_path, monkeypatch):
    # A public repo cloned straight into ~/Code/gh was treated as private by
    # its folder alone, so its uncommitted work was pushed where anyone can read it.
    gh = tmp_path / "gh"
    monkeypatch.setattr(sg, "GH_DIR", gh)
    vis = {"me/pub": "public", "me/priv": "private", "me/unknown": None}
    monkeypatch.setattr(sg, "_probe_visibility", lambda slug: vis[slug])
    assert sg.classify_repo(_gh_repo(gh / "pub", "me/pub")) == "bundle"
    assert sg.classify_repo(_gh_repo(gh / "priv", "me/priv")) == "push"
    # Offline or rate-limited: don't push on a guess.
    assert sg.classify_repo(_gh_repo(gh / "unknown", "me/unknown")) == "bundle"


def test_visibility_is_cached_and_rechecked_after_ttl(tmp_path, monkeypatch):
    calls = []

    def probe(slug):
        calls.append(slug)
        return "private"

    monkeypatch.setattr(sg, "_probe_visibility", probe)
    r = _gh_repo(tmp_path / "r", "me/r")
    assert sg.github_visibility(r) == "private"
    assert sg.github_visibility(r) == "private"
    assert calls == ["me/r"]
    cache = Path(git(r, "rev-parse", "--absolute-git-dir").stdout.strip()) / (
        "wip-visibility"
    )
    old = time.time() - sg.VISIBILITY_TTL - 1
    os.utime(cache, (old, old))
    assert sg.github_visibility(r) == "private"
    assert calls == ["me/r", "me/r"]


def test_unknown_visibility_is_not_cached(tmp_path, monkeypatch):
    answers = iter([None, "public"])
    monkeypatch.setattr(sg, "_probe_visibility", lambda slug: next(answers))
    r = _gh_repo(tmp_path / "r", "me/r")
    assert sg.github_visibility(r) is None
    monkeypatch.setattr(sg, "_probe_failed", False)  # next sweep
    assert sg.github_visibility(r) == "public"


def test_one_unanswered_probe_stops_probing_for_the_run(tmp_path, monkeypatch):
    # On a network that swallows requests each probe waits PROBE_TIMEOUT; doing
    # that for every repo would make one sweep outlast the 5-minute interval.
    calls = []

    def probe(slug):
        calls.append(slug)

    monkeypatch.setattr(sg, "_probe_visibility", probe)
    monkeypatch.setattr(sg, "_probe_failed", False)
    a = _gh_repo(tmp_path / "a", "me/a")
    b = _gh_repo(tmp_path / "b", "me/b")
    assert sg.github_visibility(a) is None
    assert sg.github_visibility(b) is None
    assert calls == ["me/a"]


# ---------- what a snapshot leaves out ----------


def test_snapshot_leaves_out_secrets_whatever_gitignore_says(tmp_path):
    # A .env the repo's .gitignore missed went into a Syncthing-shared bundle.
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "hello")
    (r / "sub").mkdir()
    for name in (".env", ".env.local", ".envrc", "server.pem", "id.key", "sub/.env"):
        (r / name).write_text("SECRET")
    for name in (".env.example", ".env.sample", "keep.py"):
        (r / name).write_text("fine")
    files = ls_tree_files(r, sg.snapshot_commit(r, "m"))
    assert {".env.example", ".env.sample", "keep.py"} <= files
    assert not files & {".env", ".env.local", ".envrc", "server.pem", "id.key"}
    assert "sub/.env" not in files


def test_snapshot_keeps_a_committed_secret_file_at_its_committed_version(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, ".env", "OLD")
    (r / ".env").write_text("NEW_SECRET")
    git(r, "add", ".env")
    (r / "work.txt").write_text("w")
    sha = sg.snapshot_commit(r, "m")
    for rev in git(r, "rev-list", sha, "--not", "HEAD").stdout.split():
        assert git(r, "show", f"{rev}:.env").stdout == "OLD"


def test_snapshot_secret_alone_is_nothing_to_snapshot(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "hello")
    (r / ".env").write_text("SECRET")
    git(r, "add", ".env")
    assert sg.snapshot_commit(r, "m") is None


def test_snapshot_ignores_mode_only_changes(tmp_path):
    # One checkout had 3,400 files whose only change was the executable bit.
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.sh", "echo hi")
    (r / "a.sh").chmod(0o755)
    assert git(r, "status", "--porcelain").stdout.strip() == "M a.sh"
    assert sg.snapshot_commit(r, "m") is None
    git(r, "add", "a.sh")  # staged mode change too
    assert sg.snapshot_commit(r, "m") is None


def test_snapshot_keeps_a_content_change_with_a_mode_change(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.sh", "echo hi")
    (r / "a.sh").write_text("echo bye")
    (r / "a.sh").chmod(0o755)
    sha = sg.snapshot_commit(r, "m")
    assert git(r, "show", f"{sha}:a.sh").stdout == "echo bye"


def test_snapshot_leaves_out_a_nested_clone(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "hello")
    inner = init_repo(r / "vendor" / "inner")
    commit_file(inner, "x.txt", "x")
    (r / "real.txt").write_text("work")
    files = ls_tree_files(r, sg.snapshot_commit(r, "m"))
    assert "real.txt" in files
    assert not any(f.startswith("vendor") for f in files)


def test_snapshot_leaves_out_agent_tool_installs(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "hello")
    (r / ".claude" / "skills" / "mine").mkdir(parents=True)
    commit_file(r, ".claude/skills/mine/SKILL.md", "v1")
    noise = (
        ".agents/tool/x.md",
        ".claude/skills/installed/SKILL.md",
        "skills-lock.json",
        ".claude/worktrees/wt/f.txt",
        ".claude/settings.local.json",
    )
    for name in noise:
        (r / name).parent.mkdir(parents=True, exist_ok=True)
        (r / name).write_text("noise")
    assert sg.snapshot_commit(r, "m") is None
    (r / ".claude" / "settings.json").write_text("{}")
    (r / ".claude/skills/mine/SKILL.md").write_text("v2")  # the repo's own skill
    sha = sg.snapshot_commit(r, "m")
    files = ls_tree_files(r, sha)
    assert not files & set(noise)
    assert ".claude/settings.json" in files
    assert git(r, "show", f"{sha}:.claude/skills/mine/SKILL.md").stdout == "v2"


# ---------- the real index (staged changes) ----------


def test_snapshot_keeps_a_staged_version_that_differs_from_the_working_copy(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "v0")
    (r / "a.txt").write_text("v1")
    git(r, "add", "a.txt")
    (r / "a.txt").write_text("v2")
    sha = sg.snapshot_commit(r, "m")
    head = git(r, "rev-parse", "HEAD").stdout.strip()
    assert git(r, "show", f"{sha}:a.txt").stdout == "v2"
    assert git(r, "rev-parse", f"{sha}^1").stdout.strip() == head
    assert git(r, "show", f"{sha}^2:a.txt").stdout == "v1"
    assert git(r, "rev-parse", f"{sha}^2^").stdout.strip() == head


def test_snapshot_keeps_a_staged_file_gone_from_disk(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "v0")
    (r / "new.txt").write_text("staged only")
    git(r, "add", "new.txt")
    (r / "new.txt").unlink()
    sha = sg.snapshot_commit(r, "m")
    assert sha
    assert git(r, "show", f"{sha}^2:new.txt").stdout == "staged only"


def test_snapshot_has_no_index_parent_when_the_index_adds_nothing(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "v0")
    (r / "a.txt").write_text("unstaged")
    sha = sg.snapshot_commit(r, "m")
    assert git(r, "rev-parse", "--verify", "-q", f"{sha}^2", check=False).returncode
    git(r, "add", "a.txt")  # index == working tree
    sha = sg.snapshot_commit(r, "m")
    assert git(r, "rev-parse", "--verify", "-q", f"{sha}^2", check=False).returncode


def test_snapshot_in_an_unborn_repo_keeps_the_index(tmp_path):
    r = init_repo(tmp_path / "r")
    (r / "a.txt").write_text("v1")
    git(r, "add", "a.txt")
    (r / "a.txt").write_text("v2")
    sha = sg.snapshot_commit(r, "m")
    assert git(r, "show", f"{sha}:a.txt").stdout == "v2"
    assert git(r, "show", f"{sha}^:a.txt").stdout == "v1"


def test_snapshot_of_an_empty_unborn_repo_is_none(tmp_path):
    r = init_repo(tmp_path / "r")
    assert sg.snapshot_commit(r, "m") is None


def test_snapshot_leaves_out_a_mass_staged_deletion(tmp_path, capsys):
    # An emptied index (every file staged for deletion, all still on disk)
    # produced a 113 MB staged diff.
    r = init_repo(tmp_path / "r")
    for i in range(60):
        (r / f"f{i}.txt").write_text(str(i))
    git(r, "add", ".")
    git(r, "commit", "-q", "-m", "c")
    git(r, "rm", "-r", "-q", "--cached", ".")
    assert sg.snapshot_commit(r, "m") is None
    assert "stages deletion of 60 of 60 files" in capsys.readouterr().out
    (r / "f0.txt").write_text("edited")
    sha = sg.snapshot_commit(r, "m")
    assert git(r, "show", f"{sha}:f0.txt").stdout == "edited"
    assert git(r, "rev-parse", "--verify", "-q", f"{sha}^2", check=False).returncode


def test_snapshot_keeps_a_small_staged_deletion(tmp_path):
    r = init_repo(tmp_path / "r")
    for i in range(60):
        (r / f"f{i}.txt").write_text(str(i))
    git(r, "add", ".")
    git(r, "commit", "-q", "-m", "c")
    git(r, "rm", "-q", "--cached", "f0.txt")
    sha = sg.snapshot_commit(r, "m")
    assert sha
    assert "f0.txt" not in ls_tree_files(r, f"{sha}^2")


def _origin_and_clone(tmp_path):
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare), check=False)
    r = init_repo(tmp_path / "r", origin=bare)
    commit_file(r, "a.txt", "hello")
    git(r, "push", "-q", "-u", "origin", "main")
    return bare, r


def test_push_wip_repushes_when_only_the_index_changed(tmp_path):
    bare, r = _origin_and_clone(tmp_path)
    (r / "a.txt").write_text("v1")
    git(r, "add", "a.txt")
    (r / "a.txt").write_text("v2")
    sg.push_wip("r", r, "hostx")
    assert git(bare, "show", "refs/heads/wip/hostx^2:a.txt").stdout == "v1"
    (r / "a.txt").write_text("v1b")
    git(r, "add", "a.txt")
    (r / "a.txt").write_text("v2")
    sg.push_wip("r", r, "hostx")
    assert git(bare, "show", "refs/heads/wip/hostx^2:a.txt").stdout == "v1b"


# ---------- push only what origin lacks ----------


def test_push_wip_clean_checkout_on_origin_pushes_nothing(tmp_path):
    # 368 of 537 wip branches on GitHub pointed at a HEAD origin already had.
    bare, r = _origin_and_clone(tmp_path)
    sg.push_wip("r", r, "hostx")
    assert git(bare, "rev-parse", "refs/heads/wip/hostx", check=False).returncode


def test_push_wip_clean_checkout_deletes_its_own_stale_wip_ref(tmp_path):
    bare, r = _origin_and_clone(tmp_path)
    wt = tmp_path / "r-wt"
    git(r, "worktree", "add", "-q", "-b", "side", str(wt))
    (r / "w.txt").write_text("x")
    (wt / "w.txt").write_text("x")
    sg.push_wip("r", r, "hostx")
    sg.push_wip("r-wt", wt, "hostx")
    git(r, "push", "-q", "origin", "HEAD:refs/heads/wip/otherhost")
    (r / "w.txt").unlink()  # main checkout is clean again
    sg.push_wip("r", r, "hostx")
    refs = remote_refs(bare)
    assert "refs/heads/wip/hostx" not in refs
    assert "refs/heads/wip/hostx@r-wt" in refs  # a sibling's own ref stays
    assert "refs/heads/wip/otherhost" in refs  # other hosts are never touched
    sg.push_wip("r", r, "hostx")  # nothing left to delete: no error


def test_push_wip_clean_unborn_repo_pushes_nothing(tmp_path, capsys):
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare), check=False)
    seed = init_repo(tmp_path / "seed", origin=bare)
    commit_file(seed, "a.txt", "hello")
    git(seed, "push", "-q", "origin", "main")
    r = init_repo(tmp_path / "r", origin=bare)
    git(r, "fetch", "-q", "origin")
    sg.push_wip("r", r, "hostx")
    assert git(bare, "rev-parse", "refs/heads/wip/hostx", check=False).returncode
    assert "failed" not in capsys.readouterr().out


def test_push_wip_skips_in_progress_in_a_worktree(tmp_path):
    bare, r = _origin_and_clone(tmp_path)
    wt = tmp_path / "r-wt"
    git(r, "worktree", "add", "-q", "-b", "side", str(wt))
    (wt / "w.txt").write_text("x")
    wt_git = Path(git(wt, "rev-parse", "--absolute-git-dir").stdout.strip())
    (wt_git / "MERGE_HEAD").write_text("deadbeef\n")
    sg.push_wip("r-wt", wt, "hostx")
    assert "refs/heads/wip/hostx@r-wt" not in remote_refs(bare)


# ---------- where a snapshot came from ----------


def test_push_wip_message_names_branch_checkout_and_upstream(tmp_path, monkeypatch):
    monkeypatch.setattr(sg, "GH_DIR", tmp_path)
    bare, r = _origin_and_clone(tmp_path)
    (r / "w.txt").write_text("x")
    sg.push_wip("r", r, "hostx")
    msg = git(bare, "log", "-1", "--format=%B", "refs/heads/wip/hostx").stdout
    subject, _, body = msg.partition("\n")
    assert subject == "wip snapshot (hostx)"
    assert "branch: main" in body
    assert "checkout: r" in body
    assert "upstream: origin/main" in body


def test_snapshot_message_outside_gh_dir_and_without_upstream(tmp_path, monkeypatch):
    monkeypatch.setattr(sg, "GH_DIR", tmp_path / "gh")
    r = init_repo(tmp_path / "Projects" / "p")
    msg = sg.snapshot_message(r, "hostx")
    assert msg.startswith("wip snapshot (hostx)\n\n")
    assert "branch: main" in msg
    assert f"checkout: {r}" in msg
    assert "upstream: none" in msg


def test_snapshot_survives_a_nested_repo_with_no_commit(tmp_path):
    # `git add -A` refuses the whole tree when an embedded repo has no commit.
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "hello")
    init_repo(r / "scratch")
    (r / "scratch" / "f.txt").write_text("x")
    (r / "real.txt").write_text("work")
    files = ls_tree_files(r, sg.snapshot_commit(r, "m"))
    assert "real.txt" in files
    assert not any(f.startswith("scratch") for f in files)


def test_bundle_wip_detached_head_says_so_in_the_message(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "one")
    commit_file(r, "a.txt", "two")
    git(r, "checkout", "-q", "HEAD~1")
    (r / "w.txt").write_text("x")
    sg.bundle_wip("r", r, "hostx", tmp_path / "bundles")
    msg = git(r, "log", "-1", "--format=%B", "refs/wip/hostx").stdout
    assert "branch: (detached)" in msg
    assert "w.txt" in ls_tree_files(r, "refs/wip/hostx")


def test_in_progress_op_outside_a_repo_is_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "MERGE_HEAD").write_text("x")
    assert sg.in_progress_op(tmp_path / "missing") is None


# ---------- review fixes ----------


def test_snapshot_fails_loudly_when_a_file_cannot_be_read(tmp_path):
    # --ignore-errors must only forgive a nested repo, not hide a lost edit.
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "hello")
    (r / "a.txt").write_text("edited")
    (r / "a.txt").chmod(0)
    try:
        with pytest.raises(subprocess.CalledProcessError):
            sg.snapshot_commit(r, "m")
    finally:
        (r / "a.txt").chmod(0o644)


def test_snapshot_keeps_new_files_in_a_repos_own_skill(tmp_path):
    r = init_repo(tmp_path / "r")
    (r / ".claude" / "skills" / "mine").mkdir(parents=True)
    commit_file(r, ".claude/skills/mine/SKILL.md", "v1")
    (r / ".claude/skills/mine/notes.md").write_text("new file in my skill")
    (r / ".claude" / "skills" / "new").mkdir()
    (r / ".claude/skills/new/SKILL.md").write_text("a new skill")
    files = ls_tree_files(r, sg.snapshot_commit(r, "m"))
    assert ".claude/skills/mine/notes.md" in files
    # A new skill folder looks like an install until it is staged.
    assert ".claude/skills/new/SKILL.md" not in files
    git(r, "add", ".claude/skills/new/SKILL.md")
    sha = sg.snapshot_commit(r, "m")
    assert ".claude/skills/new/SKILL.md" in ls_tree_files(r, sha)


def test_snapshot_keeps_a_staged_file_in_an_agent_folder(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "hello")
    (r / ".agents").mkdir()
    (r / ".agents" / "AGENTS.md").write_text("mine")
    git(r, "add", "-f", ".agents/AGENTS.md")
    sha = sg.snapshot_commit(r, "m")
    assert ".agents/AGENTS.md" in ls_tree_files(r, sha)


def test_snapshot_secret_names_ignore_case_and_keep_templates(tmp_path):
    r = init_repo(tmp_path / "r")
    commit_file(r, "a.txt", "hello")
    (r / ".ENV").write_text("SECRET")
    (r / "Server.PEM").write_text("SECRET")
    (r / ".env.template").write_text("fine")
    files = ls_tree_files(r, sg.snapshot_commit(r, "m"))
    assert ".env.template" in files
    assert not files & {".ENV", "Server.PEM"}


def test_push_wip_commit_only_on_another_remote_is_pushed(tmp_path):
    bare, r = _origin_and_clone(tmp_path)
    up = tmp_path / "upstream.git"
    git(tmp_path, "init", "-q", "--bare", str(up), check=False)
    git(r, "remote", "add", "upstream", str(up))
    commit_file(r, "b.txt", "two")
    git(r, "push", "-q", "upstream", "main")
    sg.push_wip("r", r, "hostx")
    assert tree_of(bare, "refs/heads/wip/hostx") == tree_of(r, "HEAD")


def test_push_wip_keeps_wip_ref_when_the_branch_is_gone_from_origin(tmp_path):
    # A stale tracking ref (branch deleted on GitHub) still "contains" HEAD.
    bare, r = _origin_and_clone(tmp_path)
    git(r, "checkout", "-q", "-b", "feature")
    commit_file(r, "b.txt", "two")
    git(r, "push", "-q", "-u", "origin", "feature")
    (r / "w.txt").write_text("x")
    sg.push_wip("r", r, "hostx")
    (r / "w.txt").unlink()
    git(bare, "branch", "-D", "feature")  # deleted on origin, still cached here
    sg.push_wip("r", r, "hostx")
    assert "refs/heads/wip/hostx" in remote_refs(bare)


def test_push_wip_unborn_repo_repushes_when_only_the_index_changed(tmp_path):
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare), check=False)
    seed = init_repo(tmp_path / "seed", origin=bare)
    commit_file(seed, "a.txt", "hello")
    git(seed, "push", "-q", "origin", "main")
    r = init_repo(tmp_path / "r", origin=bare)
    git(r, "fetch", "-q", "origin")
    (r / "n.txt").write_text("v1")
    git(r, "add", "n.txt")
    (r / "n.txt").write_text("v2")
    sg.push_wip("r", r, "hostx")
    (r / "n.txt").write_text("v1b")
    git(r, "add", "n.txt")
    (r / "n.txt").write_text("v2")
    sg.push_wip("r", r, "hostx")
    assert git(bare, "show", "refs/heads/wip/hostx^:n.txt").stdout == "v1b"


def test_pull_prunes_deleted_remote_branches(tmp_path):
    bare, r = _origin_and_clone(tmp_path)
    git(r, "config", "fetch.prune", "false")  # a user default must not decide it
    git(r, "push", "-q", "origin", "main:gone")
    git(r, "fetch", "-q", "origin")
    git(bare, "branch", "-D", "gone")
    sg.pull_repo("r", r)
    assert git(r, "rev-parse", "-q", "--verify", "origin/gone", check=False).returncode
