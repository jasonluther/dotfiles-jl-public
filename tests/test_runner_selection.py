"""Public repositories run CI on GitHub-hosted runners only.

vars.RUNS_ON may send jobs to the owner's self-hosted runners, but only
while the repository is private: a public repository's jobs (pull requests
from strangers included) always land on ubuntu-latest. This covers this
repo's own workflows and the copier templates' CI and set-runner.sh.
"""

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ["python-uv", "python-uv-with-js"]
WORKFLOWS = sorted((ROOT / ".github/workflows").glob("*.yml")) + [
    ROOT / f"templates/{t}/.github/workflows/ci.yml.jinja" for t in TEMPLATES
]
PRIVATE_GATE = "(github.event.repository.private &&"


def _runs_on_lines(path):
    """Expression lines that read vars.RUNS_ON (comments skipped)."""
    return [
        line.strip()
        for line in path.read_text().splitlines()
        if "vars.RUNS_ON" in line and not line.lstrip().startswith("#")
    ]


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: str(p.relative_to(ROOT)))
def test_runs_on_is_used_only_while_private(path):
    for line in _runs_on_lines(path):
        expr = re.sub(r"\$\{\{ '\{\{' \}\}|\{\{ '\}\}' \}\}|\$\{\{|\}\}", "", line)
        assert PRIVATE_GATE in expr, f"{path.name}: {line}"
        # A public repo falls through to the hosted runner.
        if "runs-on:" in line:
            assert expr.rstrip().endswith("|| 'ubuntu-latest'"), line


def test_lint_workflow_runs_on():
    lines = [
        line.strip()
        for line in (ROOT / ".github/workflows/lint.yml").read_text().splitlines()
        if line.strip().startswith("runs-on:")
    ]
    assert lines == [
        "runs-on: ${{ (github.event.repository.private && vars.RUNS_ON) || 'ubuntu-latest' }}"
    ]


TEMPLATE_GATE = (
    "(github.event.repository.private && github.event_name != 'push'"
    " && github.actor != 'dependabot[bot]' && vars.RUNS_ON"
)


@pytest.mark.parametrize("template", TEMPLATES)
def test_template_runner_expressions(template):
    text = (ROOT / f"templates/{template}/.github/workflows/ci.yml.jinja").read_text()
    lines = [
        ln.strip()
        for ln in text.splitlines()
        if "vars.RUNS_ON" in ln and "#" not in ln.split(":")[0]
    ]
    assert lines == [
        "IS_SELF_HOSTED: ${{ '{{' }} "
        + TEMPLATE_GATE
        + " == 'self-hosted') {{ '}}' }}",
        "runs-on: ${{ '{{' }} " + TEMPLATE_GATE + ") || 'ubuntu-latest' {{ '}}' }}",
    ]


def _fake_gh(tmp_path, is_private):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "gh.log"
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$*" >> "{log}"\n'
        'if [[ "$1 $2" == "repo view" ]]; then\n'
        + (
            '  echo "gh: not logged in" >&2; exit 4\n'
            if is_private is None
            else f'  echo "{"true" if is_private else "false"}"\n'
        )
        + "fi\n"
    )
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    return env, log


def _set_runner(template, choice, env):
    return subprocess.run(
        ["bash", str(ROOT / f"templates/{template}/scripts/set-runner.sh"), choice],
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("template", TEMPLATES)
def test_set_runner_refuses_self_hosted_on_public_repo(template, tmp_path):
    env, log = _fake_gh(tmp_path, is_private=False)
    result = _set_runner(template, "self-hosted", env)
    assert result.returncode != 0
    assert "public" in result.stderr
    assert "variable set" not in log.read_text()


@pytest.mark.parametrize("template", TEMPLATES)
def test_set_runner_sets_self_hosted_on_private_repo(template, tmp_path):
    env, log = _fake_gh(tmp_path, is_private=True)
    result = _set_runner(template, "self-hosted", env)
    assert result.returncode == 0, result.stderr
    assert "variable set RUNS_ON --body self-hosted" in log.read_text()


@pytest.mark.parametrize("template", TEMPLATES)
def test_set_runner_github_works_on_public_repo(template, tmp_path):
    env, log = _fake_gh(tmp_path, is_private=False)
    result = _set_runner(template, "github", env)
    assert result.returncode == 0, result.stderr
    assert "variable delete RUNS_ON" in log.read_text()


@pytest.mark.parametrize("template", TEMPLATES)
def test_set_runner_stops_when_gh_fails(template, tmp_path):
    env, log = _fake_gh(tmp_path, is_private=None)
    result = _set_runner(template, "self-hosted", env)
    assert result.returncode != 0
    assert "public" not in result.stderr
    assert "variable set" not in log.read_text()
