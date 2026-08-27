#!/usr/bin/env bash
# A pre-commit hook that reports registered Unicode carriers in staged text.
#
# Install with:
#   cp examples/ci/pre-commit-hook.sh .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit
#
# It reports and does not rewrite. A zero-width space can be deliberate, a
# Cyrillic name is somebody's name, and a hook that edits a commit under its
# author is worse than the thing it is guarding against. When something is
# found, you are shown where and the commit stops so you can decide.
#
# What it does not cover: confusable letters (a cleaning selector, not an
# inspection finding), statistical token-choice watermarks, and any vendor's
# mark. Passing this hook is not a statement about how the text was written.
set -euo pipefail

if ! command -v declawd > /dev/null 2>&1; then
  echo "declawd is not on PATH; skipping the carrier check" >&2
  exit 0
fi

status=0
while IFS= read -r file; do
  [ -f "$file" ] || continue
  case "$file" in
    *.md | *.markdown | *.txt) ;;
    *) continue ;;
  esac
  # Read the staged content, not the working tree, so the hook judges the
  # commit rather than whatever happens to be on disk.
  if ! git show ":$file" | declawd inspect - > /tmp/declawd-hook.$$ 2>&1; then
    echo
    echo "declawd: registered carriers in $file"
    sed 's/^/    /' /tmp/declawd-hook.$$
    status=1
  fi
  rm -f /tmp/declawd-hook.$$
done < <(git diff --cached --name-only --diff-filter=d)

if [ "$status" -ne 0 ]; then
  echo
  echo "Nothing has been changed. Inspect the findings above and commit again,"
  echo "or use --no-verify if the characters are meant to be there."
fi
exit "$status"
