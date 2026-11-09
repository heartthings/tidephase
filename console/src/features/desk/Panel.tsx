import type { ReactNode } from 'react';

type Props = {
  children: ReactNode;
  className?: string;
  hint?: string;
  title: string;
};

export function Panel({ title, hint, children, className = '' }: Props) {
  return (
    <section className={`gs-panel ${className}`}>
      <h3>
        {title}
        {hint ? <span>{hint}</span> : null}
      </h3>
      {children}
    </section>
  );
}
