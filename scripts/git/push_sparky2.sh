#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
"$SCRIPT_DIR/push_common.sh" sparky2 --restart "systemctl --user restart clawdbot-gateway.service"
