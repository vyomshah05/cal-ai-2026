# Step-by-Step Guide: Using Lockstep MCP with Devin CLI

This guide walks you through setting up and using the Lockstep MCP server with Devin CLI.

## Prerequisites

- Devin CLI installed and configured
- Python 3.11+ with conda environment `cs178`
- Valid `.env` file with Redis, Supabase, and Anthropic credentials
- Lockstep project dependencies installed

## Step 1: Verify Your Environment

### 1.1 Check your conda environment
```bash
conda activate cs178
which python
# Should output: /opt/anaconda3/envs/cs178/bin/python
```

### 1.2 Set the Python path
The configuration uses the `LOCKSTEP_PYTHON` environment variable. Add this to your `.env` file:

```bash
# In your .env file
LOCKSTEP_PYTHON=python3  # or use full path for specific environment
```

For a specific conda environment:
```bash
# Find your Python path
which python
# Output example: /opt/anaconda3/envs/cs178/bin/python

# Add to your .env file
LOCKSTEP_PYTHON=/opt/anaconda3/envs/cs178/bin/python
```

### 1.3 Test the server manually
```bash
cd /Users/doubledogok/calaihack2026/cal-aihacks-2026/cal-ai-2026
python -m server
# Press Ctrl+C to stop after verifying it starts
```

## Step 2: Set Up Environment Variables for Devin

The MCP configuration needs environment variables to be available. You have two options:

### Option A: Export variables in your shell (recommended for development)
```bash
# Load your .env file variables into your shell
export $(grep -v '^#' .env | xargs)

# Verify they're set
echo $REDIS_HOST
echo $SUPABASE_URL
echo $ANTHROPIC_API_KEY
```

### Option B: Use a .env loader script (for persistent setup)
Create a script that loads environment variables before starting Devin:

```bash
#!/bin/bash
# File: devin-env-setup.sh
cd /Users/doubledogok/calaihack2026/cal-aihacks-2026/cal-ai-2026
export $(grep -v '^#' .env | xargs)
devin "$@"
```

Make it executable:
```bash
chmod +x devin-env-setup.sh
./devin-env-setup.sh mcp list
```

## Step 3: Configure Devin to Use the MCP Server

### 3.1 Copy the example configuration
```bash
cp .devin/config.json .devin/config.local.json
```

### 3.2 Verify the configuration
Check that `.devin/config.local.json` contains:
- `"cwd": ".."` - relative path to parent directory (project root)
- `"command": "${env:LOCKSTEP_PYTHON}"` - flexible Python path
- All environment variable references using `${env:VAR_NAME}` syntax

Example configuration:
```json
{
  "mcpServers": {
    "lockstep": {
      "command": "${env:LOCKSTEP_PYTHON}",
      "args": ["-m", "server"],
      "cwd": "..",
      "env": {
        "REDIS_HOST": "${env:REDIS_HOST}",
        "REDIS_PORT": "${env:REDIS_PORT}",
        "REDIS_USERNAME": "${env:REDIS_USERNAME}",
        "REDIS_PASSWORD": "${env:REDIS_PASSWORD}",
        "SUPABASE_URL": "${env:SUPABASE_URL}",
        "SUPABASE_SERVICE_KEY": "${env:SUPABASE_SERVICE_KEY}",
        "ANTHROPIC_API_KEY": "${env:ANTHROPIC_API_KEY}",
        "RERANK_MODEL": "${env:RERANK_MODEL}",
        "EMBED_MODEL": "${env:EMBED_MODEL}",
        "EMBED_DIM": "${env:EMBED_DIM}",
        "CACHE_CAPACITY": "${env:CACHE_CAPACITY}",
        "CACHE_THETA": "${env:CACHE_THETA}",
        "DOCS_TTL_SECONDS": "${env:DOCS_TTL_SECONDS}",
        "RECO_TTL_SECONDS": "${env:RECO_TTL_SECONDS}",
        "DOCS_TOP_K": "${env:DOCS_TOP_K}",
        "LIBS_TOP_K": "${env:LIBS_TOP_K}",
        "LOCKSTEP_HOST": "${env:LOCKSTEP_HOST}",
        "LOCKSTEP_PORT": "${env:LOCKSTEP_PORT}",
        "LOCKSTEP_PYTHON": "${env:LOCKSTEP_PYTHON}"
      }
    }
  }
}
```

## Step 4: Verify MCP Server Registration

### 4.1 List configured MCP servers
```bash
devin mcp list
```

Expected output should include:
```
lockstep
```

### 4.2 Get detailed server information
```bash
devin mcp get lockstep
```

This should show the server configuration details.

## Step 5: Test the MCP Connection

### 5.1 Start a Devin session
```bash
devin
```

