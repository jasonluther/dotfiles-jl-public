"""Unit tests for the `fix-url` clipboard/URL cleanup helper."""

import importlib.machinery
import importlib.util
from pathlib import Path

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
