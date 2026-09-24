#!/usr/bin/env bash
# Puts this project on GitHub using YOUR git identity, so the commits are yours.
#
# 1. On github.com create a NEW EMPTY repository (Private, no README, no .gitignore).
# 2. Run:   bash setup_github.sh https://github.com/YOUR-USER/campus-visitor-system.git
#
# Git will ask for your GitHub login. For HTTPS, use a Personal Access Token as the password
# (GitHub -> Settings -> Developer settings -> Personal access tokens), or set up an SSH key
# and use the git@github.com:... URL instead.
set -euo pipefail
cd "$(dirname "$0")"

REMOTE_URL="${1:-}"
if [ -z "${REMOTE_URL}" ]; then
    read -r -p "Paste your new empty GitHub repository URL: " REMOTE_URL
fi

command -v git >/dev/null 2>&1 || { echo "git is not installed. Run: sudo apt install git"; exit 1; }

NAME="$(git config user.name || true)"
EMAIL="$(git config user.email || true)"
if [ -z "${NAME}" ] || [ -z "${EMAIL}" ]; then
    cat <<'MSG'
Your git identity is not set, so I will not guess it. Run these two commands with your own details
(the email must be one added to your GitHub account) and then run this script again:

    git config --global user.name  "Your Name"
    git config --global user.email "your-email@example.com"
MSG
    exit 1
fi
echo "Commits will be made as: ${NAME} <${EMAIL}>"

if [ ! -d .git ]; then
    git init -q
    git checkout -q -b main
fi

git add -A

# Safety: make sure no secrets or environment folders are about to be committed.
if git diff --cached --name-only | grep -Eq '(^|/)\.env$|(^|/)venv/|(^|/)instance/|\.(db|sqlite3)$'; then
    echo "Refusing to continue: .env, venv/, instance/ or a database file is staged."
    echo "Check .gitignore, then run: git reset"
    exit 1
fi

if git diff --cached --quiet; then
    echo "Nothing new to commit."
else
    git commit -q -m "Initial commit: Flask visitor management and digital gate pass system"
fi

if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "${REMOTE_URL}"
else
    git remote add origin "${REMOTE_URL}"
fi
git branch -M main
git push -u origin main

echo
echo "Done. Last commit author:"
git log -1 --format='  %an <%ae>'
echo "Next: on GitHub open Settings -> Collaborators and add your teammates."
