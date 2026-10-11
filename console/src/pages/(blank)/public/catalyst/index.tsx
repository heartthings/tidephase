import { Icon } from '@iconify/react';

import { CatalystDashboard } from '@/features/catalyst';
import { useDevToolsGuard } from '@/features/catalyst/useDevToolsGuard';
import {
  usePublicCatalystActiveMessages,
  usePublicCatalystDashboard,
  usePublicCatalystImpacts,
  usePublicCatalystSystemStates
} from '@/service/hooks/usePublicCatalyst';

import './public.css';

// Route metadata is colocated by the project's elegant-router convention.
// eslint-disable-next-line react-refresh/only-export-components
export const route = {
  meta: {
    constant: true,
    hideInMenu: true,
    i18nKey: 'route.(blank)_public_catalyst',
    title: 'public-catalyst'
  }
};

const publicHooks = {
  useActiveMessages: usePublicCatalystActiveMessages,
  useDashboard: usePublicCatalystDashboard,
  useImpacts: usePublicCatalystImpacts,
  useSystemStates: usePublicCatalystSystemStates
};

export default function PublicCatalystPage() {
  const blocked = useDevToolsGuard();

  return (
    <div className="public-catalyst-page">
      <CatalystDashboard
        enabled={!blocked}
        hooks={publicHooks}
        variant="public"
      />
      {blocked && (
        <div
          aria-live="assertive"
          className="public-catalyst-block"
          role="alert"
        >
          <Icon
            className="public-catalyst-block__icon"
            icon="mdi:shield-lock-outline"
          />
          <h2>禁止调试</h2>
          <p>检测到开发者工具，公开催化雷达已暂停数据加载。</p>
          <p>请关闭调试面板后刷新页面继续查看。</p>
        </div>
      )}
    </div>
  );
}
