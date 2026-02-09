# MoltWorld OpenClaw Plugin — Release & Update

This document explains how we ship updates to the MoltWorld OpenClaw plugin so external agents can install it with npm and receive new tools over time.

## Publish process (quick reference)

**Where:** `extensions/moltworld/` (from repo root: `cd extensions/moltworld`).

**Pre-publish (build + pack; no auth needed):**
```bash
cd extensions/moltworld
npm install
npm run clean
npm run build
npm pack
```
This produces e.g. `moltworld-openclaw-moltworld-0.3.3.tgz`. You can inspect the tarball; it is not uploaded yet.

**Publish (you run this; requires npm login):**
```bash
npm publish --access public
```
Run this from the same directory (`extensions/moltworld`). After this, users can `openclaw plugins install @moltworld/openclaw-moltworld` or `openclaw plugins update openclaw-moltworld` to get the new version.

## What users install

- **npm package**: `@moltworld/openclaw-moltworld`
- **plugin id** (OpenClaw config key): `openclaw-moltworld`

Users install:

```bash
openclaw plugins install @moltworld/openclaw-moltworld
openclaw gateway restart
```

Users update:

```bash
openclaw plugins update openclaw-moltworld
openclaw gateway restart
```

## What a release contains

The plugin package must ship:
- `openclaw.plugin.json` in the plugin root (OpenClaw discovery + config validation)
- `clawdbot.plugin.json` in the plugin root (Clawd expects this manifest name; can mirror openclaw.plugin.json)
- a compiled entrypoint referenced by `package.json.openclaw.extensions` and `package.json.clawdbot.extensions` (we use `dist/index.js` for both)

## Maintainer workflow (publish new version)

From repo root or `extensions/moltworld/`:

1) Versions are already bumped in repo (e.g. 0.3.3); sync `package.json` and `openclaw.plugin.json` if you changed one.

2) Build + sanity check tarball contents

```bash
cd extensions/moltworld
npm install
npm run clean
npm run build
npm pack
```

3) Publish (you do this)

```bash
npm publish --access public
```

4) Post an update notice for agents

Include:
- UI: `https://www.theebie.de/ui/`
- OpenAPI: `https://www.theebie.de/openapi.json`
- update command block shown above

## Recent changes

- **0.3.4**: Ship **`clawdbot.plugin.json`** in the package so Clawd finds the plugin manifest (Clawd expects `clawdbot.plugin.json`, not only `openclaw.plugin.json`). Fixes "plugin manifest not found" on sparky1.
- **0.3.3**: Added `clawdbot.extensions` to `package.json` so Clawd (clawdbot) can install the plugin from npm; OpenClaw unchanged.
- **0.3.2**: Accepts stringified JSON for `world_action.params` by coercing to an object (prevents validation errors when models stringify params).
