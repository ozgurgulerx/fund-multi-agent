# Deploying Next.js Frontend to Azure App Service

This guide provides step-by-step instructions for deploying a Next.js frontend application to Azure App Service.

## Prerequisites

1. **Azure CLI** installed and logged in
   ```bash
   az login
   az account set --subscription "<your-subscription-id>"
   ```

2. **Node.js 18+** installed locally

3. **GitHub repository** (for CI/CD) or local build capability

---

## Part 1: Azure Resource Setup

### 1.1 Create Resource Group (if needed)

```bash
az group create \
  --name rg-your-project \
  --location eastus
```

### 1.2 Create App Service Plan

For production workloads, use a Premium plan. For dev/test, Basic (B1) is sufficient.

```bash
# Production (Premium V3)
az appservice plan create \
  --name asp-your-project \
  --resource-group rg-your-project \
  --location eastus \
  --sku P1V3 \
  --is-linux

# Dev/Test (Basic)
az appservice plan create \
  --name asp-your-project-dev \
  --resource-group rg-your-project \
  --location eastus \
  --sku B1 \
  --is-linux
```

### 1.3 Create Web App

```bash
az webapp create \
  --name your-frontend-app \
  --resource-group rg-your-project \
  --plan asp-your-project \
  --runtime "NODE:18-lts"
```

### 1.4 Configure App Settings

```bash
# Set Node.js version and build settings
az webapp config appsettings set \
  --name your-frontend-app \
  --resource-group rg-your-project \
  --settings \
    WEBSITE_NODE_DEFAULT_VERSION="~18" \
    SCM_DO_BUILD_DURING_DEPLOYMENT="true" \
    NEXT_PUBLIC_API_URL="https://your-backend-api.azurewebsites.net"
```

---

## Part 2: Project Configuration

### 2.1 Required Files

Ensure your Next.js project has these files configured:

#### `package.json`

```json
{
  "name": "your-frontend",
  "version": "1.0.0",
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start -p $PORT",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "14.x",
    "react": "18.x",
    "react-dom": "18.x"
  },
  "engines": {
    "node": ">=18.0.0"
  }
}
```

**Important**: The `start` script must use `$PORT` (Azure sets this environment variable).

#### `next.config.js` (or `next.config.mjs`)

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',  // Required for Azure App Service

  // Optional: Configure allowed image domains
  images: {
    domains: ['your-cdn.azureedge.net'],
  },

  // Optional: Environment variables available at build time
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  },
}

module.exports = nextConfig
```

**Critical**: The `output: 'standalone'` setting creates a minimal production build that includes only necessary files.

### 2.2 Startup Command

Create a startup script or configure directly in Azure:

```bash
az webapp config set \
  --name your-frontend-app \
  --resource-group rg-your-project \
  --startup-file "node server.js"
```

For standalone output, Next.js creates `server.js` in `.next/standalone/`.

---

## Part 3: Deployment Options

### Option A: GitHub Actions (Recommended)

#### 3A.1 Create Service Principal for OIDC

```bash
# Create service principal
az ad sp create-for-rbac \
  --name "sp-github-deploy-frontend" \
  --role contributor \
  --scopes /subscriptions/<subscription-id>/resourceGroups/rg-your-project \
  --sdk-auth
```

Save the output JSON - you'll need it for GitHub secrets.

#### 3A.2 Configure Federated Credentials (OIDC - Recommended)

```bash
# Get the App ID
APP_ID=$(az ad sp list --display-name "sp-github-deploy-frontend" --query "[0].appId" -o tsv)

# Create federated credential for main branch
az ad app federated-credential create \
  --id $APP_ID \
  --parameters '{
    "name": "github-main",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:your-org/your-repo:ref:refs/heads/main",
    "audiences": ["api://AzureADTokenExchange"]
  }'
```

#### 3A.3 GitHub Secrets

Add these secrets to your repository (Settings → Secrets → Actions):

| Secret Name | Value |
|-------------|-------|
| `AZURE_CLIENT_ID` | Service principal App ID |
| `AZURE_TENANT_ID` | Your Azure AD tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Your subscription ID |

#### 3A.4 GitHub Actions Workflow

Create `.github/workflows/deploy-frontend.yml`:

```yaml
name: Deploy Frontend to Azure App Service

on:
  push:
    branches: [main]
    paths:
      - 'frontend/**'
      - '.github/workflows/deploy-frontend.yml'
  workflow_dispatch:

