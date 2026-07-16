"""Integration tests for the `wip` receive helper."""

import importlib.machinery
import importlib.util
import subprocess
from pathlib import Path

import pytest

SG_SRC = Path(
    "/Users/jason/Code/gh/public/dotfiles-jl-public/dot_local/bin/executable_sync-gh.py"
)
WIP_SRC = Path(
    "/Users/jason/Code/gh/public/dotfiles-jl-public/dot_local/bin/executable_wip"
)


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


sg = _load("sync_gh2", SG_SRC)
wip = _load("wip_tool", WIP_SRC)


def git(dest, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(dest), *args], capture_output=True, text=True, check=check
    )


def init_repo(path, origin=None):
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


def clone(bare, dest):
    subprocess.run(["git", "clone", "-q", str(bare), str(dest)], check=True)
    git(dest, "config", "user.email", "t@t.test")
    git(dest, "config", "user.name", "Test")
    return dest


def test_apply_from_bundle(tmp_path, monkeypatch):
    # Model two machines with the SAME repo path relative to $HOME, so the
    # path-derived bundle key matches across them (as it does on the real fleet).
    bare = tmp_path / "o.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    home_a, home_b = tmp_path / "A", tmp_path / "B"
    A = init_repo(home_a / "proj" / "myrepo", origin=bare)
    commit_file(A, "a.txt", "hello")
    git(A, "push", "-q", "origin", "main")
    (A / "wipfile.txt").write_text("from A")  # uncommitted WIP
    bundles = tmp_path / "bundles"
    monkeypatch.setenv("HOME", str(home_a))
    sg.bundle_wip("myrepo", A, "hostA", bundles)

    monkeypatch.setenv("HOME", str(home_b))
    B = clone(bare, home_b / "proj" / "myrepo")
    monkeypatch.setattr(wip, "WIP_BUNDLE_DIR", bundles)
    monkeypatch.setattr(wip.socket, "gethostname", lambda: "hostB")
    monkeypatch.chdir(B)
    assert "hostA" in wip.gather_snapshots("hostB")
    assert wip.cmd_apply("hostB", "hostA", force=False) == 0
    assert (B / "wipfile.txt").read_text() == "from A"


def test_apply_from_pushed_branch(tmp_path, monkeypatch):
    bare = tmp_path / "o.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    A = init_repo(tmp_path / "hostA" / "myrepo", origin=bare)
    commit_file(A, "a.txt", "hello")
    git(A, "push", "-q", "origin", "main")
    (A / "wipfile.txt").write_text("from A")
    sg.push_wip("myrepo", A, "hostA")

    B = clone(bare, tmp_path / "hostB" / "myrepo")
    monkeypatch.setattr(wip, "WIP_BUNDLE_DIR", tmp_path / "none")
    monkeypatch.setattr(wip.socket, "gethostname", lambda: "hostB")
    monkeypatch.chdir(B)
    assert "hostA" in wip.gather_snapshots("hostB")
    assert wip.cmd_apply("hostB", "hostA", force=False) == 0
    assert (B / "wipfile.txt").read_text() == "from A"


def test_apply_refuses_dirty_tree(tmp_path, monkeypatch):
    bare = tmp_path / "o.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    A = init_repo(tmp_path / "hostA" / "myrepo", origin=bare)
    commit_file(A, "a.txt", "hello")
    git(A, "push", "-q", "origin", "main")
    (A / "wipfile.txt").write_text("from A")
    sg.push_wip("myrepo", A, "hostA")

    B = clone(bare, tmp_path / "hostB" / "myrepo")
    (B / "local_change.txt").write_text("mine")  # dirty
    monkeypatch.setattr(wip, "WIP_BUNDLE_DIR", tmp_path / "none")
    monkeypatch.setattr(wip.socket, "gethostname", lambda: "hostB")
    monkeypatch.chdir(B)
    with pytest.raises(SystemExit):
        wip.cmd_apply("hostB", "hostA", force=False)
    # --force applies anyway
    assert wip.cmd_apply("hostB", "hostA", force=True) == 0
    assert (B / "wipfile.txt").read_text() == "from A"


