#!/bin/bash
set -ex  # Print each command and exit on real errors

# Define SSH key and known_hosts for HA environment
export GIT_SSH_COMMAND='ssh -i /config/.ssh/id_rsa -o UserKnownHostsFile=/config/.ssh/known_hosts -o StrictHostKeyChecking=yes'

# Backup Lovelace dashboards before committing
STORAGE_DIR="/config/.storage"
BACKUP_DIR="/config/dashboard_backups"
HELPER_BACKUP_DIR="/config/helper_backups"

mkdir -p "$BACKUP_DIR"
mkdir -p "$HELPER_BACKUP_DIR"

# Copy files matching lovelace.dashboard_xxxx
find "$STORAGE_DIR" -maxdepth 1 -type f -name "lovelace.dashboard_*" -exec cp -f {} "$BACKUP_DIR"/ \;

# Copy files matching input_xxxx
find "$STORAGE_DIR" -maxdepth 1 -type f -name "input_*" -exec cp -f {} "$HELPER_BACKUP_DIR"/ \;

# Get HA version
HA_VERSION=$(cat .HA_VERSION)

git add .

# Only commit if there are changes
if ! git diff --cached --quiet; then
    # Build a human-readable, comma-separated list of changed files (basenames only)
    mapfile -t CHANGED_FILES < <(git diff --cached --name-only | xargs -n1 basename)
    TOTAL_COUNT=${#CHANGED_FILES[@]}

    MAX_LISTED=3
    if [ "$TOTAL_COUNT" -le "$MAX_LISTED" ]; then
        LISTED_FILES=("${CHANGED_FILES[@]}")
        EXTRA_COUNT=0
    else
        LISTED_FILES=("${CHANGED_FILES[@]:0:$MAX_LISTED}")
        EXTRA_COUNT=$((TOTAL_COUNT - MAX_LISTED))
    fi
    LISTED_COUNT=${#LISTED_FILES[@]}

    if [ "$EXTRA_COUNT" -gt 0 ]; then
        # More files than we list: join all listed names with commas, then "and N more file(s)"
        FILE_LIST=$(printf ", %s" "${LISTED_FILES[@]}")
        FILE_LIST="${FILE_LIST:2}"
        if [ "$EXTRA_COUNT" -eq 1 ]; then
            FILE_LIST="$FILE_LIST and 1 more file"
        else
            FILE_LIST="$FILE_LIST and $EXTRA_COUNT more files"
        fi
    elif [ "$LISTED_COUNT" -eq 1 ]; then
        FILE_LIST="${LISTED_FILES[0]}"
    else
        FILE_LIST=$(printf ", %s" "${LISTED_FILES[@]:0:$((LISTED_COUNT - 1))}")
        FILE_LIST="${FILE_LIST:2}"
        FILE_LIST="$FILE_LIST and ${LISTED_FILES[$((LISTED_COUNT - 1))]}"
    fi

    COMMIT_MESSAGE="[$HA_VERSION]: Updated $FILE_LIST"
    echo "$COMMIT_MESSAGE"

    git commit -m "$COMMIT_MESSAGE"
    git push
else
    echo "No changes to commit."
fi