env:
  AZURE_WEBAPP_NAME: your-frontend-app
  NODE_VERSION: '18.x'

permissions:
  id-token: write
  contents: read

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        working-directory: frontend
        run: npm ci

      - name: Build application
        working-directory: frontend
        run: npm run build
        env:
          NEXT_PUBLIC_API_URL: ${{ vars.NEXT_PUBLIC_API_URL }}

      - name: Prepare deployment package
        working-directory: frontend
        run: |
          # Copy standalone build
          cp -r .next/standalone ./deploy
          cp -r .next/static ./deploy/.next/static
          cp -r public ./deploy/public 2>/dev/null || true

          # Create package.json for Azure
          echo '{"scripts":{"start":"node server.js"}}' > ./deploy/package.json

      - name: Login to Azure
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Deploy to Azure Web App
        uses: azure/webapps-deploy@v3
        with:
          app-name: ${{ env.AZURE_WEBAPP_NAME }}
          package: frontend/deploy
```

### Option B: Azure CLI Direct Deploy

#### 3B.1 Build Locally

```bash
cd frontend
npm ci
npm run build
```

#### 3B.2 Prepare Deployment Package

```bash
# Create deployment directory
mkdir -p deploy
cp -r .next/standalone/* deploy/
cp -r .next/static deploy/.next/static
cp -r public deploy/public 2>/dev/null || true

# Zip for deployment
cd deploy
zip -r ../deploy.zip .
cd ..
```

#### 3B.3 Deploy

```bash
az webapp deploy \
  --name your-frontend-app \
  --resource-group rg-your-project \
  --src-path deploy.zip \
  --type zip
```

### Option C: VS Code Extension

1. Install **Azure App Service** extension
2. Sign in to Azure
3. Right-click on your App Service → **Deploy to Web App**
4. Select the `frontend/.next/standalone` folder

---

## Part 4: Environment Variables

### 4.1 Build-time vs Runtime Variables

| Variable Type | Prefix | When Available |
|---------------|--------|----------------|
| Build-time | `NEXT_PUBLIC_` | Baked into JS bundle during build |
| Runtime | No prefix | Available in API routes and server components |

### 4.2 Configure in Azure

```bash
# Build-time variables (set in GitHub Actions or build pipeline)
# These are baked into the build, not set in App Service

# Runtime variables (set in App Service)
az webapp config appsettings set \
  --name your-frontend-app \
  --resource-group rg-your-project \
  --settings \
    DATABASE_URL="your-connection-string" \
    BACKEND_API_KEY="your-api-key" \
    NODE_ENV="production"
```

### 4.3 Using GitHub Variables for Build-time Settings

In GitHub repository settings, add **Variables** (not secrets) for public values:

- `NEXT_PUBLIC_API_URL`: `https://your-backend.azurewebsites.net`
- `NEXT_PUBLIC_APP_NAME`: `Your App Name`

Reference in workflow:
```yaml
- name: Build
  env:
    NEXT_PUBLIC_API_URL: ${{ vars.NEXT_PUBLIC_API_URL }}
```

---

## Part 5: Custom Domain and SSL

### 5.1 Add Custom Domain

```bash
# Add custom domain
az webapp config hostname add \
  --webapp-name your-frontend-app \
  --resource-group rg-your-project \
  --hostname www.yourdomain.com

# Create managed certificate (free)
az webapp config ssl create \
  --name your-frontend-app \
  --resource-group rg-your-project \
  --hostname www.yourdomain.com

# Bind certificate
az webapp config ssl bind \
  --name your-frontend-app \
  --resource-group rg-your-project \
  --certificate-thumbprint <thumbprint-from-previous-command> \
  --ssl-type SNI
```

### 5.2 Force HTTPS

```bash
az webapp update \
  --name your-frontend-app \
  --resource-group rg-your-project \
  --https-only true
```

---

## Part 6: Monitoring and Logging

### 6.1 Enable Application Insights

```bash
# Create Application Insights
az monitor app-insights component create \
  --app ai-your-frontend \
  --location eastus \
  --resource-group rg-your-project \
  --application-type web

# Get instrumentation key
INSTRUMENTATION_KEY=$(az monitor app-insights component show \
  --app ai-your-frontend \
  --resource-group rg-your-project \
  --query instrumentationKey -o tsv)

# Configure in App Service
az webapp config appsettings set \
  --name your-frontend-app \
  --resource-group rg-your-project \
  --settings \
    APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=$INSTRUMENTATION_KEY" \
    ApplicationInsightsAgent_EXTENSION_VERSION="~3"
```

### 6.2 View Logs

```bash
# Stream live logs
az webapp log tail \
  --name your-frontend-app \
  --resource-group rg-your-project

# Download logs
az webapp log download \
  --name your-frontend-app \
  --resource-group rg-your-project \
  --log-file logs.zip
```

### 6.3 Enable Diagnostic Logging

```bash
az webapp log config \
  --name your-frontend-app \
  --resource-group rg-your-project \
  --application-logging filesystem \
  --detailed-error-messages true \
  --failed-request-tracing true \
  --web-server-logging filesystem
```

---

## Part 7: Troubleshooting

### 7.1 Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| 502 Bad Gateway | App not starting | Check startup command, ensure `server.js` exists |
| Missing static files | Static files not copied | Ensure `.next/static` is in deployment |
| Environment variables undefined | Build vs runtime confusion | Use `NEXT_PUBLIC_` prefix for client-side vars |
| Slow cold starts | Large bundle or B1 plan | Use Premium plan or enable Always On |
| CORS errors | Backend not configured | Add frontend URL to backend CORS settings |

### 7.2 Debug Startup Issues

```bash
# SSH into container
az webapp ssh \
  --name your-frontend-app \
  --resource-group rg-your-project

# Inside container, check:
ls -la /home/site/wwwroot/
cat /home/site/wwwroot/package.json
node /home/site/wwwroot/server.js
```

### 7.3 Check Deployment Logs

```bash
# View deployment history
az webapp deployment list \
  --name your-frontend-app \
  --resource-group rg-your-project

# View Kudu logs
# Navigate to: https://your-frontend-app.scm.azurewebsites.net/api/logstream
```

### 7.4 Health Check Configuration

```bash
az webapp config set \
  --name your-frontend-app \
  --resource-group rg-your-project \
  --generic-configurations '{"healthCheckPath": "/api/health"}'
```

Create `/app/api/health/route.ts`:
```typescript
export async function GET() {
  return Response.json({ status: 'healthy', timestamp: new Date().toISOString() });
}
```

---

## Part 8: Performance Optimization

### 8.1 Enable Always On (Prevents Cold Starts)

```bash
az webapp config set \
  --name your-frontend-app \
  --resource-group rg-your-project \
  --always-on true
```

**Note**: Requires Basic tier or higher.

### 8.2 Configure Auto-scaling

```bash
az monitor autoscale create \
  --resource-group rg-your-project \
  --resource your-frontend-app \
  --resource-type Microsoft.Web/sites \
  --name autoscale-frontend \
  --min-count 1 \
  --max-count 5 \
  --count 1

az monitor autoscale rule create \
  --resource-group rg-your-project \
  --autoscale-name autoscale-frontend \
  --condition "CpuPercentage > 70 avg 5m" \
  --scale out 1

az monitor autoscale rule create \
  --resource-group rg-your-project \
  --autoscale-name autoscale-frontend \
  --condition "CpuPercentage < 30 avg 5m" \
  --scale in 1
```

### 8.3 Enable Compression

Add to `next.config.js`:
```javascript
const nextConfig = {
  output: 'standalone',
  compress: true,
}
```

---

## Quick Reference: Complete Deployment Checklist

- [ ] Azure resources created (Resource Group, App Service Plan, Web App)
- [ ] `next.config.js` has `output: 'standalone'`
- [ ] `package.json` start script uses `$PORT`
- [ ] GitHub Actions workflow created
- [ ] Azure service principal created with OIDC
- [ ] GitHub secrets configured
- [ ] Environment variables set (build-time in workflow, runtime in App Service)
- [ ] Custom domain configured (optional)
- [ ] SSL certificate bound (optional)
- [ ] Application Insights enabled (optional)
- [ ] Always On enabled (recommended)
- [ ] Health check configured (recommended)

---

## Example: This Project's Configuration

For the `af-pii-multi-agent` frontend:

```bash
# Resources
Resource Group: rg-pii-multiagent
App Service Plan: asp-pii-multiagent (P1V3)
Web App: pii-multiagent-frontend

# Environment Variables
NEXT_PUBLIC_API_URL=https://pii-multiagent-backend.azurewebsites.net
NEXT_PUBLIC_WS_URL=wss://pii-multiagent-backend.azurewebsites.net

# GitHub Workflow: .github/workflows/deploy-frontend.yml
```
