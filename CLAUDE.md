# Claude Code Project Instructions

## Critical Rules

### DO NOT MODIFY
The following projects and resources must NEVER be modified:
- **fund-rag namespace on AKS** - Do not touch deployments, services, or configurations
- **fund-rag-poc project** - This is a separate production system
- **rg-fund-rag resource group** - Only add new resources, never modify existing ones

### DATABASE PROTECTION - CRITICAL
- **NEVER delete, modify, or drop existing database tables**
- **NEVER run ALTER TABLE, DROP TABLE, or TRUNCATE commands**
- **Only CREATE new tables in the ic_autopilot schema**
- **Read-only access to nport_funds schema** - only SELECT queries allowed
- **Do not modify existing schemas** (nport_funds, public, etc.)

If migrations need to be run, they must:
1. Only CREATE new objects (tables, indexes, schemas)
2. Never modify or delete existing data
3. Be reviewed by the user before execution

### Separate Deployments
- IC Autopilot uses the `ic-autopilot` namespace - keep it isolated
- Use separate resource names prefixed with `ic-autopilot-`
- Do not share secrets or configurations with fund-rag

## Project Structure

```
af-pii-multi-agent/
├── backend/          # FastAPI backend
├── frontend/         # Next.js frontend
├── worker/           # Workflow executors
├── infra/            # Helm charts and scripts
├── k8s/              # Kubernetes manifests
└── tests/            # Test suite
```

## Deployment Targets

- **Backend**: AKS cluster (aks-fund-rag), namespace: ic-autopilot
- **Frontend**: Azure App Service (ic-autopilot-frontend)
- **Database**: PostgreSQL (aistartupstr), schema: ic_autopilot

## Environment

- ACR: aistartuptr.azurecr.io
- Backend image: ic-autopilot-backend
- Frontend image: ic-autopilot-frontend
