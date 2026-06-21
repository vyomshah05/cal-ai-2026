import { Card } from '../components/ui/Card';
import { CodeBlock } from '../components/ui/CodeBlock';
import {
  devinConfigSnippet,
  devinEnvVars,
  devinSetupSteps,
  devinTools,
  devinTroubleshooting,
} from '../content/devinGuideContent';

export function DevinGuide() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Use Lockstep with Devin</h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-600 dark:text-slate-400">
          Lockstep ships a ready-to-use Devin CLI config at{' '}
          <code className="rounded bg-black/5 dark:bg-white/10 px-1.5 py-0.5">.devin/config.json</code>.
          Step through this once and Devin gets the same four tools Claude Code uses.
        </p>
      </div>

      <div className="space-y-4">
        {devinSetupSteps.map((step, i) => (
          <Card key={step.title} className="p-6">
            <div className="mb-2 flex items-center gap-3">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-accent to-violet-700 dark:from-accent-dark dark:to-violet-400 text-xs font-bold text-white">
                {i + 1}
              </span>
              <h2 className="text-sm font-semibold">{step.title}</h2>
            </div>
            <CodeBlock>{step.body}</CodeBlock>
          </Card>
        ))}
      </div>

      <Card className="p-6 space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          .devin/config.json
        </h2>
        <CodeBlock>{devinConfigSnippet}</CodeBlock>
      </Card>

      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Available tools
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {devinTools.map((t) => (
            <Card key={t.name} className="p-4">
              <div className="mb-1 font-mono text-sm font-semibold text-accent dark:text-accent-dark">
                {t.name}
              </div>
              <p className="text-sm text-slate-600 dark:text-slate-400">{t.desc}</p>
            </Card>
          ))}
        </div>
      </div>

      <Card className="p-6">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Environment variables
        </h2>
        <div className="divide-y divide-black/5 dark:divide-white/10">
          {devinEnvVars.map((v) => (
            <div key={v.name} className="flex flex-col gap-1 py-2 sm:flex-row sm:items-center sm:justify-between">
              <code className="text-xs text-slate-700 dark:text-slate-300">{v.name}</code>
              <span className="text-xs text-slate-500 dark:text-slate-400">{v.note}</span>
            </div>
          ))}
        </div>
      </Card>

      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Troubleshooting
        </h2>
        <div className="space-y-2">
          {devinTroubleshooting.map((t) => (
            <details key={t.issue} className="group rounded-xl border border-black/5 dark:border-white/10 bg-surface-light dark:bg-surface-dark p-4">
              <summary className="cursor-pointer text-sm font-medium text-slate-900 dark:text-slate-100">
                {t.issue}
              </summary>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{t.fix}</p>
            </details>
          ))}
        </div>
      </div>
    </div>
  );
}
