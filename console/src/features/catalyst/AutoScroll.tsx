import { useEffect, useRef } from 'react';

type Props = {
  children: React.ReactNode;
  className?: string;
  /** Restart only when content identity changes. */
  contentKey?: string | number;
  /** Idle time after mount / manual scroll before auto-scroll starts (ms). */
  resumeMs?: number;
  /** Pixels per second while auto-scrolling. */
  speed?: number;
};

/**
 * Scroll container that keeps native manual scrolling. After `resumeMs` without wheel/touch/drag, auto-scrolls when
 * content overflows.
 */
export function AutoScroll({ children, className, contentKey, resumeMs = 5000, speed = 32 }: Props) {
  const viewportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return undefined;

    let raf = 0;
    let last = performance.now();
    let idleUntil = performance.now() + resumeMs;
    let holdUntil = 0;
    let pendingReset = false;

    const markIdleWait = () => {
      idleUntil = performance.now() + resumeMs;
      pendingReset = false;
    };

    // Only treat intentional user gestures as "manual scroll".
    // Do NOT pause on programmatic `scroll` events.
    el.addEventListener('wheel', markIdleWait, { passive: true });
    el.addEventListener('touchstart', markIdleWait, { passive: true });
    el.addEventListener('pointerdown', markIdleWait, { passive: true });

    const tick = (now: number) => {
      raf = requestAnimationFrame(tick);

      const overflow = el.scrollHeight - el.clientHeight;
      if (overflow <= 4) {
        last = now;
        return;
      }

      if (now < idleUntil || now < holdUntil) {
        last = now;
        return;
      }

      if (pendingReset) {
        el.scrollTop = 0;
        pendingReset = false;
        holdUntil = now + 700;
        last = now;
        return;
      }

      const dt = Math.min(0.064, (now - last) / 1000);
      last = now;

      if (el.scrollTop >= overflow - 1) {
        holdUntil = now + 1200;
        pendingReset = true;
        return;
      }

      el.scrollTop = Math.min(overflow, el.scrollTop + speed * dt);
    };

    raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      el.removeEventListener('wheel', markIdleWait);
      el.removeEventListener('touchstart', markIdleWait);
      el.removeEventListener('pointerdown', markIdleWait);
    };
  }, [contentKey, resumeMs, speed]);

  return (
    <div
      className={['cr-auto-scroll', className].filter(Boolean).join(' ')}
      ref={viewportRef}
    >
      {children}
    </div>
  );
}
