# Claude Code Project Instructions

## Critical Rules

### DO NOT MODIFY
The following projects and resources must NEVER be modified:
- **fund-rag namespace on AKS** - Do not touch deployments, services, or configurations
- **fund-rag-poc project** - This is a separate production system
- **rg-fund-rag resource group** - Only add new resources, never modify existing ones

### DATABASE PROTECTION - STRICT & NON-NEGOTIABLE
**THIS IS AN ABSOLUTE RULE - NO EXCEPTIONS**

FORBIDDEN ACTIONS (will break production systems):
- ❌ ALTER TABLE - NEVER change table structure
- ❌ DROP TABLE - NEVER delete tables
- ❌ DROP SCHEMA - NEVER delete schemas
- ❌ TRUNCATE - NEVER empty tables
- ❌ DELETE FROM - NEVER delete rows from existing tables
- ❌ UPDATE - NEVER modify existing data
- ❌ Any DDL on existing objects

ALLOWED ACTIONS (only in ic_autopilot schema):
- ✅ CREATE SCHEMA ic_autopilot (if not exists)
- ✅ CREATE TABLE in ic_autopilot schema only
- ✅ CREATE INDEX in ic_autopilot schema only
- ✅ INSERT INTO ic_autopilot tables only
- ✅ SELECT from any table (read-only)

**The nport_funds schema and all existing tables are READ-ONLY.**
**Violating these rules will break the fund-rag-poc application.**

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
