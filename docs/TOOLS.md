# Tools & Sandbox Policy (root-in-container)

## Why this matters
Agents need “full operator” capability, but the system must remain auditable and safe.

## Tool surface (v1)

### 1) Shell tool (inside agent container)
- Executes commands as root inside the agent container.
- Examples: `apt`, `pip`, `git`, compilers, scripts.

**Logging required:** command, cwd, env (redacted), stdout/stderr, exit code, duration.

### 2) Filesystem tool
- Read/write within the mounted workspace.
- Must prevent writes outside allowed paths (no host FS).

### 3) Browser tool (Playwright recommended)
- Real browser automation for research + form-based workflows.
- Strict rate limits and timeouts.

**Logging required:** URLs visited, request domains, extracted content hashes/links.

### 4) HTTP/API tool
- For calling external APIs (GitHub, etc.)
- Use a proxy/broker for auth tokens; don’t expose raw secrets to agents by default.

### 5) Web search (backend gateway)
- **POST /tools/web_search** — agents call this to run a web search (Serper API). Returns `{ results: [{ title, snippet, url }] }`.
- Requires `WEB_SEARCH_ENABLED=1` and `SERPER_API_KEY` (see ENV.example).
- Used by proposer for **Fiverr discovery**: search Fiverr → pick a gig → transform to a sparky task → create job → executor solves it.

### 6) Web fetch (backend gateway)
- **POST /tools/web_fetch** — agents fetch a public URL (SSRF protection, optional domain allowlist). Used for research and for fetching Fiverr gig pages when `WEB_FETCH_ALLOWLIST` includes `fiverr.com`.

## Guardrails (v1)
- Containers are non-privileged.
- Mount only workspace volumes.
- Explicit outbound network policy:
  - at minimum: log all outbound domains
  - optionally: allowlist domains per tool
- Admin kill switch:
  - pause/stop container
  - revoke agent token
  - freeze entitlements

## Audit log schema (recommended)
- `timestamp`, `agent_id`
- `tool_name` (shell/browser/http/fs)
- `input_summary` (command/url)
- `output_summary` (exit code / status / bytes)
- `duration_ms`
- `artifacts` (paths, links, hashes)

