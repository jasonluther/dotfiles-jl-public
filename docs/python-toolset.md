# Python toolset notes

Reference for the recommended Python development setup as used in this dotfiles repo and in `templates/python-uv*`. Update this when any of the choices below change so the rest of the repo can be brought along.

## Current recommendations (2026)

| Concern             | Pick                                                              | Replaces                                                       |
| ------------------- | ----------------------------------------------------------------- | -------------------------------------------------------------- |
| Package + env mgmt  | `uv`                                                              | `pip`, `pip-tools`, `pipenv`, `poetry`                         |
| Project metadata    | `pyproject.toml` (PEP 621)                                        | `setup.py`, `setup.cfg`                                        |
| Build backend       | `hatchling`                                                       | `setuptools`, `poetry-core`, `flit`                            |
| Lock file           | `uv.lock`                                                         | `requirements.txt`, `poetry.lock`                              |
| Linter              | `ruff`                                                            | `flake8`, `pylint`, `pycodestyle`                              |
| Formatter           | `ruff format`                                                     | `black`, `autopep8`, `yapf`                                    |
| Import sorting      | `ruff` (built-in `I` rules)                                       | `isort`                                                        |
| Type checker        | TBD: `mypy` vs `pyright` vs `basedpyright` — fill in once decided | —                                                              |
| Test runner         | `pytest`                                                          | `unittest` (still fine for stdlib)                             |
| Task runner         | `just` or plain `make`                                            | `invoke`, `nox` (use `nox` only when matrix testing is needed) |
| Pre-commit          | `pre-commit` + `ruff` hooks                                       | manual git hooks                                               |
| Python install mgmt | `uv python install`                                               | `pyenv`, `asdf`                                                |

## Legacy/avoid

- `pipenv`: superseded by `uv`. Existing projects can be migrated incrementally.
- `poetry`: works fine but `uv` is faster and aligns with PEP standards. New projects use `uv`.
- `setup.py`: only for editable-install legacy code. New projects: `pyproject.toml` + `hatchling`.
- `requirements.txt`: still useful for ad-hoc envs, but lock files are `uv.lock`.
- `black` + `flake8` + `isort`: the `ruff` family covers all three.

## Editor settings

VS Code user `settings.json` should include:

```json
{
  "editor.fontFamily": "MonaspaceNeon Nerd Font, MonaspaceNeon, Menlo, monospace",
  "editor.fontLigatures": "'calt', 'liga', 'ss01', 'ss02', 'ss03', 'ss04', 'ss05', 'ss06', 'ss07', 'ss08'",
  "terminal.integrated.fontFamily": "MonaspaceArgon Nerd Font, MonaspaceArgon, Menlo, monospace",
  "python.defaultInterpreterPath": ".venv/bin/python",
  "editor.formatOnSave": true,
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.codeActionsOnSave": {
      "source.organizeImports": "explicit",
      "source.fixAll": "explicit"
    }
  },
  "ruff.organizeImports": true
}
```

## Fonts

[Monaspace](https://monaspace.githubnext.com/) is the recommended font family. Both casks are pinned in the public `Brewfile`:

- `font-monaspace` — base family (5 styles: Neon, Argon, Xenon, Radon, Krypton)
- `font-monaspace-nerd-font` — patched variant with Nerd Font glyphs for icons in shell prompts (starship, etc.)

Pairing convention used in this dotfiles repo:

- **Editor:** Monaspace Neon (clean, neutral)
- **Terminal:** Monaspace Argon (slight humanist warmth, easier for long sessions)

Both ship the texture-healing ligatures (the `ss01`–`ss08` features in `editor.fontLigatures` above).

## Open questions

- Type checker default — list current pick once chosen.
- `templates/python-uv/` should reference this doc in its README so forkers know the rationale.
