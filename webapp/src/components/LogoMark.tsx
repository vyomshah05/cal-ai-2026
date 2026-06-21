export function LogoMark({ className = 'h-8 w-8' }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="lockstep-grad" x1="0" y1="0" x2="32" y2="32">
          <stop offset="0%" stopColor="#6D5EF6" />
          <stop offset="100%" stopColor="#14B8A6" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#lockstep-grad)" />
      <path
        d="M11 21V13a5 5 0 0 1 10 0"
        stroke="white"
        strokeWidth="2.4"
        strokeLinecap="round"
        fill="none"
      />
      <circle cx="11" cy="21" r="2.2" fill="white" />
      <circle cx="21" cy="13" r="2.2" fill="white" />
    </svg>
  );
}
