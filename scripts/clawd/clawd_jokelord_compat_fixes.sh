#!/usr/bin/env bash
# Fix jokelord patch to match current Clawdbot API (OpenClaw naming, types, zod exports).
# Run from repo scripts dir; first arg = path to clawdbot clone root (e.g. $BUILD_DIR/clawdbot).
set -e

CLAWDBOT_ROOT="${1:?Usage: $0 <clawdbot-clone-root>}"
SRC="$CLAWDBOT_ROOT/src"
cd "$CLAWDBOT_ROOT"

echo "Applying compat fixes (OpenClaw naming, types, zod)..."

# 1) attempt.ts: jokelord uses "Clawdbot" names; upstream uses "OpenClaw"
ATTEMPT="$SRC/agents/pi-embedded-runner/run/attempt.ts"
if [[ -f "$ATTEMPT" ]]; then
  sed -i.bak \
    -e 's/resolveClawdbotAgentDir/resolveOpenClawAgentDir/g' \
    -e 's/resolveClawdbotDocsPath/resolveOpenClawDocsPath/g' \
    -e 's/createClawdbotCodingTools/createOpenClawCodingTools/g' \
    "$ATTEMPT"
  # Remove fields not in CreateAgentSessionOptions (upstream)
  sed -i.bak2 '/^[[:space:]]*systemPrompt,[[:space:]]*$/d' "$ATTEMPT"
  sed -i.bak2 '/^[[:space:]]*skills[[:space:]:,].*$/d' "$ATTEMPT"
  sed -i.bak2 '/^[[:space:]]*contextFiles[[:space:]:,].*$/d' "$ATTEMPT"
  sed -i.bak2 '/^[[:space:]]*additionalExtensionPaths[[:space:]:,].*$/d' "$ATTEMPT"
  # Ensure applySkillEnvOverrides includes required skills array (upstream expects it)
  if grep -q "applySkillEnvOverrides({" "$ATTEMPT"; then
    sed -i.bak2 '/applySkillEnvOverrides({/a\    skills: skillEntries ?? [],' "$ATTEMPT"
  fi
  rm -f "$ATTEMPT.bak" "$ATTEMPT.bak2"
  echo "  attempt.ts: renames + systemPrompt line removed"
fi

# 1b) abort.ts: jokelord attempt.ts imports isAbortError; upstream may not export it
ABORT="$SRC/agents/pi-embedded-runner/abort.ts"
if [[ -f "$ABORT" ]] && grep -q "isAbortError" "$ATTEMPT" 2>/dev/null && ! grep -q "export.*isAbortError" "$ABORT" 2>/dev/null; then
  echo "" >> "$ABORT"
  echo "export function isAbortError(e: unknown): boolean {" >> "$ABORT"
  echo "  return e instanceof Error && e.name === 'AbortError';" >> "$ABORT"
  echo "}" >> "$ABORT"
  echo "  abort.ts: added isAbortError export"
fi

# 2) compact.ts: pass getter function instead of string to applySystemPromptOverrideToSession
COMPACT="$SRC/agents/pi-embedded-runner/compact.ts"
if [[ -f "$COMPACT" ]]; then
  sed -i.bak 's/applySystemPromptOverrideToSession(session, systemPromptOverride)/applySystemPromptOverrideToSession(session, () => systemPromptOverride)/g' "$COMPACT"
  rm -f "$COMPACT.bak"
  echo "  compact.ts: systemPromptOverride wrapped in getter"
fi

# 3) zod-schema.core.ts: restore LinkModelSchema + ToolsLinksSchema from upstream
CORE="$SRC/config/zod-schema.core.ts"
if [[ -f "$CORE" ]]; then
  # Ensure ModelCompatSchema allows supportedParameters (required for tools/tool_choice)
  CORE_PATH="$CORE" python3 - <<'PY'
from pathlib import Path
import os
path = Path(os.environ["CORE_PATH"])
text = path.read_text()
if "supportedParameters" not in text:
    marker = "supportsReasoningEffort: z.boolean().optional(),"
    insert = "supportsReasoningEffort: z.boolean().optional(),\n supportsParameters: z.array(z.string()).optional(),"
    if marker in text:
        text = text.replace(marker, insert)
    else:
        # fallback: add before maxTokensField
        marker = "maxTokensField: z"
        if marker in text:
            text = text.replace(marker, "supportsParameters: z.array(z.string()).optional(),\n maxTokensField: z")
    path.write_text(text)
PY
  # Only append if upstream has them and current file does not (jokelord may have omitted them)
  if grep -q "export const LinkModelSchema" "$CORE" && grep -q "export const ToolsLinksSchema" "$CORE"; then
    echo "  zod-schema.core.ts: LinkModelSchema + ToolsLinksSchema already present, skip append"
  else
    ORIG=$(git show HEAD:src/config/zod-schema.core.ts 2>/dev/null || true)
    if [[ -n "$ORIG" ]]; then
      # Append LinkModelSchema block (needed by ToolsLinksSchema)
      echo "$ORIG" | sed -n '/^export const LinkModelSchema/,/^export const ToolsLinksSchema/p' | sed '$d' >> "$CORE"
      # Append ToolsLinksSchema block (from that export to line before NativeCommandsSettingSchema)
      echo "$ORIG" | sed -n '/^export const ToolsLinksSchema/,/^export const NativeCommandsSettingSchema/p' | sed '$d' >> "$CORE"
      echo "  zod-schema.core.ts: LinkModelSchema + ToolsLinksSchema appended from upstream"
    else
      echo "  WARN: could not get upstream zod-schema.core.ts (git show); ToolsLinksSchema may be missing" >&2
    fi
  fi
fi

echo "Compat fixes done."
