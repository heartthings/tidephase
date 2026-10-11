import { Tooltip } from 'antd';

import { PREVIEW_DESCRIPTION_MAX_LENGTH } from '../constants';
import { formatPreviewDescription, isPreviewDescriptionTruncated } from '../utils';

interface TruncatedTreeTextProps {
  className?: string;
  maxLength?: number;
  style?: React.CSSProperties;
  text: string;
}

const TruncatedTreeText = ({
  className,
  maxLength = PREVIEW_DESCRIPTION_MAX_LENGTH,
  style,
  text
}: TruncatedTreeTextProps) => {
  const fullText = text.trim();
  if (!fullText) return null;

  const displayText = formatPreviewDescription(fullText, maxLength);
  const truncated = isPreviewDescriptionTruncated(fullText, maxLength);

  const content = (
    <span
      className={className}
      style={style}
    >
      {displayText}
    </span>
  );

  if (!truncated) return content;

  return (
    <Tooltip
      mouseEnterDelay={0.25}
      title={fullText}
    >
      <span className="inline-block max-w-full cursor-default">{content}</span>
    </Tooltip>
  );
};

export default TruncatedTreeText;
