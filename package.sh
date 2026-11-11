#!/usr/bin/env bash
# Builds 41.zip with the structure the brief requires.
set -euo pipefail
cd "$(dirname "$0")"
PROJECT="$PWD"
TEAM=41

for file in "$TEAM.mp4" 28.pdf README.md src/schema.sql src/populate.sql src/app.py src/requirements.txt; do
    if [ ! -f "$file" ]; then
        echo "Missing: $file" >&2
        exit 1
    fi
done

BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT
cp "$TEAM.mp4" README.md "$BUILD/"
cp 28.pdf "$BUILD/phase3.pdf"
mkdir "$BUILD/src"
tar -C src --exclude='__pycache__' --exclude='.venv' --exclude='.gitignore' -cf - . | tar -C "$BUILD/src" -xf -

rm -f "$TEAM.zip"
(cd "$BUILD" && zip -qr "$PROJECT/$TEAM.zip" .)
unzip -l "$TEAM.zip"
