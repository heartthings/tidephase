import { Outlet } from 'react-router-dom';

import styles from './layout.module.scss';
import Header from './modules/Header';

const LoginLayout = () => {
  return (
    <div className={styles.page}>
      <div
        aria-hidden
        className={styles.pageOverlay}
      />

      <ACard
        className={styles.card}
        variant="borderless"
      >
        <div className={styles.cardInner}>
          <Header />
          <main className={styles.formArea}>
            <Outlet />
          </main>
        </div>
      </ACard>
    </div>
  );
};

export default LoginLayout;
