import { CatalystDashboard } from '@/features/catalyst';
import {
  useCatalystActiveMessages,
  useCatalystDashboard,
  useCatalystImpacts,
  useCatalystSystemStates
} from '@/service/hooks/useCatalyst';

// Route metadata is colocated by the project's elegant-router convention.
// eslint-disable-next-line react-refresh/only-export-components
export const route = {
  meta: {
    constant: true,
    i18nKey: 'route.(base)_catalyst',
    icon: 'mdi:radar',
    order: 6,
    title: 'catalyst'
  }
};

const appHooks = {
  useActiveMessages: useCatalystActiveMessages,
  useDashboard: useCatalystDashboard,
  useImpacts: useCatalystImpacts,
  useSystemStates: useCatalystSystemStates
};

export default function CatalystPage() {
  return (
    <CatalystDashboard
      hooks={appHooks}
      variant="app"
    />
  );
}
