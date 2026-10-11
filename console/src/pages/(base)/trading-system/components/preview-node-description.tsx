import clsx from 'clsx';

import Markdown from '@/components/Markdown';

import { PREVIEW_DESCRIPTION_VISIBLE_MAX_LEVEL } from '../constants';
import { isPreviewDescriptionTruncated } from '../utils';

import PreviewMarkdownTooltip from './preview-markdown-tooltip';
import styles from './preview-markdown.module.scss';

interface PreviewNodeDescriptionProps {
  className?: string;
  compact?: boolean;
  description: string;
  /** 节点层级，超过 L2 时默认隐藏描述，悬停显示 */
  level?: number;
}

const PreviewNodeDescription = ({ className, compact, description, level = 1 }: PreviewNodeDescriptionProps) => {
  const fullText = description.trim();
  if (!fullText) return null;

  if (level > PREVIEW_DESCRIPTION_VISIBLE_MAX_LEVEL) {
    return null;
  }

  const showFullOnHover = isPreviewDescriptionTruncated(fullText);

  const markdown = (
    <Markdown
      className={clsx(compact && styles.compact, showFullOnHover && styles.clamped)}
      value={fullText}
    />
  );

  const content = <div className={clsx(styles.wrap, showFullOnHover && styles.hoverable, className)}>{markdown}</div>;

  if (!showFullOnHover) return content;

  return (
    <PreviewMarkdownTooltip markdown={fullText}>
      <span className="inline-block max-w-full">{content}</span>
    </PreviewMarkdownTooltip>
  );
};

export default PreviewNodeDescription;
