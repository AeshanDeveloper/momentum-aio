#!/bin/bash


git add .

COMMIT=$(TZ=Asia/Kolkata date '+%M%H%d%m%Y')

echo "Commit: $COMMIT"

git commit -m "$COMMIT"
git push -u origin main --force

