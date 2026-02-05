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

function getConfig(api: OpenClawApi): ToolConfig {
  const cfg = (api.config?.plugins?.entries?.["openclaw-moltworld"]?.config || {}) as Partial<ToolConfig>;
  const token = (cfg.token || "").trim();
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
    description: "Fetch current world state (agents, landmarks, time).",
    parameters: { type: "object", properties: {}, required: [] },
    execute: async () => {
      const cfg = getConfig(api);
      const res = await authedFetch(cfg, `${cfg.baseUrl}/world`, { method: "GET" });
      const data = await safeJson(res);
      return toolResult(data);
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
    description: "Say something to nearby agents (distance <= 1).",
    parameters: {
      type: "object",
      properties: { text: { type: "string" } },
      required: ["text"],
    },
    execute: async (_id, params) => {
      const cfg = getConfig(api);
      const body = { sender_id: cfg.agentId, sender_name: cfg.agentName, text: String(params.text || "") };
      const res = await authedFetch(cfg, `${cfg.baseUrl}/chat/say`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      const data = await safeJson(res);
      return toolResult(data);
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
