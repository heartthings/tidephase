import clsx from 'clsx';

import avatar from '@/assets/imgs/mark.jpg';

const AppAvatar = ({ className, ...props }: React.ComponentProps<'div'>) => {
  return (
    <div
      {...props}
      className={clsx('size-72px  overflow-hidden rd-1/2', className)}
    >
      <img
        className="size-full"
        src={avatar}
      />
    </div>
  );
};

export default AppAvatar;
