# GitHub CLI token — exported for tools that read GITHUB_PERSONAL_ACCESS_TOKEN
# directly (e.g. the Claude Code GitHub MCP plugin) rather than using gh auth.
if command -v gh &>/dev/null; then
  _gh_token="$(gh auth token 2>/dev/null)"
  [[ -n "$_gh_token" ]] && export GITHUB_PERSONAL_ACCESS_TOKEN="$_gh_token"
  unset _gh_token
fi