def test_own_host_excluded(tmp_path, monkeypatch):
    bare = tmp_path / "o.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    A = init_repo(tmp_path / "hostA" / "myrepo", origin=bare)
    commit_file(A, "a.txt", "hello")
    git(A, "push", "-q", "origin", "main")
    (A / "w.txt").write_text("x")
    sg.push_wip("myrepo", A, "hostA")
    B = clone(bare, tmp_path / "hostB" / "myrepo")
    monkeypatch.setattr(wip, "WIP_BUNDLE_DIR", tmp_path / "none")
    monkeypatch.setattr(wip.socket, "gethostname", lambda: "hostA")  # same host!
    monkeypatch.chdir(B)
    assert wip.gather_snapshots("hostA") == {}  # never offer your own snapshot


def test_worktree_snapshot_listed_and_applies(tmp_path, monkeypatch):
    # A worktree on hostA pushes wip/hostA@myrepo-fix; hostB sees that token
    # and can apply it like any other snapshot.
    bare = tmp_path / "o.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    A = init_repo(tmp_path / "hostA" / "myrepo", origin=bare)
    commit_file(A, "a.txt", "hello")
    git(A, "push", "-q", "origin", "main")
    wt = tmp_path / "hostA" / "myrepo-fix"
    git(A, "worktree", "add", "-q", "-b", "fix", str(wt))
    (wt / "wt_wip.txt").write_text("from A's worktree")
    sg.push_wip("myrepo-fix", wt, "hostA")

    B = clone(bare, tmp_path / "hostB" / "myrepo")
    monkeypatch.setattr(wip, "WIP_BUNDLE_DIR", tmp_path / "none")
    monkeypatch.setattr(wip.socket, "gethostname", lambda: "hostB")
    monkeypatch.chdir(B)
    snaps = wip.gather_snapshots("hostB")
    assert "hostA@myrepo-fix" in snaps
    assert wip.cmd_apply("hostB", "hostA@myrepo-fix", force=False) == 0
    assert (B / "wt_wip.txt").read_text() == "from A's worktree"


def test_own_worktree_snapshot_excluded(tmp_path, monkeypatch):
    # wip/hostA@somewt is still hostA's own state — never offered back to hostA.
    bare = tmp_path / "o.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    A = init_repo(tmp_path / "hostA" / "myrepo", origin=bare)
    commit_file(A, "a.txt", "hello")
    git(A, "push", "-q", "origin", "main")
    wt = tmp_path / "hostA" / "myrepo-fix"
    git(A, "worktree", "add", "-q", "-b", "fix", str(wt))
    (wt / "w.txt").write_text("x")
    sg.push_wip("myrepo-fix", wt, "hostA")
    monkeypatch.setattr(wip, "WIP_BUNDLE_DIR", tmp_path / "none")
    monkeypatch.setattr(wip.socket, "gethostname", lambda: "hostA")
    monkeypatch.chdir(A)
    assert wip.gather_snapshots("hostA") == {}


def test_apply_from_worktree_bundle(tmp_path, monkeypatch):
    # Bundles from a worktree carry a suffixed internal ref; the receive side
    # must discover it from the bundle rather than assuming refs/wip/<host>.
    home_a, home_b = tmp_path / "A", tmp_path / "B"
    A = init_repo(home_a / "proj" / "myrepo")
    commit_file(A, "a.txt", "hello")
    wt = home_a / "proj" / "myrepo-fix"
    git(A, "worktree", "add", "-q", "-b", "fix", str(wt))
    (wt / "wt_wip.txt").write_text("from A's worktree")
    bundles = tmp_path / "bundles"
    monkeypatch.setenv("HOME", str(home_a))
    sg.bundle_wip("myrepo-fix", wt, "hostA", bundles)

    # hostB has an ordinary checkout at the same HOME-relative path
    monkeypatch.setenv("HOME", str(home_b))
    B = init_repo(home_b / "proj" / "myrepo-fix")
    commit_file(B, "a.txt", "hello")
    monkeypatch.setattr(wip, "WIP_BUNDLE_DIR", bundles)
    monkeypatch.setattr(wip.socket, "gethostname", lambda: "hostB")
    monkeypatch.chdir(B)
    snaps = wip.gather_snapshots("hostB")
    assert "hostA" in snaps
    assert wip.cmd_apply("hostB", "hostA", force=False) == 0
    assert (B / "wt_wip.txt").read_text() == "from A's worktree"
