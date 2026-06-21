import logoLight from '../assets/logo_light.png';
import logoDark from '../assets/logo_dark.png';
import { TopNav, type SectionKey } from './TopNav';

interface HeaderProps {
  active: SectionKey;
  onChange: (key: SectionKey) => void;
}

export function Header({ active, onChange }: HeaderProps) {
  return (
    <header className="sticky top-0 z-40 border-b border-black/5 dark:border-white/10 bg-cream/70 dark:bg-near-black/70 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-2">
        <TopNav active={active} onChange={onChange} />
        <a href="#" className="flex items-center" aria-label="Lockstep">
          <img src={logoLight} alt="Lockstep" className="block dark:hidden h-[3.2rem] w-auto object-contain" />
          <img src={logoDark} alt="Lockstep" className="hidden dark:block h-[3.2rem] w-auto object-contain" />
        </a>
      </div>
    </header>
  );
}
