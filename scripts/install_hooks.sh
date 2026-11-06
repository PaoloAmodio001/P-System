#!/bin/sh
# Install the hook of this repository: a commit then runs the fast tests and lake build first.
set -e
root=$(git rev-parse --show-toplevel)
hooks=$(git -C "$root" rev-parse --git-path hooks)

case "$hooks" in
    /*) ;;
    *) hooks="$root/$hooks" ;;
esac

mkdir -p "$hooks"

if [ -e "$hooks/pre-commit" ] && ! cmp -s "$hooks/pre-commit" "$root/scripts/pre-commit"; then
    echo "$hooks/pre-commit exists and is another hook: left as it is" >&2
    exit 1
fi

cp "$root/scripts/pre-commit" "$hooks/pre-commit"
chmod +x "$hooks/pre-commit"
echo "installed: $hooks/pre-commit"
