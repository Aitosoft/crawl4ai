#!/bin/bash

# ==========================================
# Crawl4AI Azure Deployment Script with Key Vault Authentication
# ==========================================
# This script deploys Crawl4AI with simplified Bearer token authentication using Azure Key Vault

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
RESOURCE_GROUP="crawl4ai-v2-rg"
CONTAINER_APP="crawl4ai-v2-app"
ENVIRONMENT="crawl4ai-v2-env"
KEYVAULT_NAME="crawl4ai-v2-keyvault"
LOCATION="northeurope"
IMAGE="unclecode/crawl4ai:latest"
LOG_WORKSPACE="crawl4ai-v2-logs"

# Bearer token for internal use
BEARER_TOKEN="as070511sip772patat"

# Parse command line arguments
DRY_RUN=false
UPDATE_ONLY=false
NEW_TOKEN=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --update-only)
            UPDATE_ONLY=true
            shift
            ;;
        --new-token)
            NEW_TOKEN="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--dry-run] [--update-only] [--new-token TOKEN]"
            echo "  --dry-run      Show what would be done without executing"
            echo "  --update-only  Update existing container app only"
            echo "  --new-token    Set a new bearer token value"
            exit 0
            ;;
        *)
            echo "Unknown option $1"
            exit 1
            ;;
    esac
done

# Use new token if provided
if [[ -n "$NEW_TOKEN" ]]; then
    BEARER_TOKEN="$NEW_TOKEN"
fi

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to execute commands with dry-run support
execute_cmd() {
    local cmd="$1"
    local description="$2"
    
    print_status "$description"
    
    if [ "$DRY_RUN" = true ]; then
        echo "DRY RUN: $cmd"
        return 0
    fi
    
    echo "Executing: $cmd"
    if eval "$cmd"; then
        print_success "✅ $description completed"
        return 0
    else
        print_error "❌ $description failed"
        return 1
    fi
}

# Check if Azure CLI is installed and logged in
check_azure_cli() {
    if ! command -v az &> /dev/null; then
        print_error "Azure CLI is not installed. Please install it first."
        exit 1
    fi
    
    if ! az account show &> /dev/null; then
        print_error "Not logged in to Azure. Please run 'az login' first."
        exit 1
    fi
    
    print_success "Azure CLI is ready"
}

# Get current user for role assignments
get_current_user() {
    if [ "$DRY_RUN" = false ]; then
        CURRENT_USER=$(az account show --query user.name -o tsv)
        print_status "Current user: $CURRENT_USER"
    else
        CURRENT_USER="user@example.com"
    fi
}

