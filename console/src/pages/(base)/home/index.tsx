import { DatePicker, Skeleton } from 'antd';
import dayjs from 'dayjs';
import { useMemo, useState } from 'react';

import { Panel } from '@/features/desk/Panel';
import { Pct } from '@/features/desk/Pct';
import '@/features/desk/desk.css';
import { useConsoleDesk } from '@/service/hooks/useDesk';

function fmt(n?: number | null, digits = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return n.toFixed(digits);
}

const Home = () => {
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const { data, isLoading, isFetching } = useConsoleDesk(date);

  const sh = useMemo(() => data?.indices?.find(i => i.code === 'sh000001'), [data]);
  const cy = useMemo(() => data?.indices?.find(i => i.code === 'sz399006'), [data]);

  if (isLoading && !data) {
    return (
      <div className="gs-desk p-2">
        <Skeleton
          active
          paragraph={{ rows: 10 }}
        />
      </div>
    );
  }

  const b = data?.breadth || {};
  const s = data?.sentiment || {};

  return (
    <div className="gs-desk space-y-3">
      <div className="gs-pagehead">
        <div>
          <h1>观势台</h1>
          <p className="gs-sub">
            {data?.date}
            {data?.isTradingDay ? ' 交易日' : ' 休市'}
            {isFetching ? ' · 刷新中' : ''}
          </p>
        </div>
        <DatePicker
          allowClear={false}
          value={dayjs(date)}
          onChange={d => setDate(d?.format('YYYY-MM-DD') || dayjs().format('YYYY-MM-DD'))}
        />
      </div>

      <div className="gs-kpis">
          <div className="gs-kpi">
            <div className="label">上证</div>
            <div className="value">
              <Pct value={sh?.pct} />
            </div>
            <div className="meta">{fmt(sh?.close)}</div>
          </div>
          <div className="gs-kpi">
            <div className="label">创业板</div>
            <div className="value">
              <Pct value={cy?.pct} />
            </div>
            <div className="meta">{fmt(cy?.close)}</div>
          </div>
          <div className="gs-kpi">
            <div className="label">涨 / 跌</div>
            <div className="value">
              <span className="gs-up">{b.upN ?? '—'}</span>
              <span className="text-[var(--gs-muted)]"> / </span>
              <span className="gs-down">{b.downN ?? '—'}</span>
            </div>
            <div className="meta">平 {b.flatN ?? '—'}</div>
          </div>
          <div className="gs-kpi">
            <div className="label">涨停 / 跌停</div>
            <div className="value">
              {s.limitUp ?? '—'} / {s.limitDown ?? '—'}
            </div>
            <div className="meta">炸板率 {fmt(s.brokenRate as number | null)}%</div>
          </div>
          <div className="gs-kpi">
            <div className="label">最高连板</div>
            <div className="value">{s.maxBoard ?? '—'}</div>
            <div className="meta">晋级率 {fmt(s.promoteRate as number | null)}%</div>
          </div>
          <div className="gs-kpi">
            <div className="label">题材数</div>
            <div className="value">{data?.topicCount ?? '—'}</div>
            <div className="meta">更新 {data?.asOf?.slice(11, 16) || '—'}</div>
          </div>
        </div>

      <div className="gs-grid">
        <Panel
          hint={`${data?.live?.length || 0} 条`}
          title="大盘直播"
        >
          {(data?.live || []).length === 0 ? (
            <div className="gs-empty">这一天还没有直播</div>
          ) : (
            (data?.live || []).slice(0, 8).map(item => (
              <div
                className="gs-live-item"
                key={item.id}
              >
                <div className="gs-live-meta">
                  <span>{item.time}</span>
                  {item.plate && item.plate !== '大盘' && item.plate !== '大盘直播' ? (
                    <span className="gs-live-plate">{item.plate}</span>
                  ) : null}
                  {item.pct ? <span className="gs-up">{item.pct}</span> : null}
                </div>
                <div className="text-13px leading-relaxed">{item.content}</div>
                {item.stocks && item.stocks.length > 0 ? (
                  <div className="gs-chip-row">
                    {item.stocks.slice(0, 6).map(name => (
                      <span
                        className="gs-chip"
                        key={name}
                      >
                        {name}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ))
          )}
        </Panel>

        <Panel
          hint={`${data?.ztPool?.length || 0} 只`}
          title="涨停梯队"
        >
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>板</th>
                <th>封单</th>
                <th>题材</th>
              </tr>
            </thead>
            <tbody>
              {(data?.ztPool || []).slice(0, 12).map(row => (
                <tr key={row.code}>
                  <td>
                    <div className="font-600">{row.name}</div>
                    <div className="text-11px text-[var(--gs-muted)]">{row.code}</div>
                  </td>
                  <td>{row.boardDays ?? '—'}</td>
                  <td>{row.sealYi != null ? `${row.sealYi}亿` : '—'}</td>
                  <td>{row.theme || row.industry || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel title="情绪与宽度">
          <table>
            <tbody>
              <tr>
                <th>封板率</th>
                <td>{fmt(s.sealRate as number | null)}%</td>
              </tr>
              <tr>
                <th>炸板率</th>
                <td>{fmt(s.brokenRate as number | null)}%</td>
              </tr>
              <tr>
                <th>昨涨停表现</th>
                <td>
                  <Pct value={s.yestRase as number | null} />
                </td>
              </tr>
              <tr>
                <th>情绪分</th>
                <td>{fmt(s.score as number | null)}</td>
              </tr>
              <tr>
                <th>均值 / 中位涨跌</th>
                <td>
                  <Pct value={b.avgPct} /> / <Pct value={b.medianPct} />
                </td>
              </tr>
              <tr>
                <th>近涨停区 / 近跌停区</th>
                <td>
                  {b.limitUpZone ?? '—'} / {b.limitDownZone ?? '—'}
                </td>
              </tr>
            </tbody>
          </table>
        </Panel>
      </div>

      <div className="gs-grid-2">
        <Panel title="板块涨幅">
          <table>
            <thead>
              <tr>
                <th>板块</th>
                <th>涨跌</th>
                <th>主力净额</th>
              </tr>
            </thead>
            <tbody>
              {(data?.sectors?.gainers || []).slice(0, 10).map(row => (
                <tr key={row.name}>
                  <td>{row.name}</td>
                  <td>
                    <Pct value={row.pct} />
                  </td>
                  <td>{row.inflowYi != null ? `${row.inflowYi}亿` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel title="主力流入">
          <table>
            <thead>
              <tr>
                <th>板块</th>
                <th>净流入</th>
                <th>涨跌</th>
              </tr>
            </thead>
            <tbody>
              {(data?.sectors?.inflow || []).slice(0, 10).map(row => (
                <tr key={row.name}>
                  <td>{row.name}</td>
                  <td className={row.inflowYi && row.inflowYi > 0 ? 'gs-up' : 'gs-down'}>
                    {row.inflowYi != null ? `${row.inflowYi}亿` : '—'}
                  </td>
                  <td>
                    <Pct value={row.pct} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>

      <div className="gs-grid">
        <Panel title="竞价强弱">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>竞价涨幅</th>
                <th>板块</th>
              </tr>
            </thead>
            <tbody>
              {(data?.auction || []).slice(0, 12).map(row => (
                <tr key={row.code}>
                  <td>{row.name}</td>
                  <td>
                    <Pct value={row.pct} />
                  </td>
                  <td>{row.sector || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel title="隔夜外盘">
          <table>
            <thead>
              <tr>
                <th>品种</th>
                <th>涨跌</th>
                <th>收盘</th>
              </tr>
            </thead>
            <tbody>
              {(data?.overnight || []).map(row => (
                <tr key={row.code}>
                  <td>{row.name}</td>
                  <td>
                    <Pct value={row.pct} />
                  </td>
                  <td>{fmt(row.close)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel title="北向五日">
          <table>
            <thead>
              <tr>
                <th>日期</th>
                <th>净买</th>
                <th>沪/深</th>
              </tr>
            </thead>
            <tbody>
              {(data?.northbound || []).map(row => (
                <tr key={row.date}>
                  <td>{row.date.slice(5)}</td>
                  <td className={(row.netYi || 0) >= 0 ? 'gs-up' : 'gs-down'}>
                    {row.netYi != null ? `${row.netYi}亿` : '—'}
                  </td>
                  <td>
                    {fmt(row.hgtYi)} / {fmt(row.sgtYi)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>

      <div className="gs-grid-2">
        <Panel
          hint={`${data?.cognitions?.length || 0}`}
          title="基础/迭代认知"
        >
          <table>
            <thead>
              <tr>
                <th>编号</th>
                <th>标题</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {(data?.cognitions || []).slice(0, 12).map(row => (
                <tr key={row.id}>
                  <td>{row.id}</td>
                  <td>{row.title}</td>
                  <td>{row.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel title="数据覆盖">
          <table>
            <thead>
              <tr>
                <th>表</th>
                <th>最新</th>
                <th>行数</th>
              </tr>
            </thead>
            <tbody>
              {(data?.freshness || []).map(row => (
                <tr key={row.table}>
                  <td>{row.table}</td>
                  <td>{row.latest || '—'}</td>
                  <td>{row.rows}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
    </div>
  );
};

export default Home;
