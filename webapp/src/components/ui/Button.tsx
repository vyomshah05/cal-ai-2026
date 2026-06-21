import type { ButtonHTMLAttributes } from 'react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost';
}

const base =
  'inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition disabled:opacity-50 disabled:cursor-not-allowed';

const variants: Record<string, string> = {
  primary:
    'bg-gradient-to-br from-accent to-violet-700 dark:from-accent-dark dark:to-violet-400 text-white shadow-sm hover:opacity-90',
  secondary:
    'bg-black/5 dark:bg-white/10 text-slate-900 dark:text-slate-100 hover:bg-black/10 dark:hover:bg-white/15',
  ghost: 'text-slate-600 dark:text-slate-300 hover:bg-black/5 dark:hover:bg-white/10',
};

export function Button({ variant = 'primary', className = '', ...props }: ButtonProps) {
  return <button className={`${base} ${variants[variant]} ${className}`} {...props} />;
}
