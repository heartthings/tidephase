import type { ReactElement, ReactNode } from 'react';

import { PREVIEW_DESCRIPTION_VISIBLE_MAX_LEVEL } from '../constants';

import PreviewMarkdownTooltip from './preview-markdown-tooltip';

interface PreviewDescriptionHostProps {
  children: ReactNode;
  description?: string;
  level: number;
}

/** L3+ 不占位，悬停整块区域时 Tooltip 以 Markdown 展示描述 */
const PreviewDescriptionHost = ({ children, description, level }: PreviewDescriptionHostProps): ReactElement => {
  const fullText = description?.trim();
  const hoverOnly = level > PREVIEW_DESCRIPTION_VISIBLE_MAX_LEVEL && Boolean(fullText);

  if (!hoverOnly) {
    return children as ReactElement;
  }

  return (
    <PreviewMarkdownTooltip markdown={fullText!}>
      <span className="max-w-full min-h-0 min-w-0 flex flex-col flex-1">{children}</span>
    </PreviewMarkdownTooltip>
  );
};

export default PreviewDescriptionHost;
