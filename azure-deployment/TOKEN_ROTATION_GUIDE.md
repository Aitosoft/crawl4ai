# Token Rotation Guide

## Overview

This guide describes how to rotate the Crawl4AI API authentication token securely. The token is used by AI agents in the aitosoft-platform to authenticate API requests to the Crawl4AI service.

## When to Rotate

- **Immediately**: If the token has been exposed in code, logs, or documentation
- **Quarterly**: As a security best practice (every 90 days)
- **On Demand**: If suspicious activity is detected or team members leave

## Token Storage Locations

The token must be updated in three locations:

1. **Azure Key Vault** (`crawl4ai-v2-keyvault`) - Production secret
2. **GitHub Repository Secrets** (`C4AI_TOKEN`) - For CI/CD workflows
3. **Local Development** (`.env.local`) - For local testing

## Step-by-Step Rotation Procedure

### 1. Generate New Secure Token

```bash
# Generate a 32-byte hexadecimal token (64 characters)
openssl rand -hex 32
```

**Example output:**
```
9d4ff233da7e24925d1cd6cf7bea5b9265f208c08b95d0a8fdea2b1ba1480892
```

**Important**: Save this token securely - you'll need it for the next steps.

### 2. Update Azure Key Vault

```bash
# Login to Azure (if not already logged in)
az login

# Set the new token in Key Vault
az keyvault secret set \
  --vault-name crawl4ai-v2-keyvault \
  --name C4AI-TOKEN \
  --value "YOUR_NEW_TOKEN_HERE"

# Verify the secret was updated
az keyvault secret show \
  --vault-name crawl4ai-v2-keyvault \
  --name C4AI-TOKEN \
  --query "attributes.updated" \
  --output tsv
```

**Note**: The Container App automatically picks up the new secret from Key Vault via managed identity reference. No restart required.

### 3. Update GitHub Repository Secret

```bash
# Using GitHub CLI (recommended)
echo "YOUR_NEW_TOKEN_HERE" | gh secret set C4AI_TOKEN --repo Aitosoft/crawl4ai

# Verify the secret was updated
gh secret list --repo Aitosoft/crawl4ai | grep C4AI_TOKEN
```

**Alternative (via GitHub web UI)**:
1. Go to https://github.com/Aitosoft/crawl4ai/settings/secrets/actions
2. Click on `C4AI_TOKEN`
3. Click "Update secret"
4. Paste the new token value
5. Click "Update secret"

### 4. Update Local Development Environment

```bash
# Update your local .env.local file
echo "CRAWL4AI_API_TOKEN=YOUR_NEW_TOKEN_HERE" > .env.local
echo "APP_VERSION=dev" >> .env.local

# Verify the file is git-ignored
git status .env.local
# Should show nothing (file is ignored)
```

### 5. Notify Dependent Systems

After rotation, update the token in systems that call the Crawl4AI API:

**aitosoft-platform repository:**
1. Update the environment variable in that project's deployment
2. Typically stored in Azure Container Apps environment variables
3. Coordinate with the agent responsible for that repository

### 6. Verify Token Works

```bash
# Test health endpoint (no auth required)
curl https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/health

# Test with new token
curl -X POST https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/crawl \
  -H "Authorization: Bearer YOUR_NEW_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"urls":["https://example.com"]}'
```

**Expected response:**
- Health check: `{"status":"ok","timestamp":"...","version":"..."}`
- Crawl request: `{"success":true,"results":[...]}`

### 7. Test Old Token is Revoked

```bash
# Test with the OLD token (should fail)
curl -X POST https://crawl4ai-v2-app.kindforest-02188d13.northeurope.azurecontainerapps.io/crawl \
  -H "Authorization: Bearer OLD_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"urls":["https://example.com"]}'
```

**Expected response:**
- Status code: `401 Unauthorized`
- Body: `{"detail":"Invalid authentication credentials"}`

## Emergency Rotation (Exposed Token)

If a token has been exposed in git history or public documentation:

### 1. Immediate Rotation

