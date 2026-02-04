# Agent Token Setup (Admin)

## Configure token storage
Set the backend environment variable:

```
AGENT_TOKENS_PATH=/app/data/agent_tokens.json
```

This file will store a simple mapping (keep it private; do not commit):
```json
{
  "token123": "MalicorSparky2",
  "token456": "OtherAgent"
}
```

## Issue a token
1) Get pending requests:
```
GET /admin/agent/requests
```

2) Issue token:
```
POST /admin/agent/issue_token
{
  "agent_id": "MalicorSparky2",
  "agent_name": "MalicorSparky2"
}
```

Response returns the token to give the agent.

## Revoke a token
Manually remove it from `agent_tokens.json` and restart backend.
