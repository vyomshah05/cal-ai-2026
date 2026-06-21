import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Card } from '../components/ui/Card';
import { useDarkMode } from '../hooks/useDarkMode';
import {
  firstPromptErrorRate,
  planningTimeReductionPct,
  planningTimeShare,
  syntaxErrorRate,
  timePerPrompt,
} from '../content/homeStats';

const COLORS = {
  withMcp: { light: '#14B8A6', dark: '#2DD4BF' }, // teal, "good"
  withoutMcp: { light: '#EF4444', dark: '#F87171' }, // red, "worse"
};

function StatCard({
  value,
  label,
  accent,
}: {
  value: string;
  label: string;
  accent: 'teal' | 'claude' | 'accent';
}) {
  const accentClass = {
    teal: 'text-teal dark:text-teal-dark',
    claude: 'text-claude dark:text-claude-dark',
    accent: 'text-accent dark:text-accent-dark',
  }[accent];
  return (
    <Card className="p-6 text-center">
      <div className={`text-4xl font-extrabold tracking-tight ${accentClass}`}>{value}</div>
      <div className="mt-2 text-sm text-slate-600 dark:text-slate-400">{label}</div>
    </Card>
  );
}

function ChartTooltip({
  active,
  payload,
  label,
  isDark,
  unit,
}: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string | number;
  isDark: boolean;
  unit: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className={`rounded-lg border px-3 py-2 text-xs shadow-lg ${
        isDark
          ? 'border-white/10 bg-surface-dark text-slate-100'
          : 'border-black/5 bg-surface-light text-slate-900'
      }`}
    >
      <div className="mb-1 font-semibold">Prompt {label}</div>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
          <span>
            {p.name}: <strong>{p.value}{unit}</strong>
          </span>
        </div>
      ))}
    </div>
  );
}

