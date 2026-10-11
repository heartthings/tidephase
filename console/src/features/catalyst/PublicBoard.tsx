import { Icon } from '@iconify/react';
import { Empty, Progress, Tag, Tooltip } from 'antd';
import dayjs from 'dayjs';
import type { CSSProperties, ReactNode } from 'react';

import { AutoScroll } from './AutoScroll';
import type { PublicScreenId } from './publicScreens';

type PhaseMeta = Record<string, { color: string; label: string }>;

type TopicRow = {
  influence: number;
  level: number;
  messages: number;
  name: string;
  phase: string;
  trend?: string;
};

type StatusMeta = Record<string, { color: string; icon: string; label: string }>;

type Props = {
  accuracy?: Api.Catalyst.Dashboard['accuracy'];
  activeMessages: Api.Catalyst.ActiveMessage[];
  formatPercent: (value?: number) => string;
  impacts: Api.Catalyst.Impact[];
  levelFromImpact: (level: number) => string;
  messageTypeLabel: Record<string, string>;
  onSelectImpact: (impact: Api.Catalyst.Impact) => void;
  phaseMeta: PhaseMeta;
  predictions: Api.Catalyst.Prediction[];
  screen: PublicScreenId;
  stageLabel: Record<string, string>;
  statusMeta: StatusMeta;
  topicRows: TopicRow[];
};

function Panel({
  children,
  className,
  count,
  title
}: {
  children: ReactNode;
  className?: string;
  count?: ReactNode;
  title: string;
}) {
  return (
    <article className={['cr-panel', className].filter(Boolean).join(' ')}>
      <div className="cr-panel__head">
        <h2>{title}</h2>
        {count !== undefined && count !== null ? <span>{count}</span> : null}
      </div>
      {children}
    </article>
  );
}

