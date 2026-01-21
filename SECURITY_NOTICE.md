# Security Notice

## Sensitive Files Removed from Git Tracking

The following files contain sensitive data and have been removed from git tracking:

- `app/config/providers.json` - **Contains API keys**
- `app/config/chat_sessions.json` - User conversation history
- `app/config/model_config.json` - User preferences

These files **remain on your local disk** but are no longer tracked by git.

## ⚠️ IMPORTANT: Git History Cleanup

If these files were previously committed to your repository, they **still exist in git history** and may be accessible to others with access to your repository.

### To Remove Sensitive Data from Git History

If you've already pushed commits containing API keys to a remote repository:

1. **Revoke exposed API keys immediately:**
   - OpenAI: https://platform.openai.com/api-keys
   - Google Gemini: https://aistudio.google.com/app/apikey

2. **Remove files from git history:**

   ```bash
   # Install git-filter-repo if not already installed
   pip install git-filter-repo
   
   # Remove the files from all commits
   git filter-repo --invert-paths \
     --path app/config/providers.json \
     --path app/config/chat_sessions.json \
     --path app/config/model_config.json
   ```

3. **Force push to remote (if repository is shared):**

   ```bash
   git push origin --force --all
   git push origin --force --tags
   ```

   **⚠️ WARNING**: This rewrites history. Coordinate with your team if others have cloned the repository.

### Alternative: Use BFG Repo-Cleaner

```bash
# Download BFG from https://rtyley.github.io/bfg-repo-cleaner/

# Remove files
java -jar bfg.jar --delete-files providers.json
java -jar bfg.jar --delete-files chat_sessions.json
java -jar bfg.jar --delete-files model_config.json

# Clean up
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# Force push
git push origin --force --all
```

## Setup for New Installation

1. Copy example files to create your configuration:

   ```bash
   # Windows PowerShell
   Copy-Item app\config\providers.example.json app\config\providers.json
   Copy-Item app\config\model_config.example.json app\config\model_config.json
   
   # macOS/Linux
   cp app/config/providers.example.json app/config/providers.json
   cp app/config/model_config.example.json app/config/model_config.json
   ```

2. Edit `app/config/providers.json` and add your API keys

3. The application will create `chat_sessions.json` automatically on first run

## Best Practices

1. **Never commit API keys**: Always use `.gitignore` and example files
2. **Use environment variables** for production deployments
3. **Rotate API keys regularly**
4. **Set file permissions**: 
   ```bash
   # Unix/Linux/macOS
   chmod 600 app/config/providers.json
   ```
5. **Use separate API keys** for development and production

## Current Status

✅ Sensitive files are now in `.gitignore`  
✅ Files removed from git tracking  
✅ Example files provided  
⚠️  Check if files exist in git history (see above)

## Questions?

If you're unsure whether your API keys were exposed, assume they were and rotate them immediately.
