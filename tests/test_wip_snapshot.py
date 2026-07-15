"""Tests for sync-gh.py WIP snapshot engine. Run: pytest -q test_sync_gh.py"""

import importlib.util
import subprocess
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
