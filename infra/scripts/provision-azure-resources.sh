#!/bin/bash
# Provision Azure resources for IC Autopilot
# This creates AKS, ACR, Storage, Key Vault if they don't exist

set -e

# Configuration
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-ic-autopilot}"
LOCATION="${LOCATION:-eastus}"
AKS_CLUSTER="${AKS_CLUSTER:-aks-ic-autopilot}"
ACR_NAME="${ACR_NAME:-aistartuptr}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-sticautopilot$(openssl rand -hex 4)}"
KEY_VAULT_NAME="${KEY_VAULT_NAME:-kv-ic-autopilot-$(openssl rand -hex 4)}"

# AKS Configuration
AKS_NODE_COUNT="${AKS_NODE_COUNT:-2}"
AKS_NODE_VM_SIZE="${AKS_NODE_VM_SIZE:-Standard_D4s_v3}"
AKS_K8S_VERSION="${AKS_K8S_VERSION:-1.29}"

echo "🚀 Provisioning Azure Resources for IC Autopilot"
echo "================================================"
echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo "AKS Cluster: $AKS_CLUSTER"
echo "ACR: $ACR_NAME"
echo "Storage Account: $STORAGE_ACCOUNT"
echo "Key Vault: $KEY_VAULT_NAME"
echo ""

# Create Resource Group
echo "📁 Creating Resource Group..."
az group create \
    --name $RESOURCE_GROUP \
    --location $LOCATION \
    --output none
echo "✅ Resource Group created"

# Create ACR (if not exists)
echo ""
echo "🐳 Creating/Checking Container Registry..."
ACR_EXISTS=$(az acr show --name $ACR_NAME --query "id" --output tsv 2>/dev/null || echo "")
if [ -z "$ACR_EXISTS" ]; then
    az acr create \
        --name $ACR_NAME \
        --resource-group $RESOURCE_GROUP \
        --sku Standard \
        --admin-enabled false \
        --output none
    echo "✅ ACR created: $ACR_NAME"
else
    echo "✅ Using existing ACR: $ACR_NAME"
fi

# Create AKS Cluster
echo ""
echo "☸️  Creating/Checking AKS Cluster..."
AKS_EXISTS=$(az aks show --name $AKS_CLUSTER --resource-group $RESOURCE_GROUP --query "id" --output tsv 2>/dev/null || echo "")
if [ -z "$AKS_EXISTS" ]; then
    az aks create \
        --name $AKS_CLUSTER \
        --resource-group $RESOURCE_GROUP \
        --location $LOCATION \
        --node-count $AKS_NODE_COUNT \
        --node-vm-size $AKS_NODE_VM_SIZE \
        --kubernetes-version $AKS_K8S_VERSION \
        --enable-managed-identity \
        --enable-oidc-issuer \
        --enable-workload-identity \
        --attach-acr $ACR_NAME \
        --network-plugin azure \
        --network-policy azure \
        --generate-ssh-keys \
        --output none
    echo "✅ AKS cluster created: $AKS_CLUSTER"
else
    echo "✅ Using existing AKS cluster: $AKS_CLUSTER"

    # Ensure OIDC and Workload Identity are enabled
    echo "   Checking OIDC/Workload Identity..."
    OIDC_ENABLED=$(az aks show --name $AKS_CLUSTER --resource-group $RESOURCE_GROUP --query "oidcIssuerProfile.enabled" --output tsv)
    if [ "$OIDC_ENABLED" != "true" ]; then
        echo "   Enabling OIDC and Workload Identity..."
        az aks update \
            --name $AKS_CLUSTER \
            --resource-group $RESOURCE_GROUP \
            --enable-oidc-issuer \
            --enable-workload-identity \
            --output none
    fi
fi

# Create Storage Account
echo ""
echo "📦 Creating/Checking Storage Account..."
STORAGE_EXISTS=$(az storage account show --name $STORAGE_ACCOUNT --query "id" --output tsv 2>/dev/null || echo "")
if [ -z "$STORAGE_EXISTS" ]; then
    az storage account create \
        --name $STORAGE_ACCOUNT \
        --resource-group $RESOURCE_GROUP \
        --location $LOCATION \
        --sku Standard_LRS \
        --kind StorageV2 \
        --allow-blob-public-access false \
        --output none

    # Create container for artifacts
    az storage container create \
        --name ic-artifacts \
        --account-name $STORAGE_ACCOUNT \
        --auth-mode login \
        --output none

    echo "✅ Storage Account created: $STORAGE_ACCOUNT"
