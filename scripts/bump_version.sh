#!/bin/bash

# usage: ./scripts/bump_version.sh <new_version>
# example: ./scripts/bump_version.sh 0.1.1

set -e

NEW_VERSION="$1"

if [ -z "$NEW_VERSION" ]; then
    echo "Error: No version specified."
    echo "Usage: ./scripts/bump_version.sh <new_version>"
    exit 1
fi

# 1. Update pyproject.toml
# This regex looks for 'version = "..."' in the [project] section roughly
# It assumes standard formatting in pyproject.toml
if [[ "$OSTYPE" == "darwin"* ]]; then
  sed -i '' "s/^version = ".*"/version = "$NEW_VERSION"/" pyproject.toml
else
  sed -i "s/^version = ".*"/version = "$NEW_VERSION"/" pyproject.toml
fi

echo "✅ Updated pyproject.toml to $NEW_VERSION"

# 2. Update uv.lock
echo "🔄 Updating lockfile..."
uv lock

# 3. Commit and Tag
echo "📦 Preparing commit..."
git add pyproject.toml uv.lock
git commit -m "chore: bump version to v$NEW_VERSION"
git tag -a "v$NEW_VERSION" -m "Release v$NEW_VERSION"

echo "🎉 Version bumped to $NEW_VERSION and tagged."
echo ""
echo "🚀 To trigger the release build, run:"
echo "   git push origin main --tags"
