#!/bin/bash

# ==========================================
# Crawl4AI Azure Container Apps Deployment Script
# ==========================================
# This script provides a clean, maintainable way to deploy Crawl4AI to Azure
# Usage: ./deploy.sh [--dry-run] [--update-only]

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
LOCATION="northeurope"
IMAGE="unclecode/crawl4ai:latest"
LOG_WORKSPACE="crawl4ai-v2-logs"

# Authentication token (generate a secure one)
API_TOKEN="crawl4ai-$(openssl rand -hex 16)"

# JWT Secret for token signing
JWT_SECRET="jwt-secret-$(openssl rand -hex 32)"

# Parse command line arguments
DRY_RUN=false
UPDATE_ONLY=false

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
        -h|--help)
            echo "Usage: $0 [--dry-run] [--update-only]"
            echo "  --dry-run     Show what would be done without executing"
            echo "  --update-only Update existing container app only"
            exit 0
            ;;
        *)
            echo "Unknown option $1"
            exit 1
            ;;
    esac
done

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

# Main deployment function
deploy_crawl4ai() {
    print_status "🚀 Starting Crawl4AI deployment to Azure Container Apps"
    print_status "📋 Configuration:"
    echo "   Resource Group: $RESOURCE_GROUP"
    echo "   Container App: $CONTAINER_APP"
    echo "   Environment: $ENVIRONMENT"
    echo "   Location: $LOCATION"
    echo "   Image: $IMAGE"
    echo "   API Token: $API_TOKEN"
    echo ""
    
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
        
        # Get workspace ID and key
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
    fi
    
    # Create or update the container app
    local app_cmd="az containerapp create \
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
        --env-vars \
            CRAWL4AI_API_TOKEN=$API_TOKEN \
            SECRET_KEY=$JWT_SECRET \
            ENVIRONMENT=production \
            LOG_LEVEL=INFO \
            MAX_CONCURRENT_REQUESTS=10 \
            SECURITY_ENABLED=true \
            JWT_ENABLED=true"
    
    if [ "$UPDATE_ONLY" = true ]; then
        app_cmd=$(echo "$app_cmd" | sed 's/create/update/')
    fi
    
    execute_cmd "$app_cmd" "$([ "$UPDATE_ONLY" = true ] && echo "Updating" || echo "Creating") container app"
    
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
        echo "   API Token: $API_TOKEN"
        echo "   JWT Secret: $JWT_SECRET"
        echo ""
        echo "🔧 Test your deployment:"
        echo "   # Get a JWT token first:"
        echo "   curl -X POST https://$APP_URL/token -H \"Content-Type: application/json\" -d '{\"email\":\"test@gmail.com\"}'"
        echo ""
        echo "   # Then use the token for requests:"
        echo "   curl -H \"Authorization: Bearer <JWT_TOKEN>\" https://$APP_URL/health"
        echo ""
        echo "💾 Save these credentials securely:"
        echo "   API_TOKEN=$API_TOKEN"
        echo "   JWT_SECRET=$JWT_SECRET"
    fi
}

# Main execution
main() {
    check_azure_cli
    deploy_crawl4ai
}

# Run main function
main "$@"