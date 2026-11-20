"""Unit tests for the `fix-url` clipboard/URL cleanup helper."""

import importlib.machinery
import importlib.util
import io
from pathlib import Path

import pytest

FIX_URL_SRC = (
    Path(__file__).resolve().parent.parent / "dot_local/bin/executable_fix-url"
)


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


fix_url = _load("fix_url_tool", FIX_URL_SRC)

WRAPPED = (
    "https://claude.com/cai/oauth/authorize?code=true&client_id=9d1c250a-e61b-44d9-88\n"
    "ed-5944d1962f5e&response_type=code&redirect_uri=https%3A%2F%2Fplatform.claude.co\n"
    "m%2Foauth%2Fcode%2Fcallback&scope=org%3Acreate_api_key+user%3Aprofile+user%3Ainf\n"
    "erence\n"
)
CLEAN = (
    "https://claude.com/cai/oauth/authorize?code=true&client_id=9d1c250a-e61b-44d9-88"
    "ed-5944d1962f5e&response_type=code&redirect_uri=https%3A%2F%2Fplatform.claude.co"
    "m%2Foauth%2Fcode%2Fcallback&scope=org%3Acreate_api_key+user%3Aprofile+user%3Ainf"
    "erence"
)


def test_clean_joins_wrapped_lines():
    assert fix_url.clean(WRAPPED) == CLEAN


def test_clean_strips_stray_spaces():
    assert fix_url.clean("https://example.com/ a b\tc\n") == "https://example.com/abc"


def test_clean_already_clean_url_is_unchanged():
    assert fix_url.clean(CLEAN) == CLEAN


def test_clean_empty_string():
    assert fix_url.clean("") == ""


def test_looks_like_url_true_for_https():
    assert fix_url.looks_like_url(CLEAN) is True


def test_looks_like_url_false_for_garbage():
    assert fix_url.looks_like_url("not a url") is False


def test_looks_like_url_false_for_scheme_only():
    assert fix_url.looks_like_url("https://") is False


def test_looks_like_url_false_for_non_http_scheme():
    assert fix_url.looks_like_url("ftp://example.com/file") is False


def test_looks_like_url_false_for_empty_string():
    assert fix_url.looks_like_url("") is False


def test_extract_strips_parens():
    assert fix_url.extract("(https://example.com/a?b=c)") == "https://example.com/a?b=c"


def test_extract_strips_square_and_angle_brackets():
    assert fix_url.extract("[https://example.com/a]") == "https://example.com/a"
    assert fix_url.extract("<https://example.com/a>") == "https://example.com/a"


def test_extract_markdown_link_takes_first_url():
    md = "[https://example.com/a](https://example.com/a)"
    assert fix_url.extract(md) == "https://example.com/a"


def test_extract_markdown_link_with_label():
    assert fix_url.extract("[Sheet](https://example.com/s)") == "https://example.com/s"


def test_extract_keeps_balanced_parens_in_url():
    url = "https://en.wikipedia.org/wiki/Mercury_(planet)"
    assert fix_url.extract(f"({url})") == url
    assert fix_url.extract(url) == url


def test_extract_drops_trailing_punctuation_and_text():
    assert fix_url.extract("see(https://example.com/x).") == "https://example.com/x"
    assert fix_url.extract("https://example.com/x,") == "https://example.com/x"


def test_extract_wrapped_url_in_parens():
    assert fix_url.extract(fix_url.clean(f"({WRAPPED})")) == CLEAN


def test_extract_no_url_returns_text():
    assert fix_url.extract("not a url") == "not a url"


def test_extract_clean_url_is_unchanged():
    assert fix_url.extract(CLEAN) == CLEAN


def _main(monkeypatch, text, *argv):
    """Run main() on piped *text*; return (opened, copied, exit message)."""
    opened, copied = [], []
    monkeypatch.setattr(fix_url.sys, "argv", ["fix-url", *argv])
    monkeypatch.setattr(fix_url.sys, "stdin", io.StringIO(text))
    monkeypatch.setattr(fix_url, "open_browser", opened.append)
    monkeypatch.setattr(fix_url, "write_clipboard", copied.append)
    try:
        fix_url.main()
    except SystemExit as e:
        return opened, copied, str(e.code)
    return opened, copied, None


def test_main_opens_and_copies_the_cleaned_url(monkeypatch):
    assert _main(monkeypatch, f"({WRAPPED})") == ([CLEAN], [CLEAN], None)


@pytest.mark.parametrize(
    "text", ["rm -rf ~", "file:///etc/passwd", "javascript:alert(1)", "   \n"]
)
def test_main_refuses_to_open_or_copy_anything_that_is_not_a_web_url(monkeypatch, text):
    opened, copied, error = _main(monkeypatch, text)
    assert (opened, copied) == ([], [])
    assert error and error.startswith("fix-url:")


def test_print_mode_does_not_open_the_browser(monkeypatch, capsys):
    assert _main(monkeypatch, WRAPPED, "-p") == ([], [CLEAN], None)
    assert capsys.readouterr().out.strip() == CLEAN