function ImpactPanel({
  formatPercent,
  impacts,
  messageTypeLabel,
  onSelectImpact,
  stageLabel
}: Pick<Props, 'formatPercent' | 'impacts' | 'messageTypeLabel' | 'onSelectImpact' | 'stageLabel'>) {
  if (!impacts.length) {
    return (
      <Panel
        className="cr-panel--impacts"
        count="0 条"
        title="今日冲击"
      >
        <Empty
          description="当日暂无冲击记录"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </Panel>
    );
  }

  return (
    <Panel
      className="cr-panel--impacts"
      count={`${impacts.length} 条`}
      title="今日冲击"
    >
      <AutoScroll
        className="cr-impact-list"
        contentKey={impacts.map(item => item.id).join(',')}
      >
        <ul className="cr-impact-list__inner">
          {impacts.map(impact => (
            <li key={impact.id}>
              <button
                className="cr-impact-row"
                type="button"
                onClick={() => onSelectImpact(impact)}
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
                    {impact.targetTopics.length > 3 ? <em>+{impact.targetTopics.length - 3}</em> : null}
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
      </AutoScroll>
    </Panel>
  );
}

function ActivePanel({
  activeMessages,
  formatPercent,
  stageLabel
}: Pick<Props, 'activeMessages' | 'formatPercent' | 'stageLabel'>) {
  if (!activeMessages.length) {
    return (
      <Panel
        className="cr-panel--active"
        count="0 条"
        title="发酵中消息"
      >
        <Empty
          description="暂无发酵中消息"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </Panel>
    );
  }

  return (
    <Panel
      className="cr-panel--active"
      count={`${activeMessages.length} 条`}
      title="发酵中消息"
    >
      <AutoScroll
        className="cr-active-list"
        contentKey={activeMessages.map(item => item.id).join(',')}
      >
        <ul className="cr-active-list__inner">
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
                  <span>衰减 {message.expectedDecayDate ? dayjs(message.expectedDecayDate).format('MM/DD') : '—'}</span>
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
      </AutoScroll>
    </Panel>
  );
}

function TopicsPanel({
  formatPercent,
  levelFromImpact,
  phaseMeta,
  topicRows
}: Pick<Props, 'formatPercent' | 'levelFromImpact' | 'phaseMeta' | 'topicRows'>) {
  if (!topicRows.length) {
    return (
      <Panel
        className="cr-panel--topics"
        count="0 个"
        title="题材热力"
      >
        <Empty
          description="暂无题材数据"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </Panel>
    );
  }

  return (
    <Panel
      className="cr-panel--topics"
      count={`${topicRows.length} 个`}
      title="题材热力"
    >
      <AutoScroll
        className="cr-panel__scroll"
        contentKey={topicRows.map(item => item.name).join(',')}
      >
        <div className="cr-topic-grid">
          {topicRows.map(topic => {
            const meta = phaseMeta[topic.phase] || phaseMeta.stable;
            return (
              <div
                className="cr-topic-tile"
                key={topic.name}
                style={
                  {
                    '--influence': `${Math.max(8, topic.influence * 100)}%`,
                    '--phase-color': meta.color
                  } as CSSProperties
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
      </AutoScroll>
    </Panel>
  );
}

function AccuracyPanel({ accuracy, formatPercent }: Pick<Props, 'accuracy' | 'formatPercent'>) {
  const byTopicEntries = Object.entries(accuracy?.byTopic || {});

  return (
    <Panel
      className="cr-panel--accuracy"
      title="准确率"
    >
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
          <span>
            <b>{accuracy?.pending || 0}</b>待验证
          </span>
        </div>
      </div>

      <div className="cr-subhead">分题材准确率</div>
      {byTopicEntries.length ? (
        <AutoScroll
          className="cr-accuracy-groups cr-accuracy-groups--scroll"
          contentKey={byTopicEntries.map(([name]) => name).join(',')}
        >
          <div className="cr-accuracy-groups__inner">
            {byTopicEntries.map(([name, item]) => (
              <div key={name}>
                <span title={name}>{name}</span>
                <div>
                  <i style={{ transform: `scaleX(${item.accuracyRate})` }} />
                </div>
                <strong>{formatPercent(item.accuracyRate)}</strong>
              </div>
            ))}
          </div>
        </AutoScroll>
      ) : (
        <Empty
          description="暂无分题材数据"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      )}
    </Panel>
  );
}

function PredictionsPanel({ predictions, statusMeta }: Pick<Props, 'predictions' | 'statusMeta'>) {
  if (!predictions.length) {
    return (
      <Panel
        className="cr-panel--predictions"
        count="0 条"
        title="近期预测"
      >
        <Empty
          description="暂无近期预测"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </Panel>
    );
  }

  return (
    <Panel
      className="cr-panel--predictions"
      count={`${predictions.length} 条`}
      title="近期预测"
    >
      <AutoScroll
        className="cr-prediction-list"
        contentKey={predictions.map(item => item.id).join(',')}
      >
        <div className="cr-prediction-list__inner">
          {predictions.map(prediction => {
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
          })}
        </div>
      </AutoScroll>
    </Panel>
  );
}

export function PublicBoard({
  accuracy,
  activeMessages,
  formatPercent,
  impacts,
  levelFromImpact,
  messageTypeLabel,
  onSelectImpact,
  phaseMeta,
  predictions,
  screen,
  stageLabel,
  statusMeta,
  topicRows
}: Props) {
  return (
    <section
      aria-label={screen}
      className={`cr-board cr-board--public cr-board--screen-${screen}`}
    >
      {screen === 'catalyst' ? (
        <ImpactPanel
          formatPercent={formatPercent}
          impacts={impacts}
          messageTypeLabel={messageTypeLabel}
          stageLabel={stageLabel}
          onSelectImpact={onSelectImpact}
        />
      ) : null}

      {screen === 'hot' ? (
        <>
          <ActivePanel
            activeMessages={activeMessages}
            formatPercent={formatPercent}
            stageLabel={stageLabel}
          />
          <TopicsPanel
            formatPercent={formatPercent}
            levelFromImpact={levelFromImpact}
            phaseMeta={phaseMeta}
            topicRows={topicRows}
          />
        </>
      ) : null}

      {screen === 'verify' ? (
        <>
          <PredictionsPanel
            predictions={predictions}
            statusMeta={statusMeta}
          />
          <AccuracyPanel
            accuracy={accuracy}
            formatPercent={formatPercent}
          />
        </>
      ) : null}
    </section>
  );
}