### 5.2 Check available tools
Once in the Devin session, you should see tools prefixed with `mcp__lockstep__`:
- `mcp__lockstep__plan_task`
- `mcp__lockstep__resolve_version`
- `mcp__lockstep__recommend_library`
- `mcp__lockstep__get_versioned_docs`

### 5.3 Test a simple tool call
Ask Devin to test the connection:
```
Can you call the mcp__lockstep__plan_task tool with the prompt "make HTTP requests in Python"?
```

## Step 6: Using the Lockstep MCP Tools

### 6.1 Plan a coding task
The primary workflow starts with `plan_task`:

```
I need to build a job queue system with background tasks. Can you use mcp__lockstep__plan_task to break this down?
```

Devin will:
1. Call `plan_task` with your prompt
2. Get back a structured plan with libraries and versions
3. Use that information to write accurate code

### 6.2 Get library recommendations
For specific library choices:

```
I need an HTTP library for Python. Can you use mcp__lockstep__recommend_library to suggest options?
```

### 6.3 Resolve versions from lockfiles
If you have existing dependencies:

```
Can you use mcp__lockstep__resolve_version to check what versions are in my requirements.txt?
```

### 6.4 Get version-specific documentation
For accurate API usage:

```
I'm using SQLAlchemy 2.0. Can you use mcp__lockstep__get_versioned_docs to get the correct function signatures?
```

## Step 7: Monitor Cache Performance

### 7.1 Run the cache inspector
In a separate terminal:
```bash
# From project root
python scripts/cache_inspector.py
```

This shows:
- Current cache size and capacity
- Top-K most accessed libraries
- Individual cache entries with frequency ratings
- Bloom filter and CMS status

### 7.2 Simulate queries
Test cache behavior:
```bash
python scripts/cache_inspector.py --query "make HTTP requests"
```

### 7.3 Watch cache in real-time
```bash
python scripts/cache_inspector.py --watch 5
```

## Troubleshooting

### Server doesn't start
**Problem**: Devin can't connect to the MCP server

**Solutions**:
1. Verify `LOCKSTEP_PYTHON` is set in your `.env` file: `grep LOCKSTEP_PYTHON .env`
2. Test the Python path manually: `$LOCKSTEP_PYTHON -m server`
3. Check `.devin/config.local.json` has correct `cwd: ".."`
4. Ensure your Python path is valid: `which python3` or test your specific path

### Environment variables not loading
**Problem**: MCP server can't access credentials

**Solutions**:
1. Export variables: `export $(grep -v '^#' .env | xargs)`
2. Verify variables are set: `echo $REDIS_HOST`
3. Check .env file format (no spaces around `=`)
4. Use the devin-env-setup.sh script approach

### Connection errors
**Problem**: Can't connect to Redis or Supabase

**Solutions**:
1. Test Redis connection: `redis-cli -h $REDIS_HOST -p $REDIS_PORT -a $REDIS_PASSWORD ping`
2. Verify Supabase URL is accessible
3. Check network connectivity
4. Verify credentials in .env are correct

### Tools not appearing
**Problem**: MCP tools don't show up in Devin

**Solutions**:
1. Run `devin mcp list` to verify server is registered
2. Check Devin logs for MCP startup errors
3. Ensure `.devin/config.local.json` is in project root
4. Try restarting Devin

### Cache not working
**Problem**: Cache misses or incorrect results

**Solutions**:
1. Run cache inspector: `python scripts/cache_inspector.py`
2. Check Redis connection and credentials
3. Verify cache structures exist: `redis-cli -h $REDIS_HOST -p $REDIS_PORT -a $REDIS_PASSWORD`
4. Check cache tuning parameters in .env

## Advanced Usage

### Development mode with hardcoded responses
For testing without real backend calls:
```bash
export LOCKSTEP_HARDCODED=1
devin
```

### Custom cache tuning
Edit your `.env` file to adjust cache behavior:
```
CACHE_CAPACITY=2000        # Increase cache size
CACHE_THETA=0.95          # Higher similarity threshold
DOCS_TTL_SECONDS=604800   # Longer TTL (1 week)
```

### Monitoring multiple projects
The cache inspector can help you understand usage patterns across different Devin sessions and projects.

## Next Steps

1. **Experiment with different prompts**: Try various coding tasks to see how Lockstep decomposes them
2. **Monitor cache performance**: Use the cache inspector to understand hit rates and popular libraries
3. **Contribute improvements**: The Lockstep server can be extended with additional tools and features

## Getting Help

- Check the main [README.md](../README.md) for project details
- Review [CONTRACT.md](../CONTRACT.md) for data schema information
- See [DEVIN_SETUP.md](./DEVIN_SETUP.md) for configuration reference
- Run tests: `pytest tests/` to verify server functionality