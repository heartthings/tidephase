import type { RoutePath } from '@soybean-react/vite-plugin-react-router';
import { Outlet, matchRoutes } from 'react-router-dom';

import { usePrevious, useRoute } from '@/features/router';
import { allRoutes } from '@/router';
import { fetchGetUserInfo } from '@/service/api/auth.ts';
import { useUserInfo } from '@/service/hooks';
import { QUERY_KEYS } from '@/service/keys/index.ts';
import { queryClient } from '@/service/queryClient';
import { localStg } from '@/utils/storage';

function handleRouteSwitch(to: Router.Route, from: Router.Route | null) {
  // route with href
  if (to.handle?.href) {
    window.open(to.handle.href, '_blank');

    return { path: from?.fullPath as string, replace: true };
  }

  return null;
}

function isPublicAccessPath(pathname: string) {
  return pathname === '/public/catalyst' || pathname.startsWith('/public/catalyst/');
}

function guardGuestAccess(to: Router.Route) {
  if (isPublicAccessPath(to.pathname)) return null;

  if (to.handle?.constant && to.id !== 'notFound') return null;

  return `/login?redirect=${to.fullPath}`;
}

// eslint-disable-next-line max-params
function guardAuthedAccess(to: Router.Route, roles: string[], isSuper: boolean, previousRoute: Router.Route | null) {
  const rootRoute: RoutePath = '/';
  const noAuthorizationRoute: RoutePath = '/403';
  const needLogin = !to.handle?.constant;
  const routeRoles = to.handle?.roles || [];
  const hasRole = roles.some(role => routeRoles.includes(role));
  const hasAuth = isSuper || !routeRoles.length || hasRole;

  if (to.fullPath.includes('login') && to.pathname !== '/login-out') {
    return rootRoute;
  }

  if (to.id === 'notFound') {
    const exist = matchRoutes(allRoutes[0].children || [], to.pathname);
    return exist && exist.length > 1 ? noAuthorizationRoute : null;
  }

  if (!needLogin) return handleRouteSwitch(to, previousRoute);

  if (!hasAuth && import.meta.env.VITE_AUTH_ROUTE_MODE === 'static') return noAuthorizationRoute;

  return handleRouteSwitch(to, previousRoute);
}

// eslint-disable-next-line max-params
function createRouteGuard(to: Router.Route, roles: string[], isSuper: boolean, previousRoute: Router.Route | null) {
  if (!localStg.get('token')) return guardGuestAccess(to);

  return guardAuthedAccess(to, roles, isSuper, previousRoute);
}

const RootLayout = () => {
  const route = useRoute();

  const previousRoute = usePrevious(route);

  const { handle, id, pathname } = route;

  const routeId = useRef<string>(null);

  const location = useRef<string | { path: string; replace: boolean } | null>(null);

  const { i18nKey, title } = handle || {};

  const { data: userInfo } = useUserInfo();

  const roles = userInfo?.roles || [];

  const isSuper = roles.includes(import.meta.env.VITE_STATIC_SUPER_ROLE);

  const { t } = useTranslation();

  useEffect(() => {
    document.title = i18nKey ? t(i18nKey) : title;
  }, [i18nKey, title, t]);

  useEffect(() => {
    window.NProgress?.done?.();

    return () => {
      window.NProgress?.start?.();
    };
  }, [pathname]);

  if (routeId.current !== id) {
    routeId.current = id;

    location.current = createRouteGuard(route, roles, isSuper || false, previousRoute);
  }

  // eslint-disable-next-line no-nested-ternary
  return location.current ? (
    typeof location.current === 'string' ? (
      <Navigate to={location.current} />
    ) : (
      <Navigate
        replace={location.current.replace}
        to={location.current.path}
      />
    )
  ) : (
    <Outlet context={previousRoute} />
  );
};

export async function loader() {
  const hasToken = Boolean(localStg.get('token'));

  if (hasToken) {
    await queryClient.prefetchQuery({
      gcTime: Infinity,
      queryFn: fetchGetUserInfo,
      queryKey: QUERY_KEYS.AUTH.USER_INFO,
      staleTime: Infinity
    });
  }
}

export default RootLayout;
