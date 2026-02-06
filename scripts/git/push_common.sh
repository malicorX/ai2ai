#!/bin/bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: push_common.sh <host> [--restart "<cmd>"] [--no-clean]

Pulls latest main branch on the remote host and hard-resets the repo.
Looks for the repo in common locations and optionally runs a restart command.
EOF
}

HOST=""
RESTART_CMD=""
NO_CLEAN=0
BRANCH="main"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --restart)
      RESTART_CMD="${2:-}"
      shift 2
      ;;
    --no-clean)
      NO_CLEAN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ -z "$HOST" ]]; then
        HOST="$1"
        shift
      else
        echo "Unknown argument: $1"
        usage
        exit 1
      fi
      ;;
  esac
done

if [[ -z "$HOST" ]]; then
  usage
  exit 1
fi

RESTART_ESCAPED=$(printf "%q" "$RESTART_CMD")

ssh "$HOST" "BRANCH=${BRANCH} NO_CLEAN=${NO_CLEAN} RESTART_CMD=${RESTART_ESCAPED} bash -s" <<'EOS'
set -euo pipefail

CANDIDATES=(
  "/home/malicor/ai2ai"
  "/home/malicor/ai_ai2ai"
  "/opt/ai_ai2ai"
  "/opt/ai_ai2ai/ai_ai2ai"
)

REPO=""
for p in "${CANDIDATES[@]}"; do
  if [[ -d "$p/.git" ]]; then
    REPO="$p"
    break
  fi
done

if [[ -z "$REPO" ]]; then
  echo "No git repo found in: ${CANDIDATES[*]}"
  exit 1
fi

echo "Repo: $REPO"
cd "$REPO"

git fetch --all --prune
git reset --hard "origin/${BRANCH}"
if [[ "${NO_CLEAN}" != "1" ]]; then
  git clean -fd
fi
git submodule update --init --recursive

echo "Head: $(git rev-parse --short HEAD)"

if [[ -n "${RESTART_CMD}" ]]; then
  echo "Restart: ${RESTART_CMD}"
  eval "${RESTART_CMD}"
fi
EOS
