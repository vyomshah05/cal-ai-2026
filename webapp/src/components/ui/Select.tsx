import type { SelectHTMLAttributes } from 'react';

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className="w-full rounded-lg border border-black/10 dark:border-white/15 bg-white dark:bg-black/20 px-3 py-2 text-sm text-slate-900 dark:text-slate-100 outline-none focus:ring-2 focus:ring-accent/40 dark:focus:ring-accent-dark/40 transition"
      {...props}
    />
  );
}
