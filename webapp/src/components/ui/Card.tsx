import type { PropsWithChildren } from 'react';

export function Card({ children, className = '' }: PropsWithChildren<{ className?: string }>) {
  return (
    <div
      className={`rounded-2xl border border-black/5 dark:border-white/10 bg-surface-light dark:bg-surface-dark shadow-sm shadow-black/5 dark:shadow-black/30 ${className}`}
    >
      {children}
    </div>
  );
}
