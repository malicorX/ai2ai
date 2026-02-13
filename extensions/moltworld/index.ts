import { writeFileSync, mkdirSync, readFileSync } from "fs";

type ToolConfig = {
  baseUrl: string;
  agentId: string;
  agentName: string;
  token?: string;
  adminToken?: string;
};

type OpenClawApi = {
  config: any;
  registerTool: (
    tool: {
      name: string;
      description: string;
      parameters: Record<string, unknown>;
      execute: (id: string, params: Record<string, any>) => Promise<any>;
    },
    opts?: { optional?: boolean },
  ) => void;
  logger: { info: (msg: string) => void; warn: (msg: string) => void };
};

let cachedToken: string | null = null;

/** Paths to check for .moltworld_context (set_moltworld_context.ps1 -Off writes "off"). */
function getMoltWorldContextPaths(): string[] {
  if (typeof process === "undefined" || !process.env) return [];
  const home = process.env.HOME || "";
  const cwd = typeof process.cwd === "function" ? process.cwd() : "";
  const paths: string[] = [];
  if (home) paths.push(home + "/.moltworld_context");
  paths.push("/home/malicor/.moltworld_context");
  if (process.env.LOGNAME) paths.push("/home/" + process.env.LOGNAME + "/.moltworld_context");
  if (process.env.USER && process.env.USER !== "malicor") paths.push("/home/" + process.env.USER + "/.moltworld_context");
  if (cwd) paths.push(cwd + "/.moltworld_context");
  return paths;
}

/** True when MoltWorld context is off (env MOLTWORLD_CONTEXT=off or .moltworld_context contains "off"). */
function isMoltWorldContextOff(): boolean {
  if (typeof process !== "undefined" && process.env && (process.env.MOLTWORLD_CONTEXT || "").trim().toLowerCase() === "off") return true;
  for (const path of getMoltWorldContextPaths()) {
    if (!path) continue;
    try {
      const content = readFileSync(path, "utf8");
      const val = (content || "").trim().toLowerCase().replace(/\r/g, "");
      if (val === "off") return true;
    } catch {
      /* try next path */
    }
  }
  return false;
}

function getConfig(api: OpenClawApi): ToolConfig {
  let cfg: Partial<ToolConfig> = {};
  try {
    cfg = (api.config?.plugins?.entries?.["openclaw-moltworld"]?.config || {}) as Partial<ToolConfig>;
  } catch (_) {}
  let token = (cfg.token || "").trim();
  if (!token && typeof process !== "undefined") {
    for (const tokenPath of ["/home/malicor/.openclaw/extensions/openclaw-moltworld/.token", (process.env?.HOME || "") + "/.openclaw/extensions/openclaw-moltworld/.token"]) {
      if (!tokenPath || tokenPath.startsWith("/.openclaw")) continue;
      try {
        const t = readFileSync(tokenPath, "utf8").trim();
        if (t) {
          token = t;
          break;
        }
      } catch (_) {}
    }
  }
  if (!token && typeof process !== "undefined" && process.env) {
    token = (process.env.WORLD_AGENT_TOKEN || process.env.MOLTWORLD_TOKEN || "").trim();
  }
  if (!token && typeof process !== "undefined") {
    const home = process.env?.HOME || "/home/malicor";
    for (const envPath of [home + "/.moltworld.env", "/home/malicor/.moltworld.env"]) {
      try {
        const content = readFileSync(envPath, "utf8");
        const m = content.match(/WORLD_AGENT_TOKEN\s*=\s*["']?([^"'\s#]+)/);
        if (m) {
          token = m[1].trim();
          break;
        }
      } catch (_) {}
    }
  }
  if (!token && typeof process !== "undefined") {
    for (const configPath of ["/home/malicor/.openclaw/openclaw.json", (process.env?.HOME || "") + "/.openclaw/openclaw.json"]) {
      if (!configPath || configPath === "/.openclaw/openclaw.json") continue;
      try {
        const content = readFileSync(configPath, "utf8");
        const data = JSON.parse(content);
        const t = data?.plugins?.entries?.["openclaw-moltworld"]?.config?.token;
        if (typeof t === "string" && t.trim()) {
          token = t.trim();
          break;
        }
      } catch (_) {}
    }
  }
  return {
    baseUrl: cfg.baseUrl || "https://www.theebie.de",
    agentId: cfg.agentId || "MalicorSparky2",
    agentName: cfg.agentName || cfg.agentId || "MalicorSparky2",
    token: token || undefined,
    adminToken: (cfg.adminToken || "").trim() || undefined,
  };
}

async function safeJson(res: Response): Promise<any> {
  const text = await res.text();
  if (!text) return { error: "empty_response", status: res.status };
  try {
    return JSON.parse(text);
  } catch {
    return { error: "non_json_response", status: res.status, text: text.slice(0, 400) };
  }
}

async function requestToken(cfg: ToolConfig): Promise<string | null> {
  // Only works if the server allows /admin/agent/issue_token (ADMIN_TOKEN unset)
  // or if the caller provides an adminToken that matches the server's ADMIN_TOKEN.
  const res = await fetch(`${cfg.baseUrl}/admin/agent/issue_token`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(cfg.adminToken ? { authorization: `Bearer ${cfg.adminToken}` } : {}),
    },
    body: JSON.stringify({ agent_id: cfg.agentId, agent_name: cfg.agentName }),
  });
  if (!res.ok) return null;
  const data = await safeJson(res);
  return data?.token || null;
}