Follow steps 1-4 above **immediately**.

### 2. Git History Cleanup (if exposed in commits)

**Option A: Remove from recent commits (if not pushed)**
```bash
# If the exposure is in the most recent commit
git reset --soft HEAD~1
# Edit files to remove token
git add .
git commit -m "Security: Rotate exposed token"
```

**Option B: Rewrite git history (use with caution)**
```bash
# Use BFG Repo-Cleaner to remove tokens from all history
# Only do this if absolutely necessary and coordinate with team
brew install bfg  # or download from https://rtyley.github.io/bfg-repo-cleaner/

# Create a file with tokens to remove
echo "OLD_TOKEN_VALUE" > tokens.txt

# Clean the repository
bfg --replace-text tokens.txt --no-blob-protection .

# Force push (WARNING: This rewrites history)
git reflog expire --expire=now --all && git gc --prune=now --aggressive
git push --force
```

**Option C: Contact GitHub Support (if public repository)**
- Report the exposed secret to GitHub
- They can scan and invalidate the exposed token

### 3. Review Access Logs

Check Azure Container Apps logs for suspicious activity:
```bash
az containerapp logs show \
  --name crawl4ai-v2-app \
  --resource-group crawl4ai-v2-rg \
  --tail 1000 \
  --follow
```

Look for:
- Unusual request patterns
- Requests from unexpected IPs
- High volume of requests
- Failed authentication attempts

## Automated Rotation (Future Enhancement)

Consider implementing:
1. Automated quarterly rotation via GitHub Actions
2. Token expiration tracking
3. Alerting when tokens are near expiration
4. Integration with Azure Key Vault rotation policies

## Troubleshooting

### Issue: Container App still using old token

**Cause**: Managed identity may have cached the secret value

**Solution**:
```bash
# Restart the Container App to force secret refresh
az containerapp revision restart \
  --name crawl4ai-v2-app \
  --resource-group crawl4ai-v2-rg
```

### Issue: GitHub Actions workflow failing with 401

**Cause**: GitHub secret not updated or not accessible to workflow

**Solution**:
1. Verify secret exists: `gh secret list --repo Aitosoft/crawl4ai`
2. Check workflow has access to secrets (check repository settings)
3. Re-add the secret using GitHub CLI or web UI

### Issue: Local tests failing with authentication error

**Cause**: `.env.local` not loaded or has incorrect token

**Solution**:
```bash
# Verify .env.local exists and has correct format
cat .env.local

# Should show:
# CRAWL4AI_API_TOKEN=<your-token>
# APP_VERSION=dev

# Ensure the application loads .env.local
# Check your application startup code or use a library like python-dotenv
```

## Security Best Practices

1. **Never commit tokens to git** - Always use `.env.local` (git-ignored)
2. **Use environment variables** - Reference tokens via `${CRAWL4AI_API_TOKEN}` in docs
3. **Limit token scope** - This token only grants access to Crawl4AI API
4. **Monitor usage** - Review Azure logs regularly for suspicious activity
5. **Rotate regularly** - Set a calendar reminder for quarterly rotation
6. **Document rotation** - Update DEVELOPMENT_NOTES.md when rotating

## Checklist

After rotating the token, verify:

- [ ] New token generated with `openssl rand -hex 32`
- [ ] Azure Key Vault updated and verified
- [ ] GitHub repository secret updated and verified
- [ ] Local `.env.local` updated
- [ ] Dependent systems (aitosoft-platform) notified/updated
- [ ] Production test passed with new token
- [ ] Old token confirmed revoked (401 response)
- [ ] Token rotation documented in DEVELOPMENT_NOTES.md
- [ ] Team notified of rotation

## Contact

If you encounter issues during rotation:
- Check Azure Container Apps logs
- Verify Azure Key Vault access permissions
- Review GitHub Actions workflow runs
- Consult DEVELOPMENT_NOTES.md for recent changes

---

**Last Updated**: 2026-01-19
**Next Scheduled Rotation**: 2026-04-19 (90 days from now)
