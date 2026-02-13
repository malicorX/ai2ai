#!/usr/bin/env bash
# Create minimal ~/.openclaw/openclaw.json on sparky1 so install_moltworld_plugin_on_sparky.sh can add the plugin to it.
# Usage: bash bootstrap_openclaw_on_sparky1.sh (run on sparky1)
set -e
mkdir -p "$HOME/.openclaw"
if [[ -f "$HOME/.openclaw/openclaw.json" ]]; then
  echo "Already exists: $HOME/.openclaw/openclaw.json"
  exit 0
fi
python3 -c "
import json, secrets, os
p = os.path.expanduser('$HOME/.openclaw/openclaw.json')
d = {
  'gateway': {'mode': 'local', 'auth': {'mode': 'token', 'token': secrets.token_hex(16)}},
  'plugins': {'entries': {}}
}
with open(p, 'w') as f:
    json.dump(d, f, indent=2)
print('Created', p)
"
echo "Done. Run install_moltworld_plugin_on_sparky.sh then sparky1_fix_moltworld_config.sh."
