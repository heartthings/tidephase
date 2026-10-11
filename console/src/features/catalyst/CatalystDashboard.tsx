import { Icon } from '@iconify/react';
import type { UseQueryResult } from '@tanstack/react-query';
import { Button, DatePicker, Drawer, Empty, Progress, Skeleton, Tag, Tooltip } from 'antd';
import dayjs from 'dayjs';
import { useMemo, useState } from 'react';

import Markdown from '@/components/Markdown';

import { PublicBoard } from './PublicBoard';
import { PUBLIC_SCREENS, type PublicScreenId } from './publicScreens';
import { PUBLIC_CATALYST_USAGE_GUIDE } from './publicUsageGuide';
import './styles.css';

export type CatalystDashboardVariant = 'app' | 'public';

export type CatalystQueryHooks = {
  useActiveMessages: (options?: { enabled?: boolean }) => UseQueryResult<Api.Catalyst.ActiveMessage[] | undefined>;
  useDashboard: (date: string, options?: { enabled?: boolean }) => UseQueryResult<Api.Catalyst.Dashboard | undefined>;
  useImpacts: (date: string, options?: { enabled?: boolean }) => UseQueryResult<Api.Catalyst.Impact[] | undefined>;
  useSystemStates: (
    date: string,
    options?: { enabled?: boolean }
  ) => UseQueryResult<Api.Catalyst.SystemState[] | undefined>;
};

type Props = {
  /** When false, queries pause (e.g. DevTools blocked on public page). */
  enabled?: boolean;
  hooks: CatalystQueryHooks;
  variant?: CatalystDashboardVariant;
};

const phaseMeta: Record<string, { color: string; label: string }> = {
  active: { color: '#646cff', label: '活跃' },
  critical: { color: '#f5222d', label: '临界' },
  fermentation: { color: '#52c41a', label: '发酵' },
  oscillation: { color: '#faad14', label: '震荡' },
  overheat: { color: '#fa541c', label: '过热' },
  recovery: { color: '#2080f0', label: '修复' },
  retreat: { color: '#f5222d', label: '退潮' },
  stable: { color: '#8c8c8c', label: '稳态' },
  transition: { color: '#cf1322', label: '相变' },
  trending_down: { color: '#f5222d', label: '下行' },
  trending_up: { color: '#52c41a', label: '上行' }
};

const messageTypeLabel: Record<string, string> = {
  breaking_event: '突发事件',
  earnings: '财报经营',
  geopolitical: '地缘贸易',
  global_market: '全球市场',
  industry: '行业事件',
  policy: '政策'
};

const stageLabel: Record<string, string> = {
  decay: '衰减期',
  fermentation: '发酵期',
  shock: '冲击期',
  spread: '扩散期'
};

const couplingLabel: Record<string, string> = {
  high: '高',
  low: '低',
  medium: '中',
  strong: '强',
  weak: '弱'
};

const sentimentLabel: Record<string, string> = {
  bearish: '偏空',
  bullish: '偏多',
  neutral: '中性',
  risk_off: '避险',
  risk_on: '风险偏好'
};

const statusMeta = {
  falsified: { color: 'error', icon: 'mdi:close-circle-outline', label: '证伪' },
  partially_verified: { color: 'warning', icon: 'mdi:alert-circle-outline', label: '部分验证' },
  pending: { color: 'processing', icon: 'mdi:clock-outline', label: '待验证' },
  verified: { color: 'success', icon: 'mdi:check-circle-outline', label: '已验证' }
} as const;

const IMPACT_LEVELS = ['S', 'A', 'B', 'C', 'D'] as const;
const TOPIC_PREVIEW = 8;

function formatPercent(value?: number) {
  return `${Math.round((value || 0) * 100)}%`;
}

function levelFromImpact(level: number) {
  return ['', 'D', 'C', 'B', 'A', 'S'][level] || '—';
}

