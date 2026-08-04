# fix-url — design

2026-08-04. Approved in session.

## Goal

Terminal-wrapped OAuth URLs (`claude /login`, `gh auth login`, `aws sso
login`, `gcloud auth login`, ...) printed over SSH get mangled when
selected/copied in a terminal: line wraps become embedded newlines, and some
terminals inject extra spaces at wrap points. Today this is fixed by pasting
into an editor, joining lines, and stripping spaces by hand. `fix-url`
automates that: clean the clipboard (or piped stdin), validate it's a URL,
and open it.

## Decisions

- **Name: `fix-url`.** Generic, not Claude-specific — the mangling problem
  and the fix apply to any CLI that prints a long OAuth URL over SSH.
- **Language: Python 3**, matching the style of `executable_ssh-ports`
  (module docstring as usage/help text, `sys.exit` for errors, no comment
  cruft, thin `main()` + testable pure functions).
- **Input source:** system clipboard by default (`pbpaste` on macOS;
  `xclip -selection clipboard -o`, falling back to `wl-paste`, on Linux). If
  stdin is not a tty (piped), read stdin instead — supports
  `xclip -o | fix-url` and makes the parsing logic easy to test.
- **Cleaning:** strip _all_ whitespace (spaces, tabs, newlines) from the
  input. This assumes the copied text is essentially just the wrapped URL
  (matching the current manual workflow of "join lines + remove spaces");
  no attempt to extract a URL out of surrounding noise — YAGNI.
- **Validation:** the cleaned string must parse via `urllib.parse.urlsplit`
  with scheme `http`/`https` and a non-empty host. If it doesn't validate,
  print the cleaned-but-invalid string to stderr and exit non-zero — never
  silently open garbage.
- **Output:** on success, open the URL in the browser (`open` on macOS,
  `xdg-open` on Linux, chosen via `platform.system()`) **and** write the
  cleaned URL back to the clipboard as a fallback (paste elsewhere, share to
  another device).
- **`-p` / `--print` flag:** skip opening the browser; just print the
  cleaned URL to stdout and copy it to the clipboard. Covers the case of
  running this on a machine that isn't the one with the right browser
  session.
- **Errors handled explicitly:** no clipboard tool found, clipboard/stdin
  empty, cleaned text fails URL validation. No other fallback/retry logic.

## Components

1. `dot_local/bin/executable_fix-url` — the script itself. Deployed by
   chezmoi to `~/.local/bin/fix-url` on both macOS and Linux hosts.
   - `clean(text: str) -> str` — strip all whitespace.
   - `looks_like_url(text: str) -> bool` — scheme + host check via
     `urllib.parse`.
   - `read_input() -> str` — stdin if piped, else platform clipboard read.
   - `write_clipboard(text: str) -> None` — platform clipboard write.
   - `open_browser(url: str) -> None` — platform opener.
   - `main()` — argument parsing (`-p`/`--print`, `-h`/`--help`), wiring the
     above, exit codes.

## Testing

- Unit tests for `clean()` and `looks_like_url()` covering: normal wrapped
  URL with embedded newlines and spaces, already-clean URL, empty input,
  non-URL garbage.
- Manual verification: run `claude /login` on a Linux box over SSH inside
  tmux, copy the wrapped URL as today, run `fix-url` on the Mac, confirm the
  browser opens to the correct, unmangled URL.
