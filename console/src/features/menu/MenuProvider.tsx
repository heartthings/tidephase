import type { FC, PropsWithChildren } from 'react';

import { selectActiveFirstLevelMenuKey, setActiveFirstLevelMenuKey } from '@/features/tab/tabStore';

import { useLang } from '../lang';
import { useRoute, useRouter } from '../router';
import { getBaseChildrenRoutes } from '../router/routes';

import { filterRoutesToMenus, getActiveFirstLevelMenuKey, getSelectKey } from './MenuUtil';
import { MixMenuContext } from './menuContext';

const MenuProvider: FC<PropsWithChildren> = ({ children }) => {
  const route = useRoute();

  const router = useRouter();

  const dispatch = useAppDispatch();

  const { locale } = useLang();

  const activeFirstLevelMenuKey = useAppSelector(selectActiveFirstLevelMenuKey);

  const menus = buildCustomMenus(filterRoutesToMenus(getBaseChildrenRoutes(router.reactRouter.routes)), locale);

  const firstLevelMenu = menus.map(menu => {
    const { children: _, ...rest } = menu;
    return rest;
  }) as App.Global.Menu[];

  const childLevelMenus = menus.find(menu => menu.key === activeFirstLevelMenuKey)?.children as App.Global.Menu[];

  const selectKey = getSelectKey(route);

  /** - 可以手动指定菜单或者是默认当前路由的一级菜单 */
  function changeActiveFirstLevelMenuKey(key?: string) {
    const routeKey = key || getActiveFirstLevelMenuKey(route);

    dispatch(setActiveFirstLevelMenuKey(routeKey || ''));
  }

  const mixMenuContext = {
    activeFirstLevelMenuKey,
    allMenus: menus,
    childLevelMenus: childLevelMenus || [],
    firstLevelMenu,
    isActiveFirstLevelMenuHasChildren: activeFirstLevelMenuKey ? Boolean(childLevelMenus) : false,
    route,
    selectKey,
    setActiveFirstLevelMenuKey: changeActiveFirstLevelMenuKey
  };

  return <MixMenuContext value={mixMenuContext}>{children}</MixMenuContext>;
};

function buildCustomMenus(menus: App.Global.Menu[], _locale: string): App.Global.Menu[] {
  const normalizeKey = (key?: string) => (key ? key.replace(/\/+$/, '') || '/' : '');

  const clonedMenus = menus.map(menu => ({
    ...menu,
    children: menu.children ? [...menu.children] : menu.children
  }));

  let topicLibMenu: App.Global.Menu | undefined;
  let capitalFlowMenu: App.Global.Menu | undefined;
  let intervalStatsMenu: App.Global.Menu | undefined;
  let catalystMenu: App.Global.Menu | undefined;
  let tradingNotesMenu: App.Global.Menu | undefined;

  const baseMenus: App.Global.Menu[] = [];

  clonedMenus.forEach(menu => {
    const key = normalizeKey(menu.key);

    if (key === '/topic-lib') {
      topicLibMenu = menu;
      return;
    }

    if (key === '/capital-flow') {
      capitalFlowMenu = menu;
      return;
    }

    if (key === '/interval-stats') {
      intervalStatsMenu = menu;
      return;
    }

    if (key === '/catalyst') {
      catalystMenu = menu;
      return;
    }

    if (key === '/trading-notes') {
      tradingNotesMenu = menu;
      return;
    }

    baseMenus.push(menu);
  });

  const menuMap = new Map(baseMenus.map(menu => [menu.key, menu]));

  const finalMenus: App.Global.Menu[] = [];

  function takeMenu(key: string) {
    const menu = menuMap.get(key);

    if (menu) {
      finalMenus.push(menu);
      menuMap.delete(key);
    }
  }

  takeMenu('/home');
  takeMenu('/trading-system');

  if (topicLibMenu || capitalFlowMenu || intervalStatsMenu || catalystMenu) {
    const children: App.Global.Menu[] = [];
    if (topicLibMenu) {
      children.push({
        ...topicLibMenu,
        children: undefined,
        key: '/topic-lib',
        label: topicLibMenu.label,
        title: topicLibMenu.title
      });
    }
    if (capitalFlowMenu) {
      children.push({
        ...capitalFlowMenu,
        children: undefined,
        key: '/capital-flow',
        label: capitalFlowMenu.label ?? '主力净额',
        title: capitalFlowMenu.title ?? '主力净额'
      });
    }
    if (intervalStatsMenu) {
      children.push({
        ...intervalStatsMenu,
        children: undefined,
        key: '/interval-stats',
        label: intervalStatsMenu.label ?? '区间统计',
        title: intervalStatsMenu.title ?? '区间统计'
      });
    }
    if (catalystMenu) {
      children.push({
        ...catalystMenu,
        children: undefined,
        key: '/catalyst',
        label: catalystMenu.label ?? '催化雷达',
        title: catalystMenu.title ?? '催化雷达'
      });
    }
    const baseForGroup = topicLibMenu ?? capitalFlowMenu ?? intervalStatsMenu ?? catalystMenu!;
    const groupMenu: App.Global.Menu = {
      ...baseForGroup,
      children,
      key: '/research-analysis',
      label: '研究分析',
      title: '研究分析'
    };

    finalMenus.push(groupMenu);
  }

  takeMenu('/market-trends');

  if (tradingNotesMenu) {
    const childMenu: App.Global.Menu = {
      ...tradingNotesMenu,
      children: undefined,
      key: '/trading-notes'
    };

    const groupMenu: App.Global.Menu = {
      ...tradingNotesMenu,
      children: [childMenu],
      key: '/review-summary',
      label: '复盘总结',
      title: '复盘总结'
    };

    finalMenus.push(groupMenu);
  }

  menuMap.forEach(menu => {
    finalMenus.push(menu);
  });

  return finalMenus;
}

export default MenuProvider;
