#!/bin/bash
# Setup Azure Workload Identity for AKS
# This script configures federated credentials for the IC Autopilot service account

set -e

# Configuration - Override these with environment variables or command line args
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-ic-autopilot}"
AKS_CLUSTER="${AKS_CLUSTER:-aks-ic-autopilot}"
LOCATION="${LOCATION:-eastus}"
MANAGED_IDENTITY_NAME="${MANAGED_IDENTITY_NAME:-id-ic-autopilot}"
NAMESPACE="${NAMESPACE:-ic-autopilot}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-ic-autopilot-sa}"

# Key Vault and Storage Account names (optional - for role assignments)
KEY_VAULT_NAME="${KEY_VAULT_NAME:-}"
STORAGE_ACCOUNT_NAME="${STORAGE_ACCOUNT_NAME:-}"

echo "🚀 Setting up Workload Identity for IC Autopilot"
echo "================================================"
echo "Resource Group: $RESOURCE_GROUP"
echo "AKS Cluster: $AKS_CLUSTER"
echo "Managed Identity: $MANAGED_IDENTITY_NAME"
echo "Namespace: $NAMESPACE"
echo "Service Account: $SERVICE_ACCOUNT_NAME"
echo ""

# Get AKS OIDC Issuer URL
echo "📡 Getting AKS OIDC Issuer URL..."
AKS_OIDC_ISSUER=$(az aks show \
    --name $AKS_CLUSTER \
    --resource-group $RESOURCE_GROUP \
    --query "oidcIssuerProfile.issuerUrl" \
    --output tsv)

if [ -z "$AKS_OIDC_ISSUER" ]; then
    echo "❌ OIDC issuer not found. Enabling OIDC on AKS cluster..."
    az aks update \
        --name $AKS_CLUSTER \
        --resource-group $RESOURCE_GROUP \
        --enable-oidc-issuer \
        --enable-workload-identity

    AKS_OIDC_ISSUER=$(az aks show \
        --name $AKS_CLUSTER \
        --resource-group $RESOURCE_GROUP \
        --query "oidcIssuerProfile.issuerUrl" \
        --output tsv)
fi

echo "✅ OIDC Issuer: $AKS_OIDC_ISSUER"

# Create or get Managed Identity
echo ""
echo "🔑 Creating/Getting Managed Identity..."
IDENTITY_EXISTS=$(az identity show \
    --name $MANAGED_IDENTITY_NAME \
    --resource-group $RESOURCE_GROUP \
    --query "id" \
    --output tsv 2>/dev/null || echo "")

if [ -z "$IDENTITY_EXISTS" ]; then
    az identity create \
        --name $MANAGED_IDENTITY_NAME \
        --resource-group $RESOURCE_GROUP \
        --location $LOCATION
    echo "✅ Created Managed Identity: $MANAGED_IDENTITY_NAME"
else
    echo "✅ Using existing Managed Identity: $MANAGED_IDENTITY_NAME"
fi

# Get Identity details
CLIENT_ID=$(az identity show \
    --name $MANAGED_IDENTITY_NAME \
    --resource-group $RESOURCE_GROUP \
    --query "clientId" \
    --output tsv)

PRINCIPAL_ID=$(az identity show \
    --name $MANAGED_IDENTITY_NAME \
    --resource-group $RESOURCE_GROUP \
    --query "principalId" \
    --output tsv)

echo "   Client ID: $CLIENT_ID"
echo "   Principal ID: $PRINCIPAL_ID"

# Create Federated Credential
echo ""
echo "🔗 Creating Federated Credential..."
FEDERATED_CRED_NAME="fc-${AKS_CLUSTER}-${NAMESPACE}-${SERVICE_ACCOUNT_NAME}"

az identity federated-credential create \
    --name $FEDERATED_CRED_NAME \
    --identity-name $MANAGED_IDENTITY_NAME \
    --resource-group $RESOURCE_GROUP \
    --issuer $AKS_OIDC_ISSUER \
    --subject "system:serviceaccount:${NAMESPACE}:${SERVICE_ACCOUNT_NAME}" \
    --audiences "api://AzureADTokenExchange" \
    2>/dev/null || echo "Federated credential already exists"

echo "✅ Federated Credential configured"

# Assign roles to Managed Identity
echo ""
echo "📋 Assigning roles to Managed Identity..."

SUBSCRIPTION_ID=$(az account show --query "id" --output tsv)

# Key Vault Secrets User (for Key Vault CSI)
if [ -n "$KEY_VAULT_NAME" ]; then
    echo "   Assigning Key Vault Secrets User role..."
    KV_ID=$(az keyvault show --name $KEY_VAULT_NAME --query "id" --output tsv 2>/dev/null || echo "")
    if [ -n "$KV_ID" ]; then
        az role assignment create \
            --role "Key Vault Secrets User" \
            --assignee-object-id $PRINCIPAL_ID \
            --assignee-principal-type ServicePrincipal \
            --scope $KV_ID \
            2>/dev/null || echo "   Role already assigned"
        echo "   ✅ Key Vault Secrets User assigned"
    else
        echo "   ⚠️  Key Vault not found: $KEY_VAULT_NAME"
    fi
fi

# Storage Blob Data Contributor (for artifact storage)
if [ -n "$STORAGE_ACCOUNT_NAME" ]; then
    echo "   Assigning Storage Blob Data Contributor role..."
    STORAGE_ID=$(az storage account show --name $STORAGE_ACCOUNT_NAME --query "id" --output tsv 2>/dev/null || echo "")
    if [ -n "$STORAGE_ID" ]; then
        az role assignment create \
            --role "Storage Blob Data Contributor" \
            --assignee-object-id $PRINCIPAL_ID \
            --assignee-principal-type ServicePrincipal \
            --scope $STORAGE_ID \
            2>/dev/null || echo "   Role already assigned"
        echo "   ✅ Storage Blob Data Contributor assigned"
    else
        echo "   ⚠️  Storage Account not found: $STORAGE_ACCOUNT_NAME"
    fi
fi

# Cognitive Services OpenAI User (for Azure OpenAI)
echo "   Assigning Cognitive Services OpenAI User role (subscription scope)..."
az role assignment create \
    --role "Cognitive Services OpenAI User" \
    --assignee-object-id $PRINCIPAL_ID \
    --assignee-principal-type ServicePrincipal \
    --scope "/subscriptions/$SUBSCRIPTION_ID" \
    2>/dev/null || echo "   Role already assigned"
echo "   ✅ Cognitive Services OpenAI User assigned"

# Search Index Data Contributor (for Azure AI Search)
echo "   Assigning Search Index Data Contributor role (subscription scope)..."
az role assignment create \
    --role "Search Index Data Contributor" \
    --assignee-object-id $PRINCIPAL_ID \
    --assignee-principal-type ServicePrincipal \
    --scope "/subscriptions/$SUBSCRIPTION_ID" \
    2>/dev/null || echo "   Role already assigned"
echo "   ✅ Search Index Data Contributor assigned"

echo ""
echo "================================================"
echo "✅ Workload Identity setup complete!"
echo ""
echo "Use these values in your Helm deployment:"
echo ""
echo "  azure:"
echo "    workloadIdentity:"
echo "      enabled: true"
echo "      clientId: \"$CLIENT_ID\""
echo ""
echo "Or with helm install:"
echo ""
echo "  helm install ic-autopilot ./ic-autopilot \\"
echo "    --set azure.workloadIdentity.clientId=$CLIENT_ID \\"
echo "    --set azure.tenantId=$(az account show --query tenantId -o tsv)"
echo ""
