#!/usr/bin/env zsh
# Zsh prompt — explicit so Linux matches Mac.
#
# macOS's /etc/zshrc sets `PS1="%n@%m %1~ %# "` so the bare-zsh prompt looks
# like `user@host pwd %`. Linux's /etc/zsh/zshrc doesn't, so it falls through
# to zsh's terse default `%m%# ` (just `host%`). Setting PROMPT here lines up
# both platforms.
#
# Format: `[venv] user@host pwd %`. The `(venv)` prefix is prepended by
# Python's standard `activate` script when zsh-autoswitch-virtualenv enters
# a project, so we don't have to render it ourselves.
PROMPT='%F{cyan}%n@%m%f %F{yellow}%1~%f %# '
