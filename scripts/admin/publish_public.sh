#!/usr/bin/env bash
# Publish the crew to its public repository with a history fit to publish. The private repository cannot simply be made public:
# every one of its branches, and the copies GitHub keeps of each merged pull request, carry the original history.
#
# What it does: clones the private branch fresh, rewrites every commit with git filter-repo, checks the result, and pushes it as
# `main` of the public repository. The rewrite replaces the workstation's addresses, login name, host name and deploy key id, the
# phone example's area code and the carrier's name, and maps personal e-mail addresses to GitHub no-reply addresses. Commits,
# dates, messages and authors stay; the final files differ from the private branch only in those strings.
#
# The rules live OUTSIDE the repository, because they contain the very strings they remove: $RULES_DIR/replace.txt (git
# filter-repo --replace-text format) and $RULES_DIR/mailmap.txt. The rewrite is deterministic, so a second run over a longer
# branch reproduces the same commits and adds the new ones: the push is a fast-forward.
#
# Needs git-filter-repo (pip install git-filter-repo) and push rights to the public repository.
# Use: RULES_DIR=~/.config/inverse-public scripts/admin/publish_public.sh [public-repo-url] [private-branch]
set -euo pipefail
PUBLIC="${1:-https://github.com/mathib2/inverse.git}"
BRANCH="${2:-m4-sindyc}"
RULES="${RULES_DIR:-$HOME/.config/inverse-public}"
FR="${GIT_FILTER_REPO:-git-filter-repo}"
PRIVATE="$(git remote get-url origin)"
for f in replace.txt mailmap.txt; do [ -s "$RULES/$f" ] || { echo "missing $RULES/$f" >&2; exit 2; }; done
command -v "$FR" >/dev/null || { echo "git-filter-repo not found (pip install git-filter-repo, or set GIT_FILTER_REPO)" >&2; exit 2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
git clone -q --single-branch --branch "$BRANCH" --no-tags "$PRIVATE" "$WORK/repo"
cd "$WORK/repo"
"$FR" --force --replace-text "$RULES/replace.txt" --replace-message "$RULES/replace.txt" --mailmap "$RULES/mailmap.txt" >/dev/null
git branch -m "$BRANCH" main

# Every rule's target must be gone from the whole history: contents, messages and author metadata.
leaks=0
while IFS= read -r rule; do
  [ -n "$rule" ] || continue
  pat="${rule%%==>*}"
  case "$pat" in
    regex:*) pat="${pat#regex:}" ;;
    literal:*) pat="$(printf '%s' "${pat#literal:}" | sed 's/[][\.*^$?+(){}|/]/\\&/g')" ;;
  esac
  n=$( { git log main -p --format='%B'; git log main --format='%an %ae %cn %ce'; } | grep -cP -- "$pat" || true)
  [ "$n" = 0 ] || { echo "still present ($n lines): rule $(printf '%s' "$rule" | cut -c1-12)..." >&2; leaks=1; }
done < "$RULES/replace.txt"
while IFS= read -r line; do
  old="${line##*<}"; old="${old%>}"
  [ -n "$old" ] || continue
  n=$(git log main --format='%ae %ce' | grep -cF -- "$old" || true)
  [ "$n" = 0 ] || { echo "an e-mail address is still in the metadata ($n commits)" >&2; leaks=1; }
done < "$RULES/mailmap.txt"
[ "$leaks" = 0 ] || { echo "not pushed: the rewrite left something behind" >&2; exit 1; }

echo "rewritten: $(git rev-list --count main) commits, nothing left behind"
if [ "${DRY_RUN:-}" = 1 ]; then echo "dry run: not pushed"; exit 0; fi
echo "pushing to $PUBLIC"
git push -q "$PUBLIC" main:main
echo "published: $(git log -1 --format='%h %s' main)"