# Main deployment function
deploy_crawl4ai_with_keyvault() {
    print_status "🚀 Starting Crawl4AI deployment with Key Vault authentication"
    print_status "📋 Configuration:"
    echo "   Resource Group: $RESOURCE_GROUP"
    echo "   Container App: $CONTAINER_APP"
    echo "   Key Vault: $KEYVAULT_NAME"
    echo "   Environment: $ENVIRONMENT"
    echo "   Location: $LOCATION"
    echo "   Image: $IMAGE"
    echo "   Bearer Token: ${BEARER_TOKEN:0:10}..."
    echo ""
    
    get_current_user
    
    if [ "$UPDATE_ONLY" = false ]; then
        # Create resource group
        execute_cmd "az group create --name $RESOURCE_GROUP --location $LOCATION" \
                   "Creating resource group"
        
        # Create Log Analytics workspace
        execute_cmd "az monitor log-analytics workspace create \
                      --resource-group $RESOURCE_GROUP \
                      --workspace-name $LOG_WORKSPACE \
                      --location $LOCATION" \
                   "Creating Log Analytics workspace"
        
        # Get workspace credentials
        if [ "$DRY_RUN" = false ]; then
            WORKSPACE_ID=$(az monitor log-analytics workspace show \
                         --resource-group $RESOURCE_GROUP \
                         --workspace-name $LOG_WORKSPACE \
                         --query customerId -o tsv)
            
            WORKSPACE_KEY=$(az monitor log-analytics workspace get-shared-keys \
                          --resource-group $RESOURCE_GROUP \
                          --workspace-name $LOG_WORKSPACE \
                          --query primarySharedKey -o tsv)
        fi
        
        # Create Container Apps environment
        execute_cmd "az containerapp env create \
                      --name $ENVIRONMENT \
                      --resource-group $RESOURCE_GROUP \
                      --location $LOCATION \
                      --logs-workspace-id $WORKSPACE_ID \
                      --logs-workspace-key $WORKSPACE_KEY" \
                   "Creating Container Apps environment"
        
        # Create Key Vault
        execute_cmd "az keyvault create \
                      --name $KEYVAULT_NAME \
                      --resource-group $RESOURCE_GROUP \
                      --location $LOCATION \
                      --sku standard" \
                   "Creating Key Vault"
        
        # Assign Key Vault permissions to current user
        execute_cmd "az role assignment create \
                      --role \"Key Vault Secrets Officer\" \
                      --assignee $CURRENT_USER \
                      --scope /subscriptions/\$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.KeyVault/vaults/$KEYVAULT_NAME" \
                   "Assigning Key Vault permissions to user"
        
        # Wait for role propagation
        if [ "$DRY_RUN" = false ]; then
            print_status "Waiting for role assignment propagation..."
            sleep 30
        fi
        
        # Create secret in Key Vault
        execute_cmd "az keyvault secret set \
                      --vault-name $KEYVAULT_NAME \
                      --name C4AI-TOKEN \
                      --value $BEARER_TOKEN" \
                   "Creating bearer token secret in Key Vault"
        
        # Create container app with managed identity
        execute_cmd "az containerapp create \
                      --name $CONTAINER_APP \
                      --resource-group $RESOURCE_GROUP \
                      --environment $ENVIRONMENT \
                      --image $IMAGE \
                      --target-port 11235 \
                      --ingress external \
                      --min-replicas 1 \
                      --max-replicas 3 \
                      --cpu 1.0 \
                      --memory 2.0Gi \
                      --system-assigned" \
                   "Creating container app with managed identity"
        
        # Get the managed identity principal ID
        if [ "$DRY_RUN" = false ]; then
            PRINCIPAL_ID=$(az containerapp identity show \
                         --name $CONTAINER_APP \
                         --resource-group $RESOURCE_GROUP \
                         --query principalId -o tsv)
        fi
        
        # Assign Key Vault permissions to container app
        execute_cmd "az role assignment create \
                      --role \"Key Vault Secrets User\" \
                      --assignee $PRINCIPAL_ID \
                      --scope /subscriptions/\$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.KeyVault/vaults/$KEYVAULT_NAME" \
                   "Assigning Key Vault permissions to container app"
        
        # Get secret URI
        if [ "$DRY_RUN" = false ]; then
            SECRET_URI=$(az keyvault secret show \
                       --vault-name $KEYVAULT_NAME \
                       --name C4AI-TOKEN \
                       --query id -o tsv)
        fi
        
        # Configure container app to use Key Vault secret
        execute_cmd "az containerapp secret set \
                      --name $CONTAINER_APP \
                      --resource-group $RESOURCE_GROUP \
                      --secrets c4ai-token=\"@Microsoft.KeyVault(SecretUri=$SECRET_URI)\"" \
                   "Configuring Key Vault secret reference"
        
        # Update environment variables
        execute_cmd "az containerapp update \
                      --name $CONTAINER_APP \
                      --resource-group $RESOURCE_GROUP \
                      --set-env-vars \
                        CRAWL4AI_API_TOKEN=secretref:c4ai-token \
                        ENVIRONMENT=production \
                        LOG_LEVEL=INFO \
                        MAX_CONCURRENT_REQUESTS=10 \
                        SECURITY_ENABLED=false \
                        JWT_ENABLED=false" \
                   "Updating environment variables"
    else
        # Update only mode
        if [[ -n "$NEW_TOKEN" ]]; then
            execute_cmd "az keyvault secret set \
                          --vault-name $KEYVAULT_NAME \
                          --name C4AI-TOKEN \
                          --value $BEARER_TOKEN" \
                       "Updating bearer token in Key Vault"
        fi
        
        execute_cmd "az containerapp update \
                      --name $CONTAINER_APP \
                      --resource-group $RESOURCE_GROUP \
                      --image $IMAGE" \
                   "Updating container app image"
    fi
    
    # Show deployment results
    if [ "$DRY_RUN" = false ]; then
        print_status "📊 Getting deployment information..."
        
        APP_URL=$(az containerapp show \
                  --name $CONTAINER_APP \
                  --resource-group $RESOURCE_GROUP \
                  --query properties.configuration.ingress.fqdn -o tsv)
        
        print_success "🎉 Deployment completed successfully!"
        echo ""
        echo "📋 Deployment Summary:"
        echo "   App URL: https://$APP_URL"
        echo "   Health Check: https://$APP_URL/health"
        echo "   Playground: https://$APP_URL/playground"
        echo "   Bearer Token: $BEARER_TOKEN"
        echo "   Key Vault: $KEYVAULT_NAME"
        echo ""
        echo "🔧 Test your deployment:"
        echo "   curl -H \"Authorization: Bearer $BEARER_TOKEN\" https://$APP_URL/health"
        echo ""
        echo "📄 Example API call:"
        echo "   curl -X POST https://$APP_URL/crawl \\"
        echo "     -H \"Content-Type: application/json\" \\"
        echo "     -H \"Authorization: Bearer $BEARER_TOKEN\" \\"
        echo "     -d '{\"urls\": [\"https://example.com\"]}'"
        echo ""
        echo "💾 Save this Bearer token for your application:"
        echo "   BEARER_TOKEN=$BEARER_TOKEN"
    fi
}

# Main execution
main() {
    check_azure_cli
    deploy_crawl4ai_with_keyvault
}

# Run main function
main "$@"