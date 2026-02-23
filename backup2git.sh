#!/bin/bash
set -ex  # Print each command and exit on real errors

# Define SSH key and known_hosts for HA environment
export GIT_SSH_COMMAND='ssh -i /config/.ssh/id_rsa -o UserKnownHostsFile=/config/.ssh/known_hosts -o StrictHostKeyChecking=yes'

# Backup Lovelace dashboards before committing
STORAGE_DIR="/config/.storage"
BACKUP_DIR="/config/dashboard_backups"

mkdir -p "$BACKUP_DIR"

# Copy files matching lovelace.dashboard_xxxx
find "$STORAGE_DIR" -maxdepth 1 -type f -name "lovelace.dashboard_*" -exec cp -f {} "$BACKUP_DIR"/ \;

# Get HA version and prepare commit message
HA_VERSION=$(cat .HA_VERSION)
COMMIT_DATE=$(date +'%d-%m-%Y %H:%M:%S')
COMMIT_MESSAGE="Autocommit from HA - [$HA_VERSION]: $COMMIT_DATE"

echo "$COMMIT_MESSAGE"

git add .

# Only commit if there are changes
if ! git diff --cached --quiet; then
    git commit -m "$COMMIT_MESSAGE"
    git push
else
    echo "No changes to commit."
fi