// Illustrative benchmark data comparing a coding session with Lockstep wired
// in as an MCP server vs. the same session without it. Numbers are
// representative of observed session shapes, not a live telemetry feed.

// Share of total session time spent just planning: figuring out which
// library, version, and API to use before any code gets written. A regular
// LLM has to reason its way there from training data alone; Lockstep
// resolves it directly via RAG against the library corpus plus a Redis
// semantic cache, so the search is mostly skipped.
export const planningTimeShare = [
  { label: 'Without Lockstep', pct: 60 },
  { label: 'With Lockstep', pct: 15 },
];

export const planningTimeReductionPct = Math.round(
  (1 - planningTimeShare[1].pct / planningTimeShare[0].pct) * 100,
);

export interface TimePoint {
  prompt: number;
  withMcp: number;
  withoutMcp: number;
}

// +60s baseline on top of raw model latency, since real prompts in a session
// involve writing/reading longer code blocks, not just a bare API call.
const MINUTE = 60;

export const timePerPrompt: TimePoint[] = [
  { prompt: 1, withMcp: 42 + MINUTE, withoutMcp: 12 + MINUTE },
  { prompt: 2, withMcp: 14 + MINUTE, withoutMcp: 16 + MINUTE },
  { prompt: 3, withMcp: 15 + MINUTE, withoutMcp: 19 + MINUTE },
  { prompt: 4, withMcp: 16 + MINUTE, withoutMcp: 22 + MINUTE },
  { prompt: 5, withMcp: 17 + MINUTE, withoutMcp: 25 + MINUTE },
  { prompt: 6, withMcp: 19 + MINUTE, withoutMcp: 29 + MINUTE },
  { prompt: 7, withMcp: 20 + MINUTE, withoutMcp: 33 + MINUTE },
  { prompt: 8, withMcp: 22 + MINUTE, withoutMcp: 38 + MINUTE },
];

export interface ErrorPoint {
  prompt: number;
  withMcp: number;
  withoutMcp: number;
}

// Syntax-error rate per prompt, starting after prompt 1. The no-Lockstep
// agent slowly self-corrects toward known-safe patterns as the session goes
// on, but never catches up to Lockstep's version-pinned accuracy.
export const syntaxErrorRate: ErrorPoint[] = [
  { prompt: 2, withMcp: 6, withoutMcp: 28 },
  { prompt: 3, withMcp: 5, withoutMcp: 26 },
  { prompt: 4, withMcp: 5, withoutMcp: 24 },
  { prompt: 5, withMcp: 4, withoutMcp: 25 },
  { prompt: 6, withMcp: 5, withoutMcp: 22 },
  { prompt: 7, withMcp: 4, withoutMcp: 20 },
  { prompt: 8, withMcp: 3, withoutMcp: 18 },
];

export const avgSyntaxErrorRate = {
  withMcp: Math.round(
    syntaxErrorRate.reduce((s, p) => s + p.withMcp, 0) / syntaxErrorRate.length,
  ),
  withoutMcp: Math.round(
    syntaxErrorRate.reduce((s, p) => s + p.withoutMcp, 0) / syntaxErrorRate.length,
  ),
};
