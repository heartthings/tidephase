import FlipText from '@/components/FilpText';
import SystemLogo from '@/components/SystemLogo';
import { LangSwitch } from '@/features/lang';
import { ThemeSchemaSwitch } from '@/features/theme';

import styles from '../layout.module.scss';

const Header = memo(() => {
  const { t } = useTranslation();

  return (
    <header className={styles.header}>
      <SystemLogo className={styles.logo} />

      <FlipText
        className={styles.title}
        word={t('system.title')}
      />

      <div className="i-flex-col">
        <ThemeSchemaSwitch
          className="text-20px lt-sm:text-18px"
          showTooltip={false}
        />
        <LangSwitch showTooltip={false} />
      </div>
    </header>
  );
});

export default Header;
