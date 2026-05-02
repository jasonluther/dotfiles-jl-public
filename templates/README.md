# Project Templates

Copier-based scaffolding for new repos. Two flavors:

- `python-uv` — Python with uv, ruff, pyright. Single-package layout.
- `python-uv-with-js` — adds prettier, ESLint, npm tooling for JS/HTML.

## Scaffold a new project

```bash
copier copy <path-to-dotfiles-jl-public> ./newproject
cd newproject
git init && git add -A && git commit -m "chore: initial scaffold"
```

(`copier.yml` lives at the dotfiles repo root so the source is git-tracked,
which is what makes `copier update` work in scaffolded projects.)

Or use `gh-init --template python-uv` which wraps the above and creates the
GitHub repo in one shot.

## Update an existing scaffolded project

```bash
cd existing-project
copier update
```

Conflicts produce `.rej` files just like `git apply`.

### Why `copier update` works (gotcha)

Copier only writes `_commit` into `.copier-answers.yml` when the source is
git-tracked, and it only treats a path as git-tracked when there's a `.git`
directory at the source root. That's why `copier.yml` lives at the dotfiles
repo root with `_subdirectory: "templates/{{ flavor }}"` — moving it down
into `templates/` would break `copier update` in scaffolded projects (no
`_commit` → "cannot obtain old template references"). Don't relocate it.

## Switch CI runner

After the GitHub repo exists:

```bash
./scripts/set-runner.sh self-hosted   # local macOS runner pool
./scripts/set-runner.sh github        # ubuntu-latest
```
