#!/usr/bin/env sh
# Run once after `git clone`: installs the wiki-interest skill for Claude Code.
#   ./setup.sh                    install (~/.claude/skills/wiki-interest + .venv + deps)
#   ./setup.sh claude haiku       install, then start Claude Code on Claude Haiku 4.5
#   ./setup.sh claude haiku "Чи зростає інтерес до астрономії в українській Вікіпедії?"
# All options: ./setup.sh --help
set -e
cd "$(dirname "$0")"
for py in python3 python; do
  if command -v "$py" >/dev/null 2>&1 &&
     "$py" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    exec "$py" wiki-interest/install.py "$@"
  fi
done
echo "Python 3.10+ is required: https://www.python.org/downloads/" >&2
exit 1