function SectionToggle({ label, onToggle, open }: { label: string; onToggle: () => void; open: boolean }) {
  return (
    <button
      className="cr-toggle"
      type="button"
      onClick={onToggle}
    >
      {open ? '收起' : label}
      <Icon icon={open ? 'mdi:chevron-up' : 'mdi:chevron-down'} />
    </button>
  );
}

// Dashboard composition coordinates five correlated data views in one screen.
// eslint-disable-next-line complexity
export function CatalystDashboard({ enabled = true, hooks, variant = 'app' }: Props) {
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [selectedImpact, setSelectedImpact] = useState<Api.Catalyst.Impact | null>(null);
  const [topicsExpanded, setTopicsExpanded] = useState(false);
  const [noteOpen, setNoteOpen] = useState(false);
  const [accuracyOpen, setAccuracyOpen] = useState(false);
  const [usageOpen, setUsageOpen] = useState(false);
  const [publicScreen, setPublicScreen] = useState<PublicScreenId>('catalyst');

  const queryOpts = { enabled };
  const dashboardQuery = hooks.useDashboard(date, queryOpts);
  const impactsQuery = hooks.useImpacts(date, queryOpts);
  const statesQuery = hooks.useSystemStates(date, queryOpts);
  const activeQuery = hooks.useActiveMessages(queryOpts);

  const dashboard = dashboardQuery.data;
  const impacts = impactsQuery.data || [];
  const state = statesQuery.data?.[0];
  const activeMessages = useMemo(
    () => activeQuery.data || dashboard?.activeMessageList || [],
    [activeQuery.data, dashboard?.activeMessageList]
  );
  const isLoading = dashboardQuery.isLoading || impactsQuery.isLoading || statesQuery.isLoading;

  const topicRows = useMemo(() => {
    const topics = new Map<
      string,
      { influence: number; level: number; messages: number; phase: string; trend?: string }
    >();

    Object.entries(state?.topicStates || {}).forEach(([name, topicState]) => {
      topics.set(name, {
        influence: 0,
        level: 0,
        messages: 0,
        phase: topicState.phase,
        trend: topicState.trend
      });
    });

    activeMessages.forEach(message => {
      (message.targetTopics || []).forEach(topic => {
        const current = topics.get(topic.topicName) || {
          influence: 0,
          level: 0,
          messages: 0,
          phase: 'stable'
        };
        topics.set(topic.topicName, {
          ...current,
          influence: Math.max(current.influence, message.remainingInfluence),
          level: Math.max(current.level, message.impactLevel),
          messages: current.messages + 1
        });
      });
    });

    return [...topics.entries()]
      .map(([name, value]) => ({ name, ...value }))
      .sort((a, b) => b.level - a.level || b.influence - a.influence);
  }, [activeMessages, state?.topicStates]);

  const visibleTopics = topicsExpanded ? topicRows : topicRows.slice(0, TOPIC_PREVIEW);
  const impactCounts = dashboard?.today.impacts;
  const accuracy = dashboard?.accuracy;
  const systemState = state || dashboard?.today.systemState;
  const phase = phaseMeta[systemState?.overallPhase || 'stable'] || phaseMeta.stable;
  const isPublic = variant === 'public';

  const handleRefresh = async () => {
    await Promise.all([dashboardQuery.refetch(), impactsQuery.refetch(), statesQuery.refetch(), activeQuery.refetch()]);
  };

  if (isLoading && !dashboard) {
    return (
      <div className={`catalyst-shell${isPublic ? ' catalyst-shell--public' : ''}`}>
        <Skeleton
          active
          paragraph={{ rows: 10 }}
        />
      </div>
    );
  }

  return (
    <main className={`catalyst-shell${isPublic ? ' catalyst-shell--public' : ''}`}>
      <header className="cr-toolbar">
        <div className="cr-toolbar__title">
          <Icon
            aria-hidden="true"
            className="cr-toolbar__icon"
            icon="mdi:radar"
          />
          <div>
            <h1>催化雷达</h1>
            <p>消息冲击 · 系统相态 · 预测验证</p>
          </div>
          {isPublic && (
            <Tooltip title="使用说明">
              <button
                aria-label="打开使用说明"
                className="cr-help-btn"
                type="button"
                onClick={() => setUsageOpen(true)}
              >
                <Icon
                  aria-hidden="true"
                  icon="mdi:help-circle-outline"
                />
                <span className="cr-help-btn__pulse" />
              </button>
            </Tooltip>
          )}
        </div>
        <div className="cr-toolbar__actions">
          {isPublic && (
            <div
              aria-label="大屏切换"
              className="cr-screen-switch"
              role="tablist"
            >
              {PUBLIC_SCREENS.map(item => (
                <button
                  aria-selected={publicScreen === item.id}
                  className={`cr-screen-switch__btn${publicScreen === item.id ? ' is-active' : ''}`}
                  key={item.id}
                  role="tab"
                  title={item.hint}
                  type="button"
                  onClick={() => setPublicScreen(item.id)}
                >
                  <span>{item.label}</span>
                  <small>{item.hint}</small>
                </button>
              ))}
            </div>
          )}
          <DatePicker
            allowClear={false}
            size="small"
            value={dayjs(date)}
            onChange={value => setDate((value || dayjs()).format('YYYY-MM-DD'))}
          />
          <Button
            aria-label="刷新催化雷达"
            icon={<Icon icon="mdi:refresh" />}
            loading={dashboardQuery.isFetching}
            size="small"
            onClick={handleRefresh}
          >
            刷新
          </Button>
        </div>
      </header>

      <section
        aria-label="关键指标"
        className={`cr-kpi${isPublic ? ' cr-kpi--public' : ''}`}
      >
        <article className="cr-kpi__phase">
          <span
            className="cr-kpi__dot"
            style={{ backgroundColor: phase.color }}
          />
          <div>
            <small>当前相态</small>
            <strong style={{ color: phase.color }}>{phase.label}</strong>
          </div>
          <span className="cr-live">LIVE</span>
        </article>

        <article>
          <small>今日冲击</small>
          <strong>{impactCounts?.total ?? impacts.length}</strong>
          <div className="cr-kpi__grades">
            {IMPACT_LEVELS.map(label => {
              const key = `${label.toLowerCase()}Level` as keyof NonNullable<typeof impactCounts>;
              const count = impactCounts?.[key] ?? impacts.filter(item => item.impactLabel === label).length;
              return (
                <span
                  className={`cr-grade grade-${label.toLowerCase()}`}
                  key={label}
                >
                  {label}
                  <b>{count || 0}</b>
                </span>
              );
            })}
          </div>
        </article>

        <article>
          <small>发酵中</small>
          <strong>{dashboard?.today.activeMessages ?? activeMessages.length}</strong>
          <span>条持续影响</span>
        </article>

        <article>
          <small>综合准确率</small>
          <strong className="cr-kpi__accent">{formatPercent(accuracy?.accuracyRate)}</strong>
          <span className={Number(accuracy?.trendDelta) >= 0 ? 'trend-up' : 'trend-down'}>
            <Icon icon={Number(accuracy?.trendDelta) >= 0 ? 'mdi:trending-up' : 'mdi:trending-down'} />
            30日 {Number(accuracy?.trendDelta || 0) >= 0 ? '+' : ''}
            {formatPercent(accuracy?.trendDelta)}
          </span>
        </article>

        <article>
          <small>待验证</small>
          <strong>{dashboard?.today.pendingPredictions ?? accuracy?.pending ?? 0}</strong>
          <span>条预测</span>
        </article>

        {isPublic && (
          <article
            className="cr-kpi__system"
            title={systemState?.overallNote || undefined}
          >
            <small>系统状态</small>
            <div className="cr-kpi__system-row">
              <span>
                情绪
                <b>{sentimentLabel[systemState?.sentiment || ''] || systemState?.sentiment || '中性'}</b>
              </span>
              <span>
                耦合
                <b>{couplingLabel[systemState?.globalCoupling || ''] || systemState?.globalCoupling || '中'}</b>
              </span>
            </div>
            {systemState?.overallNote ? (
              <span className="cr-kpi__system-note">{systemState.overallNote}</span>
            ) : (
              <span>无额外说明</span>
            )}
          </article>
        )}
      </section>

      {isPublic ? (
        <PublicBoard
          accuracy={accuracy}
          activeMessages={activeMessages}
          formatPercent={formatPercent}
          impacts={impacts}
          levelFromImpact={levelFromImpact}
          messageTypeLabel={messageTypeLabel}
          phaseMeta={phaseMeta}
          predictions={dashboard?.recentPredictions || []}
          screen={publicScreen}
          stageLabel={stageLabel}
          statusMeta={statusMeta}
          topicRows={topicRows}
          onSelectImpact={setSelectedImpact}
        />
      ) : (
        <section className="cr-board">
          <article className="cr-panel--impacts cr-panel">
            <div className="cr-panel__head">
              <h2>今日冲击</h2>
              <span>{impacts.length} 条</span>
            </div>
            {impacts.length ? (
              <ul className="cr-impact-list">
                {impacts.map(impact => (
                  <li key={impact.id}>
                    <button
                      className="cr-impact-row"
                      type="button"
                      onClick={() => setSelectedImpact(impact)}
                    >
                      <span className={`cr-impact-row__grade grade-${impact.impactLabel.toLowerCase()}`}>
                        {impact.impactLabel}
                      </span>
                      <div className="cr-impact-row__body">
                        <div className="cr-impact-row__meta">
                          <time>{impact.messageTime ? dayjs(impact.messageTime).format('HH:mm') : '--:--'}</time>
                          <span>{messageTypeLabel[impact.messageType] || impact.messageType}</span>
                          <span>{stageLabel[impact.lifecycleStage] || impact.lifecycleStage}</span>
                        </div>
                        <strong>{impact.messageSummary}</strong>
                        <p>{impact.predictedEffect}</p>
                        <div className="cr-impact-row__topics">
                          {impact.targetTopics.slice(0, 3).map(topic => (
                            <em key={`${impact.id}-${topic.topicName}`}>{topic.topicName}</em>
                          ))}
                          {impact.targetTopics.length > 3 && <em>+{impact.targetTopics.length - 3}</em>}
                        </div>
                      </div>
                      <div className="cr-impact-row__side">
                        <Tooltip title="剩余影响力">
                          <b>{formatPercent(impact.remainingInfluence)}</b>
                        </Tooltip>
                        <Icon icon="mdi:chevron-right" />
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty
                description="当日暂无冲击记录"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            )}
          </article>

          <article className="cr-panel cr-panel--active">
            <div className="cr-panel__head">
              <h2>发酵中消息</h2>
              <span>{activeMessages.length} 条</span>
            </div>
            {activeMessages.length ? (
              <ul className="cr-active-list">
                {activeMessages.map(message => (
                  <li
                    className="cr-active-item"
                    key={message.id}
                  >
                    <span className={`cr-impact-row__grade grade-${message.impactLabel.toLowerCase()}`}>
                      {message.impactLabel}
                    </span>
                    <div className="cr-active-item__body">
                      <strong>{message.messageSummary}</strong>
                      <div className="cr-active-item__meta">
                        <Tag bordered={false}>{stageLabel[message.currentStage] || message.currentStage}</Tag>
                        <span>
                          衰减 {message.expectedDecayDate ? dayjs(message.expectedDecayDate).format('MM/DD') : '—'}
                        </span>
                        {(message.targetTopics || []).slice(0, 2).map(topic => (
                          <em key={`${message.id}-${topic.topicName}`}>{topic.topicName}</em>
                        ))}
                      </div>
                      <Progress
                        percent={Math.round(message.remainingInfluence * 100)}
                        showInfo={false}
                        size="small"
                        strokeColor={message.impactLevel >= 4 ? '#f5222d' : '#faad14'}
                      />
                    </div>
                    <strong className="cr-active-item__pct">{formatPercent(message.remainingInfluence)}</strong>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty
                description="暂无发酵中消息"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            )}
          </article>

          <div className="cr-col cr-col--side">
            <article className="cr-panel cr-panel--state">
              <div className="cr-panel__head">
                <h2>系统状态</h2>
                {systemState?.overallNote && (
                  <SectionToggle
                    label="状态说明"
                    open={noteOpen}
                    onToggle={() => setNoteOpen(open => !open)}
                  />
                )}
              </div>
              {systemState ? (
                <>
                  <div className="cr-state-grid">
                    <div>
                      <small>全球耦合</small>
                      <strong>
                        {couplingLabel[systemState.globalCoupling || ''] || systemState.globalCoupling || '中'}
                      </strong>
                    </div>
                    <div>
                      <small>市场情绪</small>
                      <strong>{sentimentLabel[systemState.sentiment || ''] || systemState.sentiment || '中性'}</strong>
                    </div>
                    <div>
                      <small>相态</small>
                      <strong style={{ color: phase.color }}>{phase.label}</strong>
                    </div>
                  </div>
                  {noteOpen && systemState.overallNote && <p className="cr-note">{systemState.overallNote}</p>}
                </>
              ) : (
                <Empty
                  description="当日暂无系统状态快照"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              )}
            </article>

            <article className="cr-panel cr-panel--topics">
              <div className="cr-panel__head">
                <h2>题材热力</h2>
                <span>{topicRows.length} 个</span>
              </div>
              {topicRows.length ? (
                <>
                  <div className="cr-panel__scroll">
                    <div className="cr-topic-grid">
                      {(topicsExpanded ? topicRows : visibleTopics).map(topic => {
                        const meta = phaseMeta[topic.phase] || phaseMeta.stable;
                        return (
                          <div
                            className="cr-topic-tile"
                            key={topic.name}
                            style={
                              {
                                '--influence': `${Math.max(8, topic.influence * 100)}%`,
                                '--phase-color': meta.color
                              } as React.CSSProperties
                            }
                          >
                            <div className="cr-topic-tile__top">
                              <strong title={topic.name}>{topic.name}</strong>
                              <span
                                className={`cr-grade${topic.level ? ` grade-${levelFromImpact(topic.level).toLowerCase()}` : ''}`}
                              >
                                {topic.level ? levelFromImpact(topic.level) : '—'}
                              </span>
                            </div>
                            <div className="cr-topic-tile__bar">
                              <i />
                            </div>
                            <div className="cr-topic-tile__meta">
                              <em style={{ color: meta.color }}>{meta.label}</em>
                              <span>{topic.messages ? `${topic.messages} 消息` : '无冲击'}</span>
                              <b>{topic.influence ? formatPercent(topic.influence) : '—'}</b>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                  {topicRows.length > TOPIC_PREVIEW && (
                    <SectionToggle
                      label={`展开全部 ${topicRows.length} 个题材`}
                      open={topicsExpanded}
                      onToggle={() => setTopicsExpanded(open => !open)}
                    />
                  )}
                </>
              ) : (
                <Empty
                  description="暂无题材数据"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              )}
            </article>

            <article className="cr-panel cr-panel--accuracy">
              <div className="cr-panel__head">
                <h2>预测验证</h2>
                <SectionToggle
                  label="分题材准确率"
                  open={accuracyOpen}
                  onToggle={() => setAccuracyOpen(open => !open)}
                />
              </div>

              <div className="cr-accuracy-summary">
                <div className="cr-accuracy-score">
                  <strong>{formatPercent(accuracy?.accuracyRate)}</strong>
                  <span>综合准确率</span>
                </div>
                <div className="cr-accuracy-counts">
                  <span>
                    <b>{accuracy?.verified || 0}</b>已验证
                  </span>
                  <span>
                    <b>{accuracy?.partiallyVerified || 0}</b>部分
                  </span>
                  <span>
                    <b>{accuracy?.falsified || 0}</b>证伪
                  </span>
                </div>
              </div>

              {accuracyOpen && (
                <div className="cr-accuracy-groups">
                  {Object.entries(accuracy?.byTopic || {}).length ? (
                    Object.entries(accuracy?.byTopic || {}).map(([name, item]) => (
                      <div key={name}>
                        <span title={name}>{name}</span>
                        <div>
                          <i style={{ transform: `scaleX(${item.accuracyRate})` }} />
                        </div>
                        <strong>{formatPercent(item.accuracyRate)}</strong>
                      </div>
                    ))
                  ) : (
                    <Empty
                      description="暂无分题材数据"
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                    />
                  )}
                </div>
              )}

              <div className="cr-prediction-list">
                {(dashboard?.recentPredictions || []).length ? (
                  (dashboard?.recentPredictions || []).map(prediction => {
                    const meta = statusMeta[prediction.status];
                    return (
                      <div key={prediction.id}>
                        <Icon icon={meta.icon} />
                        <span title={prediction.prediction}>{prediction.prediction}</span>
                        <Tag
                          bordered={false}
                          color={meta.color}
                        >
                          {meta.label}
                        </Tag>
                      </div>
                    );
                  })
                ) : (
                  <Empty
                    description="暂无近期预测"
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                  />
                )}
              </div>
            </article>
          </div>
        </section>
      )}

      <Drawer
        open={Boolean(selectedImpact)}
        title="消息冲击评估"
        width={Math.min(520, typeof window !== 'undefined' ? window.innerWidth - 24 : 520)}
        onClose={() => setSelectedImpact(null)}
      >
        {selectedImpact && (
          <div className="impact-detail">
            <div className={`impact-detail__grade grade-${selectedImpact.impactLabel.toLowerCase()}`}>
              {selectedImpact.impactLabel}
            </div>
            <div>
              <span>{messageTypeLabel[selectedImpact.messageType] || selectedImpact.messageType}</span>
              <h2>{selectedImpact.messageSummary}</h2>
            </div>
            <dl>
              <div>
                <dt>预测影响</dt>
                <dd>{selectedImpact.predictedEffect}</dd>
              </div>
              <div>
                <dt>生命周期</dt>
                <dd>{stageLabel[selectedImpact.lifecycleStage]}</dd>
              </div>
              <div>
                <dt>剩余影响力</dt>
                <dd>{formatPercent(selectedImpact.remainingInfluence)}</dd>
              </div>
              <div>
                <dt>置信度</dt>
                <dd>{formatPercent(selectedImpact.confidence)}</dd>
              </div>
              <div>
                <dt>目标题材</dt>
                <dd>{selectedImpact.targetTopics.map(topic => topic.topicName).join('、')}</dd>
              </div>
            </dl>
            {selectedImpact.detailedAnalysis && (
              <div className="impact-detail__analysis">{selectedImpact.detailedAnalysis}</div>
            )}
          </div>
        )}
      </Drawer>

      {isPublic && (
        <Drawer
          destroyOnClose
          open={usageOpen}
          styles={{ body: { paddingTop: 8 } }}
          title="使用说明"
          width={Math.min(480, typeof window !== 'undefined' ? window.innerWidth - 24 : 480)}
          onClose={() => setUsageOpen(false)}
        >
          <Markdown
            className="cr-usage-markdown"
            value={PUBLIC_CATALYST_USAGE_GUIDE}
          />
        </Drawer>
      )}
    </main>
  );
}

export default CatalystDashboard;