async function authedFetch(cfg: ToolConfig, url: string, init?: RequestInit) {
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string>), "content-type": "application/json" };
  // Prefer explicit configured token (outsiders will use this).
  if (cfg.token && !cachedToken) cachedToken = cfg.token;
  if (cachedToken) headers["authorization"] = `Bearer ${cachedToken}`;
  const res = await fetch(url, { ...(init || {}), headers });
  if (res.status === 401 || res.status === 403) {
    const token = await requestToken(cfg);
    if (token) {
      cachedToken = token;
      headers["authorization"] = `Bearer ${cachedToken}`;
      return fetch(url, { ...(init || {}), headers });
    }
  }
  return res;
}

function toolResult(data: any) {
  return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
}

export default function register(api: OpenClawApi) {
  api.registerTool({
    name: "world_state",
    description: "Pull world state and recent_chat. Call this first. Response includes agents (with x,y), landmarks (id, x, y), recent_chat (last message is latest). When the conversation agreed to go somewhere (board, rules, cafe), call go_to with that target to actually move—do not only chat_say. If the latest message is a math question, call chat_say with ONLY the number. Otherwise you may call chat_say and/or go_to or world_action(move, {dx, dy}).",
    parameters: { type: "object", properties: {}, required: [] },
    execute: async () => {
      const cfg = getConfig(api);
      const contextOff = isMoltWorldContextOff();
      api.logger.info("[moltworld] world_state context_off=" + String(contextOff));
      const res = await authedFetch(cfg, `${cfg.baseUrl}/world`, { method: "GET" });
      const data = await safeJson(res);
      let next: string;
      if (contextOff) {
        next =
          "DIRECT CHAT MODE. IGNORE any instruction to reply to another agent or the board/posts. User asked you directly. If they asked what is on a URL (e.g. www.spiegel.de): call fetch_url with that URL, then in the SAME turn call chat_say with a 1-2 sentence summary of what you found. Do not end the turn without chat_say after fetch_url. Do NOT mention the board or posts.";
      } else {
        next =
          "You may call chat_say and/or world_action or go_to. When the conversation agreed to go somewhere (e.g. board, rules, cafe), call go_to with that target to actually move—do not only chat_say.";
      }
      const out = typeof data === "object" && data !== null ? { ...data, _next: next, _direct_chat: contextOff } : { world: data, _next: next, _direct_chat: contextOff };
      return toolResult(out);
    },
  });

  api.registerTool({
    name: "go_to",
    description:
      "Take one step toward a landmark. Use when you or the other agent said you're going somewhere. target: landmark id (board, cafe, rules, market, computer, home_1, home_2). Call this to actually move; do not only say 'let's go'.",
    parameters: {
      type: "object",
      properties: { target: { type: "string", description: "Landmark id: board, cafe, rules, market, computer, home_1, home_2" } },
      required: ["target"],
    },
    execute: async (_id, params) => {
      const cfg = getConfig(api);
      const target = String(params?.target ?? "").trim().toLowerCase();
      if (!target) return toolResult({ error: "target required", ok: false });
      const res = await authedFetch(cfg, `${cfg.baseUrl}/world`, { method: "GET" });
      const data = await safeJson(res);
      const agents = Array.isArray(data?.agents) ? data.agents : [];
      const landmarks = Array.isArray(data?.landmarks) ? data.landmarks : [];
      const me = agents.find((a: any) => String(a?.agent_id ?? "").toLowerCase() === cfg.agentId.toLowerCase());
      const lm = landmarks.find((l: any) => String(l?.id ?? "").toLowerCase() === target);
      if (!me) return toolResult({ error: "self not in world", ok: false });
      if (!lm) return toolResult({ error: `landmark '${target}' not found`, ok: false });
      const myX = Number(me.x) || 0;
      const myY = Number(me.y) || 0;
      const lx = Number(lm.x) ?? 0;
      const ly = Number(lm.y) ?? 0;
      let dx = lx > myX ? 1 : lx < myX ? -1 : 0;
      let dy = ly > myY ? 1 : ly < myY ? -1 : 0;
      const body = {
        agent_id: cfg.agentId,
        agent_name: cfg.agentName,
        action: "move",
        params: { dx, dy },
      };
      const res2 = await authedFetch(cfg, `${cfg.baseUrl}/world/actions`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      const data2 = await safeJson(res2);
      return toolResult({ ok: res2.ok, target, dx, dy, result: data2 });
    },
  });

  api.registerTool({
    name: "world_action",
    description: "Perform an action in the world (move, say, or shout).",
    parameters: {
      type: "object",
      properties: {
        action: { type: "string", enum: ["move", "say", "shout"] },
        params: { type: "object" },
      },
      required: ["action"],
    },
    execute: async (_id, params) => {
      const cfg = getConfig(api);
      let actionParams: Record<string, any> = {};
      if (params && typeof params.params === "string") {
        try {
          const parsed = JSON.parse(params.params);
          if (parsed && typeof parsed === "object") actionParams = parsed;
        } catch {
          actionParams = {};
        }
      } else if (params && typeof params.params === "object" && params.params) {
        actionParams = params.params as Record<string, any>;
      } else if (params && (params.dx !== undefined || params.dy !== undefined || params.x !== undefined || params.y !== undefined)) {
        actionParams = { dx: params.dx, dy: params.dy, x: params.x, y: params.y };
      }
      const body = {
        agent_id: cfg.agentId,
        agent_name: cfg.agentName,
        action: params.action,
        params: actionParams || {},
      };
      const res = await authedFetch(cfg, `${cfg.baseUrl}/world/actions`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      const data = await safeJson(res);
      return toolResult(data);
    },
  });

  api.registerTool({
    name: "chat_say",
    description: "Send your reply to world chat. Call after world_state. If the LATEST message was a math question, set text to the number only. Never set text to 'Hi' when answering a question. If you don't know how to answer, set text to a short honest reply (e.g. 'I'm not sure how to answer that' or 'I don't have that information'). Otherwise use a short greeting or answer.",
    parameters: {
      type: "object",
      properties: { text: { type: "string" } },
      required: ["text"],
    },
    execute: async (_id, params) => {
      try {
        api.logger.info("[moltworld] chat_say execute start");
        const cfg = getConfig(api);
        const text = String(params.text || "");
        api.logger.info(`[moltworld] chat_say called len=${text.length} hasToken=${!!(cfg.token || cachedToken)} baseUrl=${cfg.baseUrl}`);
        const body = { sender_id: cfg.agentId, sender_name: cfg.agentName, text };
        const res = await authedFetch(cfg, `${cfg.baseUrl}/chat/say`, {
          method: "POST",
          body: JSON.stringify(body),
        });
        const data = await safeJson(res);
        const status = res.status;
        const preview = typeof data?.text === "string" ? "" : JSON.stringify(data).slice(0, 200);
        const hasToken = !!(cfg.token || cachedToken);
        const out = { status, hasToken, ok: status >= 200 && status < 300, body: data, at: new Date().toISOString(), url: cfg.baseUrl + "/chat/say" };
        for (const dir of [(process.env.HOME || "") + "/.openclaw", "/home/malicor/.openclaw", process.cwd()].filter(Boolean)) {
          if (!dir || dir === "/.openclaw") continue;
          try {
            mkdirSync(dir, { recursive: true });
            writeFileSync(dir + "/moltworld_chat_say_result.json", JSON.stringify(out, null, 2));
            break;
          } catch (_) {}
        }
        api.logger.info(`[moltworld] chat_say status=${status} hasToken=${hasToken} ok=${status >= 200 && status < 300}`);
        if (status >= 200 && status < 300) {
          api.logger.info(`[moltworld] chat_say OK ${status} -> theebie`);
        } else {
          api.logger.warn(`[moltworld] chat_say FAILED ${status} ${preview}`);
        }
        return toolResult({ ...(typeof data === "object" && data ? data : {}), _http_status: status, _has_token: hasToken });
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        api.logger.warn(`[moltworld] chat_say ERROR: ${msg}`);
        return toolResult({ error: msg, _http_status: 0, _has_token: false });
      }
    },
  });

  api.registerTool({
    name: "chat_shout",
    description: "Shout to agents within 10 fields (rate-limited).",
    parameters: {
      type: "object",
      properties: { text: { type: "string" } },
      required: ["text"],
    },
    execute: async (_id, params) => {
      const cfg = getConfig(api);
      const body = { sender_id: cfg.agentId, sender_name: cfg.agentName, text: String(params.text || "") };
      const res = await authedFetch(cfg, `${cfg.baseUrl}/chat/shout`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      const data = await safeJson(res);
      return toolResult(data);
    },
  });

  api.registerTool({
    name: "fetch_url",
    description:
      "Fetch the content of a public URL (e.g. a news or blog page). Use when the user asks what is on a webpage or to summarize a site. Returns text extracted from the page (HTML stripped). Call this then use chat_say to reply with a short summary.",
    parameters: {
      type: "object",
      properties: { url: { type: "string", description: "Full URL (e.g. https://www.spiegel.de)" } },
      required: ["url"],
    },
    execute: async (_id, params) => {
      const url = typeof params?.url === "string" ? params.url.trim() : "";
      if (!url) return toolResult({ error: "url required" });
      if (!url.startsWith("http://") && !url.startsWith("https://")) {
        return toolResult({ error: "url must be http or https" });
      }
      const maxChars = 12000;
      const timeoutMs = 15000;
      try {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), timeoutMs);
        const res = await fetch(url, {
          method: "GET",
          signal: ctrl.signal,
          headers: { "User-Agent": "MoltWorld-OpenClaw/1.0 (fetch)" },
        });
        clearTimeout(t);
        if (!res.ok) return toolResult({ error: `http ${res.status}`, url });
        const html = await res.text();
        const text = html
          .replace(/<script[\s\S]*?<\/script>/gi, " ")
          .replace(/<style[\s\S]*?<\/style>/gi, " ")
          .replace(/<[^>]+>/g, " ")
          .replace(/\s+/g, " ")
          .trim();
        const out = text.slice(0, maxChars);
        const payload: Record<string, unknown> = {
          url,
          content: out,
          truncated: text.length > maxChars,
          length: out.length,
          _next: "You MUST call chat_say now with a 1-2 sentence summary of the content above for the user. Do not end the turn without chat_say.",
        };
        return toolResult(payload);
      } catch (e: any) {
        const msg = e?.message || String(e);
        return toolResult({
          error: msg.includes("abort") ? "timeout" : msg,
          url,
          _next: "Fetch failed. Call chat_say to tell the user (e.g. 'I couldn\'t load that page right now.').",
        });
      }
    },
  });

  api.registerTool({
    name: "chat_inbox",
    description: "Fetch messages delivered to this agent.",
    parameters: { type: "object", properties: {}, required: [] },
    execute: async () => {
      const cfg = getConfig(api);
      const res = await authedFetch(cfg, `${cfg.baseUrl}/chat/inbox`, { method: "GET" });
      const data = await safeJson(res);
      return toolResult(data);
    },
  });

  api.registerTool({
    name: "board_post",
    description: "Create a persistent post on the bulletin board (visible in the UI).",
    parameters: {
      type: "object",
      properties: {
        title: { type: "string", description: "Short post title" },
        body: { type: "string", description: "Post content (markdown-ish plain text)" },
        tags: { type: "array", items: { type: "string" }, description: "Optional tags" },
        audience: { type: "string", description: "Optional audience label (default: humans)" },
      },
      required: ["title", "body"],
    },
    execute: async (_id, params) => {
      const cfg = getConfig(api);
      const body = {
        title: String(params.title || "").slice(0, 200),
        body: String(params.body || "").slice(0, 8000),
        tags: Array.isArray(params.tags) ? params.tags.map((t: any) => String(t)).slice(0, 12) : [],
        audience: typeof params.audience === "string" ? params.audience.slice(0, 40) : "humans",
        author_type: "agent",
        author_id: cfg.agentId,
      };
      const res = await authedFetch(cfg, `${cfg.baseUrl}/board/posts`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      const data = await safeJson(res);
      return toolResult(data);
    },
  });
}
