import { Tooltip } from 'antd';
import clsx from 'clsx';

import { type PreviewDensityLevel, formatPreviewNodeName, isPreviewNodeNameTruncated } from '../preview-density';

interface PreviewNodeTitleProps {
  accentColor?: string;
  className?: string;
  density?: PreviewDensityLevel;
  name: string;
}

const PreviewNodeTitle = ({ accentColor, className, density = 'normal', name }: PreviewNodeTitleProps) => {
  const fullName = name.trim();
  if (!fullName) return null;

  const displayName = formatPreviewNodeName(fullName, density);
  const truncated = isPreviewNodeNameTruncated(fullName, density);

  const title = (
    <p
      className={clsx('m-0 max-w-full truncate font-600 leading-snug', className)}
      style={accentColor ? { color: accentColor } : undefined}
    >
      {displayName}
    </p>
  );

  if (!truncated) return title;

  return (
    <Tooltip
      mouseEnterDelay={0.2}
      title={fullName}
    >
      <span className="inline-block max-w-full cursor-default">{title}</span>
    </Tooltip>
  );
};

export default PreviewNodeTitle;
