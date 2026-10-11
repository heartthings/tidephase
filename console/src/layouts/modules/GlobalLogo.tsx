import clsx from 'clsx';
import type { LinkProps } from 'react-router-dom';
import { Link } from 'react-router-dom';

import SystemLogo from '@/components/SystemLogo';

interface Props extends Omit<LinkProps, 'to'> {
  showTitle?: boolean;
  variant?: 'default' | 'fill';
}
const GlobalLogo: FC<Props> = memo(({ className, showTitle = true, variant = 'default', ...props }) => {
  const { t } = useTranslation();

  return (
    <Link
      className={clsx('w-full flex-center nowrap-hidden', className)}
      to={import.meta.env.VITE_ROUTE_HOME}
      {...props}
    >
      {variant === 'fill' ? (
        <img
          alt="logo"
          className="h-32px w-32px"
          src="/trade-fill.svg"
        />
      ) : (
        <SystemLogo className="text-32px text-primary" />
      )}
      <h2
        className="pl-8px text-16px text-primary font-bold transition duration-300 ease-in-out"
        style={{ display: showTitle ? 'block' : 'none' }}
      >
        {t('system.title')}
      </h2>
    </Link>
  );
});

export default GlobalLogo;