else
    echo "✅ Using existing Storage Account: $STORAGE_ACCOUNT"
fi

# Create Key Vault
echo ""
echo "🔐 Creating/Checking Key Vault..."
KV_EXISTS=$(az keyvault show --name $KEY_VAULT_NAME --query "id" --output tsv 2>/dev/null || echo "")
if [ -z "$KV_EXISTS" ]; then
    az keyvault create \
        --name $KEY_VAULT_NAME \
        --resource-group $RESOURCE_GROUP \
        --location $LOCATION \
        --enable-rbac-authorization true \
        --output none
    echo "✅ Key Vault created: $KEY_VAULT_NAME"

    echo "   Setting up placeholder secrets (update with real values)..."
    az keyvault secret set \
        --vault-name $KEY_VAULT_NAME \
        --name "azure-openai-api-key" \
        --value "PLACEHOLDER-UPDATE-ME" \
        --output none
    az keyvault secret set \
        --vault-name $KEY_VAULT_NAME \
        --name "azure-search-api-key" \
        --value "PLACEHOLDER-UPDATE-ME" \
        --output none
    az keyvault secret set \
        --vault-name $KEY_VAULT_NAME \
        --name "postgres-password" \
        --value "PLACEHOLDER-UPDATE-ME" \
        --output none
else
    echo "✅ Using existing Key Vault: $KEY_VAULT_NAME"
fi

# Install NGINX Ingress Controller
echo ""
echo "🌐 Installing NGINX Ingress Controller..."
az aks get-credentials --name $AKS_CLUSTER --resource-group $RESOURCE_GROUP --overwrite-existing

# Check if ingress-nginx namespace exists
INGRESS_EXISTS=$(kubectl get namespace ingress-nginx --ignore-not-found -o name)
if [ -z "$INGRESS_EXISTS" ]; then
    kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.0/deploy/static/provider/cloud/deploy.yaml
    echo "✅ NGINX Ingress Controller installed"
else
    echo "✅ NGINX Ingress Controller already installed"
fi

# Install Secrets Store CSI Driver
echo ""
echo "🔑 Installing Secrets Store CSI Driver..."
helm repo add csi-secrets-store-provider-azure https://azure.github.io/secrets-store-csi-driver-provider-azure/charts 2>/dev/null || true
helm repo update

SECRETS_CSI_INSTALLED=$(helm list -n kube-system -q | grep -c "csi-secrets-store" || echo "0")
if [ "$SECRETS_CSI_INSTALLED" == "0" ]; then
    helm install csi-secrets-store-provider-azure \
        csi-secrets-store-provider-azure/csi-secrets-store-provider-azure \
        --namespace kube-system \
        --set secrets-store-csi-driver.syncSecret.enabled=true
    echo "✅ Secrets Store CSI Driver installed"
else
    echo "✅ Secrets Store CSI Driver already installed"
fi

# Output summary
echo ""
echo "================================================"
echo "✅ Azure Resources Provisioned!"
echo ""
echo "Resources:"
echo "  - Resource Group: $RESOURCE_GROUP"
echo "  - AKS Cluster: $AKS_CLUSTER"
echo "  - ACR: $ACR_NAME.azurecr.io"
echo "  - Storage Account: $STORAGE_ACCOUNT"
echo "  - Key Vault: $KEY_VAULT_NAME"
echo ""
echo "Next steps:"
echo "1. Run setup-workload-identity.sh to configure managed identity"
echo "2. Update Key Vault secrets with real values"
echo "3. Deploy with Helm:"
echo ""
echo "   helm install ic-autopilot ./infra/helm/ic-autopilot \\"
echo "     -f ./infra/helm/values-prod.yaml \\"
echo "     --set azure.workloadIdentity.clientId=<CLIENT_ID> \\"
echo "     --set azure.tenantId=$(az account show --query tenantId -o tsv) \\"
echo "     --set backend.env.AZURE_STORAGE_ACCOUNT=$STORAGE_ACCOUNT \\"
echo "     --set secrets.azureKeyVault.vaultName=$KEY_VAULT_NAME"
echo ""
