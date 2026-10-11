import type { ComponentPropsWithoutRef } from 'react';

const SystemLogo = (props: ComponentPropsWithoutRef<'img'>) => {
  return (
    <img
      alt="logo"
      src="/trade.svg"
      {...props}
    />
  );
};

export default SystemLogo;
