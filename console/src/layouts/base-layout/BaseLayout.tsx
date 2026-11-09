import { NavLink, Outlet } from 'react-router-dom';

import './console-shell.css';

const NAV: Array<{ label: string; to: string } | { section: string }> = [
  { section: '盘面' },
  { label: '观势台', to: '/home' },
  { label: '涨跌停', to: '/floor' },
  { label: '大盘直播', to: '/market-trends/radar' },
  { label: '盘中快讯', to: '/market-trends/dynamic' },
  { section: '研究' },
  { label: '题材库', to: '/topic-lib' },
  { label: '主力净额', to: '/capital-flow' },
  { label: '区间统计', to: '/interval-stats' },
  { label: '催化雷达', to: '/catalyst' },
  { section: '记录' },
  { label: '交易体系', to: '/trading-system' },
  { label: '交易笔记', to: '/trading-notes' }
];

function isSection(item: { label: string; to: string } | { section: string }): item is { section: string } {
  return 'section' in item;
}

const BaseLayout = () => {
  return (
    <div className="gs-shell">
      <aside className="gs-side">
        <div className="gs-brand">
          <span className="gs-mark">观</span>
          <span>
            <strong>观势</strong>
            <em>Tidephase</em>
          </span>
        </div>
        <nav>
          {NAV.map(item =>
            isSection(item) ? (
              <div
                className="gs-section"
                key={item.section}
              >
                {item.section}
              </div>
            ) : (
              <NavLink
                className={({ isActive }) => (isActive ? 'is-active' : undefined)}
                key={item.to}
                to={item.to}
              >
                {item.label}
              </NavLink>
            )
          )}
        </nav>
      </aside>
      <main className="gs-main">
        <Outlet />
      </main>
    </div>
  );
};

export default BaseLayout;