export function Home() {
  const isDark = useDarkMode();
  const tickColor = isDark ? '#9A98A0' : '#6B6660';
  const gridColor = isDark ? '#FFFFFF14' : '#00000012';
  const mcp = isDark ? COLORS.withMcp.dark : COLORS.withMcp.light;
  const noMcp = isDark ? COLORS.withoutMcp.dark : COLORS.withoutMcp.light;

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-3xl font-extrabold tracking-tight">
          Stop shipping{' '}
          <span className="bg-gradient-to-r from-accent to-teal dark:from-accent-dark dark:to-teal-dark bg-clip-text text-transparent">
            hallucinated APIs
          </span>
        </h1>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-slate-600 dark:text-slate-400">
          Lockstep is an MCP server that hands coding agents like Claude Code and Devin
          accurate, version-pinned library documentation instead of letting them guess from
          stale training data. It decomposes a coding prompt into subtasks, resolves the right
          library and version for each one, and serves real function signatures from a
          Supabase-backed corpus through a Redis semantic cache, so generated code compiles
          and runs against APIs that actually exist.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard value={`~${planningTimeReductionPct}%`} label="less time spent planning which library and API to use, with Lockstep" accent="teal" />
        <StatCard value={`${firstPromptErrorRate.withMcp}%`} label="syntax-error rate after prompt 1, with Lockstep" accent="teal" />
        <StatCard value={`${firstPromptErrorRate.withoutMcp}%`} label="syntax-error rate after prompt 1, without Lockstep" accent="claude" />
      </div>

      <Card className="p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Time spent planning
        </h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          A regular LLM has to reason its way to the right library and version from training
          data alone. Lockstep resolves that directly through RAG against the library corpus
          plus a Redis semantic cache, so most of that search is skipped entirely.
        </p>
        <div className="mt-4 h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={planningTimeShare} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
              <XAxis dataKey="label" tick={{ fill: tickColor, fontSize: 12 }} axisLine={{ stroke: gridColor }} tickLine={false} />
              <YAxis tick={{ fill: tickColor, fontSize: 12 }} axisLine={false} tickLine={false} width={36} unit="%" />
              <Tooltip
                cursor={{ fill: isDark ? '#FFFFFF0A' : '#0000000A' }}
                content={({ active, payload }) =>
                  active && payload?.length ? (
                    <div
                      className={`rounded-lg border px-3 py-2 text-xs shadow-lg ${
                        isDark
                          ? 'border-white/10 bg-surface-dark text-slate-100'
                          : 'border-black/5 bg-surface-light text-slate-900'
                      }`}
                    >
                      {payload[0].payload.label}: <strong>{payload[0].value}% of session time planning</strong>
                    </div>
                  ) : null
                }
              />
              <Bar
                dataKey="pct"
                radius={[8, 8, 0, 0]}
                isAnimationActive
                animationEasing="ease-out"
                animationDuration={900}
              >
                {planningTimeShare.map((entry) => (
                  <Cell key={entry.label} fill={entry.label === 'With Lockstep' ? mcp : noMcp} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card className="p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Time per prompt across a session
        </h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          Lockstep's decomposition step adds a little overhead on prompt 1, but pays for itself
          immediately after, since every later prompt resolves docs from cache instead of
          re-discovering them.
        </p>
        <div className="mt-4 h-80">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={timePerPrompt} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
              <XAxis
                dataKey="prompt"
                tick={{ fill: tickColor, fontSize: 12 }}
                axisLine={{ stroke: gridColor }}
                tickLine={false}
                label={{ value: 'Prompt #', position: 'insideBottom', offset: -4, fill: tickColor, fontSize: 12 }}
              />
              <YAxis
                tick={{ fill: tickColor, fontSize: 12 }}
                axisLine={false}
                tickLine={false}
                width={36}
                label={{ value: 'Seconds', angle: -90, position: 'insideLeft', fill: tickColor, fontSize: 12 }}
              />
              <Tooltip content={<ChartTooltip isDark={isDark} unit="s" />} />
              <Legend wrapperStyle={{ fontSize: 12, color: tickColor, paddingTop: 32 }} height={52} verticalAlign="bottom" />
              <Line
                type="monotone"
                dataKey="withMcp"
                name="With Lockstep"
                stroke={mcp}
                strokeWidth={2.5}
                dot={{ r: 3, fill: mcp }}
                activeDot={{ r: 5 }}
                isAnimationActive
                animationEasing="ease-out"
                animationDuration={1200}
              />
              <Line
                type="monotone"
                dataKey="withoutMcp"
                name="Without Lockstep"
                stroke={noMcp}
                strokeWidth={2.5}
                dot={{ r: 3, fill: noMcp }}
                activeDot={{ r: 5 }}
                isAnimationActive
                animationEasing="ease-out"
                animationDuration={1200}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card className="p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Syntax error per prompt
        </h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          Once code starts compounding across a session, version-pinned docs keep generated
          calls valid. Without them, the agent drifts toward outdated or invented signatures.
        </p>
        <div className="mt-4 h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={syntaxErrorRate} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
              <XAxis
                dataKey="prompt"
                tick={{ fill: tickColor, fontSize: 12 }}
                axisLine={{ stroke: gridColor }}
                tickLine={false}
                label={{ value: 'Prompt #', position: 'insideBottom', offset: -4, fill: tickColor, fontSize: 12 }}
              />
              <YAxis
                tick={{ fill: tickColor, fontSize: 12 }}
                axisLine={false}
                tickLine={false}
                width={36}
                unit="%"
              />
              <Tooltip content={<ChartTooltip isDark={isDark} unit="%" />} />
              <Legend wrapperStyle={{ fontSize: 12, color: tickColor, paddingTop: 32 }} height={52} verticalAlign="bottom" />
              <Bar
                dataKey="withMcp"
                name="With Lockstep"
                fill={mcp}
                radius={[4, 4, 0, 0]}
                isAnimationActive
                animationEasing="ease-out"
                animationDuration={900}
              />
              <Bar
                dataKey="withoutMcp"
                name="Without Lockstep"
                fill={noMcp}
                radius={[4, 4, 0, 0]}
                isAnimationActive
                animationEasing="ease-out"
                animationDuration={900}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card className="p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Demo
        </h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          See Lockstep resolve real library docs inside an agent session.
        </p>
        <div className="mt-4 aspect-video overflow-hidden rounded-xl border border-black/5 dark:border-white/10">
          <iframe
            className="h-full w-full"
            src="https://www.youtube.com/embed/YS1SB8UrKaA"
            title="Lockstep demo"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            referrerPolicy="strict-origin-when-cross-origin"
            allowFullScreen
          />
        </div>
      </Card>
    </div>
  );
}
