export const REPO_URL = 'https://github.com/vyomshah05/cal-ai-2026';

export const devinConfigSnippet = `{
  "mcpServers": {
    "lockstep": {
      "command": "\${env:LOCKSTEP_PYTHON}",
      "args": ["-m", "server"],
      "cwd": "..",
      "env": {
        "REDIS_HOST": "\${env:REDIS_HOST}",
        "REDIS_PORT": "\${env:REDIS_PORT}",
        "REDIS_USERNAME": "\${env:REDIS_USERNAME}",
        "REDIS_PASSWORD": "\${env:REDIS_PASSWORD}",
        "SUPABASE_URL": "\${env:SUPABASE_URL}",
        "SUPABASE_SERVICE_KEY": "\${env:SUPABASE_SERVICE_KEY}",
        "ANTHROPIC_API_KEY": "\${env:ANTHROPIC_API_KEY}",
        "RERANK_MODEL": "\${env:RERANK_MODEL}",
        "EMBED_MODEL": "\${env:EMBED_MODEL}",
        "EMBED_DIM": "\${env:EMBED_DIM}",
        "LOCKSTEP_HOST": "\${env:LOCKSTEP_HOST}",
        "LOCKSTEP_PORT": "\${env:LOCKSTEP_PORT}",
        "LOCKSTEP_PYTHON": "\${env:LOCKSTEP_PYTHON}"
      }
    }
  }
}`;

export const devinSetupSteps = [
  {
    title: 'Clone the repo and install',
    body: `git clone ${REPO_URL}.git\ncd cal-ai-2026\npython -m venv .venv && source .venv/bin/activate\npip install -e .\ncp .env.example .env   # fill in Supabase, Redis, Anthropic credentials`,
  },
  {
    title: 'Set your Python interpreter',
    body: `# In your .env file\nLOCKSTEP_PYTHON=python3   # or a full path, e.g. /opt/anaconda3/envs/myenv/bin/python`,
  },
  {
    title: 'Copy the Devin MCP config',
    body: `cp .devin/config.json .devin/config.local.json\nexport $(grep -v '^#' .env | xargs)`,
  },
  {
    title: 'Verify registration',
    body: `devin mcp list\ndevin mcp get lockstep`,
  },
  {
    title: 'Start a Devin session and test a tool call',
    body: `Can you call the mcp__lockstep__plan_task tool with the prompt "make HTTP requests in Python"?`,
  },
];

export const devinTools = [
  { name: 'mcp__lockstep__plan_task', desc: 'Decompose a coding prompt into subtasks with library + docs recommendations.' },
  { name: 'mcp__lockstep__resolve_version', desc: 'Parse lockfiles and extract pinned dependency versions.' },
  { name: 'mcp__lockstep__recommend_library', desc: 'Recommend libraries for a specific task, reranked by Claude.' },
  { name: 'mcp__lockstep__get_versioned_docs', desc: 'Fetch version-pinned documentation chunks for a library.' },
];

export const devinEnvVars = [
  { name: 'LOCKSTEP_PYTHON', note: 'Python interpreter path (required)' },
  { name: 'REDIS_HOST / REDIS_PORT / REDIS_USERNAME / REDIS_PASSWORD', note: 'Redis Stack connection (required)' },
  { name: 'SUPABASE_URL / SUPABASE_SERVICE_KEY', note: 'Supabase connection (required)' },
  { name: 'ANTHROPIC_API_KEY', note: 'Claude API for task decomposition (required)' },
  { name: 'RERANK_MODEL', note: 'Default: claude-sonnet-4-6' },
  { name: 'EMBED_MODEL / EMBED_DIM', note: 'Default: all-MiniLM-L6-v2 / 384' },
  { name: 'LOCKSTEP_HOST / LOCKSTEP_PORT', note: 'Default: 127.0.0.1 / 8000' },
];

export const devinTroubleshooting = [
  {
    issue: "Server doesn't start",
    fix: 'Verify LOCKSTEP_PYTHON is set (grep LOCKSTEP_PYTHON .env), test it manually with `$LOCKSTEP_PYTHON -m server`, and confirm .devin/config.local.json has "cwd": "..".',
  },
  {
    issue: 'Environment variables not loading',
    fix: "Run `export $(grep -v '^#' .env | xargs)` before starting Devin, and confirm with `echo $REDIS_HOST`.",
  },
  {
    issue: "Can't connect to Redis or Supabase",
    fix: 'Test Redis with `redis-cli -h $REDIS_HOST -p $REDIS_PORT -a $REDIS_PASSWORD ping`, and double-check SUPABASE_URL/SUPABASE_SERVICE_KEY.',
  },
  {
    issue: "Tools don't show up in Devin",
    fix: 'Run `devin mcp list` to confirm registration, check Devin logs for MCP startup errors, then restart Devin.',
  },
];
