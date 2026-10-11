import { Tooltip } from 'antd';
import type { ReactElement, ReactNode } from 'react';

import Markdown from '@/components/Markdown';

import styles from './preview-markdown.module.scss';

interface PreviewMarkdownTooltipProps {
  children: ReactNode;
  markdown: string;
}

/** 悬停展示 Markdown 描述，不透明卡片样式 */
const PreviewMarkdownTooltip = ({ children, markdown }: PreviewMarkdownTooltipProps): ReactElement => {
  return (
    <Tooltip
      classNames={{ root: styles.tooltipOverlay }}
      mouseEnterDelay={0.25}
      title={
        <div className={styles.tooltipPanel}>
          <Markdown
            className={styles.tooltipMarkdown}
            value={markdown}
          />
        </div>
      }
    >
      {children}
    </Tooltip>
  );
};

export default PreviewMarkdownTooltip;
