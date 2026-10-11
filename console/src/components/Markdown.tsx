import { Image } from 'antd';
import mermaid from 'mermaid';
import type { CSSProperties, ReactNode } from 'react';
import { useEffect, useId, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import rehypeRaw from 'rehype-raw';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';

import 'katex/dist/katex.min.css';

import styles from './Markdown.module.scss';

interface Props {
  className?: string;
  style?: CSSProperties;
  value: string;
}

mermaid.initialize({
  fontFamily: 'ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif',
  securityLevel: 'loose',
  startOnLoad: false,
  theme: 'neutral'
});

function MermaidBlock({ chart }: { chart: string }) {
  const reactId = useId().replace(/:/g, '');
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const renderId = `mermaid-${reactId}-${Math.random().toString(36).slice(2, 8)}`;
    mermaid
      .render(renderId, chart)
      .then(result => {
        if (!cancelled) {
          setSvg(result.svg);
          setError(null);
        }
      })
      .catch(err => {
        if (!cancelled) {
          setSvg('');
          setError(err?.message || 'Mermaid 渲染失败');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [chart, reactId]);

  if (error) {
    return (
      <pre className={styles.codeBlock}>
        <code>{chart}</code>
        <div className={styles.mermaidError}>图示渲染失败：{error}</div>
      </pre>
    );
  }

  return (
    <div
      className={styles.mermaidWrap}
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

function Markdown({ className, style, value }: Props) {
  const content = useMemo(() => (value || '').trim(), [value]);

  if (!content) {
    return null;
  }

  return (
    <div
      className={[styles.markdownBody, className || ''].filter(Boolean).join(' ')}
      style={style}
    >
      <ReactMarkdown
        rehypePlugins={[rehypeRaw, rehypeKatex]}
        remarkPlugins={[remarkGfm, remarkMath]}
        components={{
          a: ({ children, href }) => (
            <a
              href={href}
              rel="noopener noreferrer"
              target="_blank"
            >
              {children}
            </a>
          ),
          code: ({ children, className: codeClassName, ...props }) => {
            const text = String(children).replace(/\n$/, '');
            const match = /language-([\w-]+)/.exec(codeClassName || '');
            const lang = match?.[1];
            const isInline = !codeClassName && !text.includes('\n');

            if (lang === 'mermaid') {
              return <MermaidBlock chart={text} />;
            }

            if (isInline) {
              return (
                <code
                  className={styles.inlineCode}
                  {...props}
                >
                  {children}
                </code>
              );
            }

            return (
              <pre className={styles.codeBlock}>
                {lang ? <div className={styles.codeLang}>{lang}</div> : null}
                <code className={codeClassName}>{text}</code>
              </pre>
            );
          },
          img: ({ alt, src }) => {
            if (!src) return null;
            return (
              <span className={styles.imageWrap}>
                <Image
                  alt={alt || '图片'}
                  className={styles.image}
                  src={src}
                />
                {alt ? <span className={styles.imageCaption}>{alt}</span> : null}
              </span>
            );
          },
          pre: ({ children }) => children as ReactNode,
          table: ({ children }) => (
            <div className={styles.tableWrap}>
              <table>{children}</table>
            </div>
          )
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export default Markdown;
