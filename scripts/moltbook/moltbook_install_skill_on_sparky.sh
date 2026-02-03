#!/bin/bash
# Install Moltbook skill into ~/.moltbot/skills/moltbook on sparky. Run via run_moltbook_install_skill.ps1.
set -e
BASE="https://www.moltbook.com"
mkdir -p ~/.moltbot/skills/moltbook
curl -s "$BASE/skill.md"       -o ~/.moltbot/skills/moltbook/SKILL.md
curl -s "$BASE/heartbeat.md"   -o ~/.moltbot/skills/moltbook/HEARTBEAT.md
curl -s "$BASE/messaging.md"   -o ~/.moltbot/skills/moltbook/MESSAGING.md
curl -s "$BASE/skill.json"     -o ~/.moltbot/skills/moltbook/package.json
echo "Installed Moltbook skill in ~/.moltbot/skills/moltbook"
