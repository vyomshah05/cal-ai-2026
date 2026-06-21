export function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="overflow-x-auto rounded-xl border border-black/10 dark:border-white/10 bg-slate-950 dark:bg-black/40 px-4 py-3 text-xs leading-relaxed text-slate-100">
      <code>{children}</code>
    </pre>
  );
}
