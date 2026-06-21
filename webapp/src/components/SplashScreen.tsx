import { useEffect, useState } from 'react';
import logoLight from '../assets/LOCKSTEP_light.gif';
import logoDark from '../assets/LOCKSTEP_dark.gif';

interface SplashScreenProps {
  onDone: () => void;
  durationMs?: number;
}

export function SplashScreen({ onDone, durationMs = 2600 }: SplashScreenProps) {
  const [fadingOut, setFadingOut] = useState(false);

  useEffect(() => {
    const fadeTimer = setTimeout(() => setFadingOut(true), durationMs - 400);
    const doneTimer = setTimeout(onDone, durationMs);
    return () => {
      clearTimeout(fadeTimer);
      clearTimeout(doneTimer);
    };
  }, [durationMs, onDone]);

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center bg-cream dark:bg-near-black transition-opacity duration-400 ${
        fadingOut ? 'opacity-0 pointer-events-none' : 'opacity-100'
      }`}
    >
      <img
        src={logoLight}
        alt="Lockstep"
        className="block dark:hidden h-[42rem] max-h-[85vh] w-auto md:h-[54rem] object-contain"
      />
      <img
        src={logoDark}
        alt="Lockstep"
        className="hidden dark:block h-[42rem] max-h-[85vh] w-auto md:h-[54rem] object-contain"
      />
    </div>
  );
}
