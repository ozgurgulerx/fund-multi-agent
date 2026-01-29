# IC Autopilot Infrastructure

This directory contains infrastructure-as-code for deploying IC Autopilot to Azure.

## Directory Structure

```
infra/
├── helm/
│   ├── ic-autopilot/          # Helm chart
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   └── templates/
│   ├── values-dev.yaml        # Development overrides
│   └── values-prod.yaml       # Production overrides
└── scripts/
    ├── provision-azure-resources.sh
    └── setup-workload-identity.sh
```

## Prerequisites

- Azure CLI (`az`) installed and logged in
- `kubectl` configured
- `helm` v3+
- AKS cluster with OIDC and Workload Identity enabled

## Quick Start

### 1. Provision Azure Resources (Optional)

If you need to create a new AKS cluster and supporting resources:

```bash
cd infra/scripts
./provision-azure-resources.sh
```

### 2. Setup Workload Identity

Configure managed identity for secure access to Azure services:

```bash
export RESOURCE_GROUP=rg-ic-autopilot
export AKS_CLUSTER=aks-ic-autopilot
export KEY_VAULT_NAME=kv-ic-autopilot
export STORAGE_ACCOUNT_NAME=sticautopilot

./setup-workload-identity.sh
```

### 3. Deploy with Helm

**Development:**
```bash
helm install ic-autopilot ./helm/ic-autopilot \
  -f ./helm/values-dev.yaml \
  --namespace ic-autopilot-dev \
  --create-namespace
```

**Production:**
```bash
helm install ic-autopilot ./helm/ic-autopilot \
  -f ./helm/values-prod.yaml \
  --set azure.workloadIdentity.clientId=<CLIENT_ID> \
  --set azure.tenantId=<TENANT_ID> \
  --set backend.env.AZURE_OPENAI_ENDPOINT=<ENDPOINT> \
  --set backend.env.AZURE_SEARCH_ENDPOINT=<ENDPOINT> \
  --set backend.env.AZURE_STORAGE_ACCOUNT=<ACCOUNT> \
  --set backend.env.POSTGRES_HOST=<HOST> \
  --set secrets.azureKeyVault.vaultName=<VAULT> \
  --namespace ic-autopilot \
  --create-namespace
```

### 4. Upgrade Deployment

```bash
helm upgrade ic-autopilot ./helm/ic-autopilot \
  -f ./helm/values-prod.yaml \
  --set image.tag=<NEW_TAG>
```

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Azure Kubernetes Service                   │
│                                                                   │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │   Ingress   │───▶│   Backend   │───▶│    Redis    │          │
│  │   (NGINX)   │    │  (FastAPI)  │    │  (Streams)  │          │
│  └─────────────┘    └─────────────┘    └─────────────┘          │
│         │                  │                                      │
│         │                  │ Workload Identity                    │
└─────────│──────────────────│─────────────────────────────────────┘
          │                  │
          ▼                  ▼
┌─────────────────┐  ┌──────────────────────────────────────────┐
│  App Service    │  │              Azure Services               │
│  (Frontend)     │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  Next.js SSR    │  │  │ OpenAI   │ │ Storage  │ │ Key Vault│ │
└─────────────────┘  │  │ Service  │ │ Account  │ │          │ │
                     │  └──────────┘ └──────────┘ └──────────┘ │
                     │  ┌──────────┐ ┌──────────┐              │
                     │  │AI Search │ │PostgreSQL│              │
                     │  └──────────┘ └──────────┘              │
                     └──────────────────────────────────────────┘
```

## Configuration

### Workload Identity

Workload Identity provides secure, credential-free access to Azure services:

1. A User-Assigned Managed Identity is created
2. Federated credentials link the K8s service account to the identity
3. Azure SDK in pods automatically uses the identity for authentication

No API keys needed for:
- Azure Blob Storage (artifact store)
- Azure OpenAI (LLM calls)
- Azure AI Search (document retrieval)
- Azure Key Vault (secret retrieval)

### Secrets Management

**Option 1: Azure Key Vault (Recommended for Production)**
```yaml
secrets:
  azureKeyVault:
    enabled: true
    vaultName: kv-ic-autopilot
```

**Option 2: Kubernetes Secrets (Development Only)**
```yaml
secrets:
  inline:
    enabled: true
    azureOpenaiApiKey: "..."
```

### Autoscaling

HPA is configured to scale backend pods based on CPU/memory:

```yaml
backend:
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
    targetCPUUtilization: 70
```

## Troubleshooting

### Check Pod Status
```bash
kubectl get pods -n ic-autopilot
kubectl describe pod <pod-name> -n ic-autopilot
```

### View Logs
```bash
kubectl logs -f deployment/ic-autopilot-backend -n ic-autopilot
```

### Test Workload Identity
```bash
kubectl exec -it deployment/ic-autopilot-backend -n ic-autopilot -- \
  az account get-access-token --resource https://storage.azure.com/
```

### Verify Key Vault Access
```bash
kubectl exec -it deployment/ic-autopilot-backend -n ic-autopilot -- \
  cat /mnt/secrets-store/AZURE_OPENAI_API_KEY
```
