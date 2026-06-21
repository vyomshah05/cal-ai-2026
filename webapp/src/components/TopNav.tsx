export type SectionKey = 'claude-code' | 'devin' | 'add-docs';

const SECTIONS: { key: SectionKey; label: string }[] = [
  { key: 'claude-code', label: 'Claude Code' },
  { key: 'devin', label: 'Devin' },
  { key: 'add-docs', label: 'Add Documentation' },
];

interface TopNavProps {
  active: SectionKey;
  onChange: (key: SectionKey) => void;
}

export function TopNav({ active, onChange }: TopNavProps) {
  return (
    <nav className="flex items-center gap-1">
      {SECTIONS.map((s) => {
        const isActive = s.key === active;
        return (
          <button
            key={s.key}
            onClick={() => onChange(s.key)}
            className={`relative rounded-lg px-3 py-2 text-sm font-medium transition ${
              isActive
                ? 'text-accent dark:text-accent-dark bg-accent/10 dark:bg-accent-dark/15'
                : 'text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/10'
            }`}
          >
            {s.label}
          </button>
        );
      })}
    </nav>
  );
}
