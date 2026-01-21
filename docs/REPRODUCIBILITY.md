# Reproducibility Checklist

Goal: ensure this project can be recreated later in a different repo with minimal ambiguity.

## Pin versions
- Record OS + driver versions on DGX nodes.
- Pin Python versions and key packages (requirements + lockfile).
- Pin model versions (exact model IDs + quantization + runtime config).

## Environment
- Document required env vars in `.env.example`.
- Separate secrets from repo; document how to provision secrets safely.

## Data
- DB schema migrations (Alembic or equivalent).
- Seed data / fixtures for demo worlds.
- Backup/restore instructions.

## Deployment
- docker-compose for v1
- ansible inventory + playbook for two-node deployment (optional)
- documented ports and DNS assumptions

## Testing
- Smoke tests:
  - backend `/world` responds
  - websocket emits updates
  - agent can move and post to board
  - reward/penalty updates ledger and entitlements

