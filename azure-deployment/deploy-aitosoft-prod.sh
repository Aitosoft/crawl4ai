#!/bin/bash

# ==========================================
# Crawl4AI Deployment to Aitosoft Production
# ==========================================
# Deploys to existing aitosoft-prod infrastructure in West Europe
# Uses existing: aitosoftacr, aitosoft-aca, workspace-aitosoftprodnCsc

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration - Using existing aitosoft-prod resources
RESOURCE_GROUP="aitosoft-prod"
CONTAINER_APP="crawl4ai-service"
ENVIRONMENT="aitosoft-aca"  # Existing Container Apps environment
LOCATION="westeurope"
ACR_NAME="aitosoftacr"
IMAGE_NAME="crawl4ai-service"
IMAGE_TAG="0.8.0"
FULL_IMAGE="${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${IMAGE_TAG}"

# Generate secure token
API_TOKEN="crawl4ai-$(openssl rand -hex 24)"
JWT_SECRET="jwt-secret-$(openssl rand -hex 32)"

# Parse command line arguments
DRY_RUN=false
UPDATE_ONLY=false
SKIP_BUILD=false

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
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--dry-run] [--update-only] [--skip-build]"
            echo "  --dry-run     Show what would be done without executing"
            echo "  --update-only Update existing container app only"
            echo "  --skip-build  Skip Docker build (use existing image)"
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

# Check if Docker is available for building
check_docker() {
    if [ "$SKIP_BUILD" = true ]; then
        print_warning "Skipping Docker build check (--skip-build flag)"
        return 0
    fi

    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Use --skip-build if image is already pushed."
        exit 1
    fi

    print_success "Docker is available"
}

# Build and push Docker image
build_and_push_image() {
    if [ "$SKIP_BUILD" = true ]; then
        print_warning "Skipping Docker build (--skip-build flag)"
        return 0
    fi

    print_status "🐳 Building Docker image..."

    # Login to ACR
    execute_cmd "az acr login --name ${ACR_NAME}" \
               "Logging in to Azure Container Registry"

    # Build image
    execute_cmd "docker build -t ${FULL_IMAGE} ." \
               "Building Docker image"

    # Push to ACR
    execute_cmd "docker push ${FULL_IMAGE}" \
               "Pushing image to ACR"
}

# Deploy container app
deploy_container_app() {
    print_status "🚀 Deploying crawl4ai to aitosoft-prod"
    print_status "📋 Configuration:"
    echo "   Resource Group: $RESOURCE_GROUP"
    echo "   Container App: $CONTAINER_APP"
    echo "   Environment: $ENVIRONMENT"
    echo "   Location: $LOCATION"
    echo "   Image: $FULL_IMAGE"
    echo ""

    if [ "$UPDATE_ONLY" = true ]; then
        # Update existing app
        local update_cmd="az containerapp update \
            --name $CONTAINER_APP \
            --resource-group $RESOURCE_GROUP \
            --image $FULL_IMAGE \
            --set-env-vars \
                CRAWL4AI_API_TOKEN=$API_TOKEN \
                SECRET_KEY=$JWT_SECRET \
                ENVIRONMENT=production \
                LOG_LEVEL=INFO \
                MAX_CONCURRENT_REQUESTS=10"

        execute_cmd "$update_cmd" "Updating container app"
    else
        # Create new app
        local create_cmd="az containerapp create \
            --name $CONTAINER_APP \
            --resource-group $RESOURCE_GROUP \
            --environment $ENVIRONMENT \
            --image $FULL_IMAGE \
            --target-port 11235 \
            --ingress external \
            --min-replicas 1 \
            --max-replicas 3 \
            --cpu 1.0 \
            --memory 2.0Gi \
            --registry-server ${ACR_NAME}.azurecr.io \
            --env-vars \
                CRAWL4AI_API_TOKEN=$API_TOKEN \
                SECRET_KEY=$JWT_SECRET \
                ENVIRONMENT=production \
                LOG_LEVEL=INFO \
                MAX_CONCURRENT_REQUESTS=10"

        execute_cmd "$create_cmd" "Creating container app"
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
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "📋 DEPLOYMENT SUMMARY"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "🌍 Location: West Europe (co-located with MAS)"
        echo "🔗 App URL: https://$APP_URL"
        echo "💚 Health Check: https://$APP_URL/health"
        echo "📖 API Docs: https://$APP_URL/docs"
        echo "🎮 Playground: https://$APP_URL/playground"
        echo ""
        echo "🔑 CREDENTIALS (save these securely!):"
        echo "   API Token: $API_TOKEN"
        echo "   JWT Secret: $JWT_SECRET"
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "🧪 TEST YOUR DEPLOYMENT"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "# 1. Health check (no auth required):"
        echo "curl https://$APP_URL/health"
        echo ""
        echo "# 2. Test without auth (should fail with 401):"
        echo "curl -X POST https://$APP_URL/crawl \\"
        echo "  -H \"Content-Type: application/json\" \\"
        echo "  -d '{\"urls\": [\"https://example.com\"]}'"
        echo ""
        echo "# 3. Test with auth (should succeed):"
        echo "curl -X POST https://$APP_URL/crawl \\"
        echo "  -H \"Authorization: Bearer $API_TOKEN\" \\"
        echo "  -H \"Content-Type: application/json\" \\"
        echo "  -d '{\"urls\": [\"https://example.com\"]}'"
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "📝 FOR YOUR MAS REPO (.env or config):"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "CRAWL4AI_API_URL=https://$APP_URL"
        echo "CRAWL4AI_API_TOKEN=$API_TOKEN"
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    fi
}

# Main execution
main() {
    print_status "🚀 Crawl4AI Deployment to Aitosoft Production (West Europe)"
    echo ""

    check_azure_cli
    check_docker

    if [ "$UPDATE_ONLY" = false ]; then
        build_and_push_image
    fi

    deploy_container_app

    print_success "✅ All done!"
}

# Run main function
main "$@"
