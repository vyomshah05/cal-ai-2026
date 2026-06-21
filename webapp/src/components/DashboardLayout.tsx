import type { PropsWithChildren } from 'react';
import { Header } from './Header';
import type { SectionKey } from './TopNav';

interface DashboardLayoutProps {
  active: SectionKey;
  onChange: (key: SectionKey) => void;
}

export function DashboardLayout({
  active,
  onChange,
  children,
}: PropsWithChildren<DashboardLayoutProps>) {
  return (
    <div className="min-h-screen bg-cream dark:bg-near-black text-slate-900 dark:text-slate-100 transition-colors animate-fade-in">
      <Header active={active} onChange={onChange} />
      <main className="mx-auto max-w-6xl px-6 py-10">{children}</main>
    </div>
  );
}
