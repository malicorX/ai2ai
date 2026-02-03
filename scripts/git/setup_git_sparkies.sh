#!/bin/bash
# Setup git on sparky1 and sparky2
# Run this on sparky1 or sparky2 to set up git with the remote

set -e

REPO_URL="https://github.com/malicorX/ai2ai.git"
BRANCH="main"

echo "=== Setting up git ==="

# Initialize git if not already done
if [ ! -d .git ]; then
    echo "Initializing git repository..."
    git init
    git branch -M $BRANCH
fi

# Add remote if not exists
if ! git remote get-url origin >/dev/null 2>&1; then
    echo "Adding remote origin..."
    git remote add origin $REPO_URL
else
    echo "Remote origin already exists, updating URL..."
    git remote set-url origin $REPO_URL
fi

# Fetch from remote
echo "Fetching from remote..."
git fetch origin

# Check if we have a local main branch
if git show-ref --verify --quiet refs/heads/$BRANCH; then
    echo "Local $BRANCH branch exists"
    # Try to merge or reset
    echo "Attempting to sync with remote..."
    git pull origin $BRANCH --allow-unrelated-histories --no-edit || {
        echo "Merge had conflicts. Resetting to match remote (this will lose local changes)..."
        read -p "Continue? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            git reset --hard origin/$BRANCH
        fi
    }
else
    echo "Creating local $BRANCH branch tracking remote..."
    git checkout -b $BRANCH origin/$BRANCH || git checkout $BRANCH
fi

echo ""
echo "=== Git setup complete ==="
echo "To pull latest changes: git pull origin $BRANCH"
echo "To check status: git status"
echo ""
echo "Note: For pushing, you'll need to set up GitHub authentication:"
echo "  - Use SSH keys, or"
echo "  - Use a personal access token with git config credential.helper"
