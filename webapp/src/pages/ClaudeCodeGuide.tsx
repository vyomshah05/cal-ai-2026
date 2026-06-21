import { Card } from '../components/ui/Card';
import { CodeBlock } from '../components/ui/CodeBlock';
import { REPO_URL } from '../content/devinGuideContent';

const TOOLS = [
  {
    name: 'plan_task',
    desc: 'Call this first with the raw prompt. Decomposes it into 2-6 subtasks and returns the best library + key function docs for each, so code gets written against accurate, non-deprecated APIs.',
  },
  {
    name: 'resolve_version',
    desc: 'Parses your lockfiles (package-lock.json, poetry.lock, Cargo.lock, go.mod, requirements.txt, yarn.lock) and returns the pinned dependency versions actually in use.',
  },
  {
    name: 'recommend_library',
    desc: 'Recommends libraries for a coding task, reranked by Claude, with tradeoffs and a sample snippet.',
  },
  {
    name: 'get_versioned_docs',
    desc: 'Returns documentation chunks for a library pinned to a specific version, so generated code matches the API that is actually installed.',
  },
];

export function ClaudeCodeGuide() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Use Lockstep with Claude Code</h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-600 dark:text-slate-400">
          Lockstep runs as a local MCP server over stdio. Claude Code talks to it directly —
          no extra ports, no extra services beyond Supabase and Redis.
        </p>
      </div>

      <Card className="p-6 space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          1. Clone &amp; install
        </h2>
        <CodeBlock>{`git clone ${REPO_URL}.git\ncd cal-ai-2026\npython -m venv .venv && source .venv/bin/activate\npip install -e .\ncp .env.example .env   # fill in SUPABASE_URL, SUPABASE_SERVICE_KEY, REDIS_*, ANTHROPIC_API_KEY`}</CodeBlock>
      </Card>

      <Card className="p-6 space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          2. Register the MCP server
        </h2>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          From the repo root, register Lockstep with Claude Code's CLI:
        </p>
        <CodeBlock>{`claude mcp add lockstep -- python3 -m server`}</CodeBlock>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Or point a project <code>.mcp.json</code> at it directly:
        </p>
        <CodeBlock>{`{
  "mcpServers": {
    "lockstep": {
      "command": "python3",
      "args": ["-m", "server"],
      "cwd": "/absolute/path/to/cal-ai-2026"
    }
  }
}`}</CodeBlock>
      </Card>

      <Card className="p-6 space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          3. Verify &amp; use
        </h2>
        <CodeBlock>{`claude mcp list\n# should include "lockstep"`}</CodeBlock>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Then just ask Claude Code to use it — e.g. <em>"Use plan_task to break down: build a job
          queue with retries in Python."</em> The primary workflow always starts with{' '}
          <code className="rounded bg-black/5 dark:bg-white/10 px-1.5 py-0.5">plan_task</code>.
        </p>
      </Card>

      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Available tools
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {TOOLS.map((t) => (
            <Card key={t.name} className="p-4">
              <div className="mb-1 font-mono text-sm font-semibold text-accent dark:text-accent-dark">
                {t.name}
              </div>
              <p className="text-sm text-slate-600 dark:text-slate-400">{t.desc}</p>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
