import { useEffect, useState } from 'react';

type Options = {
  /** Threshold (px) of outer-inner width/height gap that suggests docked DevTools. */
  sizeThreshold?: number;
};

/**
 * Client-side DevTools deterrence for the public radar page. Not absolute security — skilled users can bypass; real
 * gate is AES token + TTL.
 */
export function useDevToolsGuard(options?: Options) {
  const sizeThreshold = options?.sizeThreshold ?? 160;
  const [blocked, setBlocked] = useState(false);

  useEffect(() => {
    const block = () => setBlocked(true);

    const onContextMenu = (e: MouseEvent) => {
      e.preventDefault();
    };

    const onKeyDown = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      const isMac = navigator.platform.toLowerCase().includes('mac');

      if (key === 'f12') {
        e.preventDefault();
        block();
        return;
      }

      if (e.ctrlKey && e.shiftKey && (key === 'i' || key === 'j' || key === 'c')) {
        e.preventDefault();
        block();
        return;
      }

      if (isMac && e.metaKey && e.altKey && (key === 'i' || key === 'j' || key === 'c')) {
        e.preventDefault();
        block();
      }

      if (e.ctrlKey && key === 'u') {
        e.preventDefault();
      }
    };

    const checkDocked = () => {
      const isCoarsePointer = window.matchMedia('(pointer: coarse)').matches;
      if (isCoarsePointer) return;

      const widthGap = Math.abs(window.outerWidth - window.innerWidth);
      const heightGap = Math.abs(window.outerHeight - window.innerHeight);
      if (widthGap > sizeThreshold || heightGap > sizeThreshold) {
        block();
      }
    };

    const onSelectStart = (e: Event) => {
      e.preventDefault();
    };

    document.addEventListener('contextmenu', onContextMenu);
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('selectstart', onSelectStart);
    window.addEventListener('resize', checkDocked);
    checkDocked();

    const timer = window.setInterval(checkDocked, 1200);

    return () => {
      document.removeEventListener('contextmenu', onContextMenu);
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('selectstart', onSelectStart);
      window.removeEventListener('resize', checkDocked);
      window.clearInterval(timer);
    };
  }, [sizeThreshold]);

  return blocked;
}
