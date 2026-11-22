"""sync-gh.py's full run (the GitHub-listing path) and the snapshot's index isolation.

The full run is where public repos must never get a wip/ branch pushed: a
snapshot of a public repo's working tree on a public remote would publish
uncommitted (possibly private) work.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SRC = (
    Path(__file__).resolve().parents[1] / "dot_local" / "bin" / "executable_sync-gh.py"
)
spec = importlib.util.spec_from_file_location("sync_gh_full", SRC)
sg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sg)


def git(dest, *args):
    return subprocess.run(
        ["git", "-C", str(dest), *args], capture_output=True, text=True, check=True
    )


def _repo(name, owner="jasonluther", private=True, archived=False):
    return {
        "name": name,
        "nameWithOwner": f"{owner}/{name}",
        "isPrivate": private,
        "isArchived": archived,
        "url": f"https://github.com/{owner}/{name}",
    }


@pytest.fixture
def full_run(tmp_path, monkeypatch):
    """Run main() against a fake GitHub listing; return {action: [repo names]}."""
    gh = tmp_path / "gh"
    monkeypatch.setattr(sg, "GH_DIR", gh)
    monkeypatch.setattr(sg, "PUBLIC_DIR", gh / "public")
    monkeypatch.setattr(sg, "ARCHIVED_DIR", gh / "archived")
    monkeypatch.setattr(sg, "ARCHIVED_PUBLIC_DIR", gh / "archived" / "public")
    monkeypatch.setattr(
        sg,
        "ALL_REPO_DIRS",
        [gh, gh / "public", gh / "archived", gh / "archived" / "public"],
    )
    monkeypatch.setattr(sg, "sanitized_hostname", lambda: "hostA")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    calls = {"clone": [], "pull": [], "push_wip": []}
    monkeypatch.setattr(
        sg, "clone_repo", lambda name, url, dest: calls["clone"].append(name)
    )
    monkeypatch.setattr(sg, "pull_repo", lambda name, dest: calls["pull"].append(name))
    monkeypatch.setattr(
        sg, "push_wip", lambda name, dest, host: calls["push_wip"].append(name)
    )

    def run(repos, *argv, create=True):
        for repo in repos if create else ():
            sg.repo_dir(repo).joinpath(repo["name"]).mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(sg, "get_repos", lambda: repos)
        monkeypatch.setattr(sys, "argv", ["sync-gh.py", *argv])
        sg.main()
        return calls

    return run


def test_full_run_pushes_wip_for_private_repos_only(full_run):
    calls = full_run(
        [_repo("priv"), _repo("pub", private=False), _repo("old", archived=True)]
    )
    assert calls["push_wip"] == ["priv"]
    assert sorted(calls["pull"]) == ["priv", "pub"]


def test_full_run_honours_wip_exclude(full_run, tmp_path):
    (tmp_path / "cfg" / "sync-gh").mkdir(parents=True)
    (tmp_path / "cfg" / "sync-gh" / "wip-exclude").write_text("Acme-Corp\n")
    calls = full_run([_repo("priv"), _repo("client", owner="acme-corp")])
    assert calls["push_wip"] == ["priv"]


def test_no_push_wip_pushes_nothing(full_run):
    assert full_run([_repo("priv")], "--no-push-wip")["push_wip"] == []


def test_repos_land_in_the_directory_for_their_visibility(tmp_path, monkeypatch):
    gh = tmp_path / "gh"
    monkeypatch.setattr(sg, "GH_DIR", gh)
    monkeypatch.setattr(sg, "PUBLIC_DIR", gh / "public")
    monkeypatch.setattr(sg, "ARCHIVED_DIR", gh / "archived")
    monkeypatch.setattr(sg, "ARCHIVED_PUBLIC_DIR", gh / "archived" / "public")
    assert sg.repo_dir(_repo("a")) == gh
    assert sg.repo_dir(_repo("a", private=False)) == gh / "public"
    assert sg.repo_dir(_repo("a", archived=True)) == gh / "archived"
    assert (
        sg.repo_dir(_repo("a", private=False, archived=True))
        == gh / "archived" / "public"
    )


def test_snapshot_leaves_the_real_index_alone(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.name", "t")
    git(r, "config", "user.email", "t@t.test")
    git(r, "commit", "-q", "--allow-empty", "-m", "c")
    (r / "staged.txt").write_text("staged")
    git(r, "add", "staged.txt")
    (r / "loose.txt").write_text("not staged")
    before = git(r, "status", "--porcelain").stdout
    assert sg.snapshot_commit(r, "m")
    assert git(r, "status", "--porcelain").stdout == before


def test_the_script_arms_a_whole_run_timeout_before_doing_anything():
    # launchd never restarts a still-running agent, so a hung run would
    # silently skip every later snapshot. The alarm must be set first.
    probe = (
        "import runpy, signal, sys\n"
        "def alarm(seconds):\n"
        "    print(seconds); sys.exit(0)\n"
        "signal.alarm = alarm\n"
        f"runpy.run_path({str(SRC)!r}, run_name='__main__')\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.stdout.strip() == str(sg.RUN_TIMEOUT), done.stderr
    assert 0 < sg.RUN_TIMEOUT <= 3600


def _clone_of(path, owner, name):
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(path, "remote", "add", "origin", f"https://github.com/{owner}/{name}.git")


def test_same_name_under_two_owners_does_not_move_either(full_run, tmp_path):
    # jasonluther/awth (archived) and kilotronic/awth (public) share a name. The
    # move step used to shove each one into the other's folder, nesting a copy
    # one level deeper every run until shutil.move hit an existing path.
    gh = tmp_path / "gh"
    _clone_of(gh / "archived" / "awth", "jasonluther", "awth")
    _clone_of(gh / "public" / "awth", "kilotronic", "awth")
    full_run(
        [
            _repo("awth", archived=True),
            _repo("awth", owner="kilotronic", private=False),
        ],
        create=False,
    )
    assert sg.origin_owner(gh / "archived" / "awth") == "jasonluther"
    assert sg.origin_owner(gh / "public" / "awth") == "kilotronic"
    assert not (gh / "public" / "awth" / "awth").exists()
    assert not (gh / "archived" / "awth" / "awth").exists()


def test_misplaced_repo_is_not_moved_into_an_existing_folder(full_run, tmp_path):
    gh = tmp_path / "gh"
    _clone_of(gh / "stale", "jasonluther", "stale")
    _clone_of(gh / "archived" / "stale", "jasonluther", "stale")
    full_run([_repo("stale", archived=True)], create=False)
    assert (gh / "stale").is_dir()
    assert not (gh / "archived" / "stale" / "stale").exists()


def test_misplaced_repo_still_moves(full_run, tmp_path):
    gh = tmp_path / "gh"
    _clone_of(gh / "gone", "jasonluther", "gone")
    full_run([_repo("gone", archived=True)], create=False)
    assert not (gh / "gone").exists()
    assert sg.origin_owner(gh / "archived" / "gone") == "jasonluther"
