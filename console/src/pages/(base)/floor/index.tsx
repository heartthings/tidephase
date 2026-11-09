import { DatePicker, Tabs } from 'antd';
import dayjs from 'dayjs';
import { useState } from 'react';

import { Panel } from '@/features/desk/Panel';
import { Pct } from '@/features/desk/Pct';
import '@/features/desk/desk.css';
import { useConsoleDesk } from '@/service/hooks/useDesk';
import type { DeskPoolItem } from '@/service/api/desk';

function PoolTable({ rows }: { rows: DeskPoolItem[] }) {
  if (!rows.length) return <div className="gs-empty">这一天还没有数</div>;
  return (
    <table>
      <thead>
        <tr>
          <th>名称</th>
          <th>涨跌</th>
          <th>板</th>
          <th>封单</th>
          <th>成交</th>
          <th>换手</th>
          <th>首封</th>
          <th>题材 / 原因</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(row => (
          <tr key={row.code}>
            <td>
              <div className="font-600">{row.name}</div>
              <div className="text-11px text-[var(--gs-muted)]">{row.code}</div>
            </td>
            <td>
              <Pct value={row.pct} />
            </td>
            <td>{row.boardDays ?? '—'}</td>
            <td>{row.sealYi != null ? `${row.sealYi}亿` : '—'}</td>
            <td>{row.amountYi != null ? `${row.amountYi}亿` : '—'}</td>
            <td>{row.turnover != null ? `${row.turnover}%` : '—'}</td>
            <td>{row.firstSeal || '—'}</td>
            <td>
              <div>{row.theme || row.industry || '—'}</div>
              <div className="text-11px text-[var(--gs-muted)]">{row.reason || ''}</div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const Floor = () => {
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const { data, isLoading } = useConsoleDesk(date);
  const s = data?.sentiment || {};

  return (
    <div className="gs-desk space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="m-0 text-24px">涨跌停与情绪</h1>
          <p className="m-0 mt-1 text-13px text-[var(--gs-muted)]">涨停池、炸板池、跌停池，加上当天情绪刻度。</p>
        </div>
        <DatePicker
          allowClear={false}
          value={dayjs(date)}
          onChange={d => setDate(d?.format('YYYY-MM-DD') || dayjs().format('YYYY-MM-DD'))}
        />
      </div>

      <div className="gs-grid" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
        <Panel title="涨停">
          <div className="text-28px font-600 gs-up">{s.limitUp ?? '—'}</div>
        </Panel>
        <Panel title="跌停">
          <div className="text-28px font-600 gs-down">{s.limitDown ?? '—'}</div>
        </Panel>
        <Panel title="炸板率">
          <div className="text-28px font-600">{s.brokenRate != null ? `${Number(s.brokenRate).toFixed(1)}%` : '—'}</div>
        </Panel>
        <Panel title="最高连板">
          <div className="text-28px font-600">{s.maxBoard ?? '—'}</div>
        </Panel>
      </div>

      <Panel title="池子">
        {isLoading && !data ? (
          <div className="gs-empty">加载中…</div>
        ) : (
          <Tabs
            items={[
              { key: 'zt', label: `涨停 ${data?.ztPool?.length || 0}`, children: <PoolTable rows={data?.ztPool || []} /> },
              { key: 'zb', label: `炸板 ${data?.zbPool?.length || 0}`, children: <PoolTable rows={data?.zbPool || []} /> },
              { key: 'dt', label: `跌停 ${data?.dtPool?.length || 0}`, children: <PoolTable rows={data?.dtPool || []} /> }
            ]}
          />
        )}
      </Panel>

      <div className="gs-grid-2">
        <Panel title="领涨">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>涨跌</th>
                <th>成交</th>
              </tr>
            </thead>
            <tbody>
              {(data?.leaders?.up || []).map(row => (
                <tr key={row.code}>
                  <td>{row.name}</td>
                  <td>
                    <Pct value={row.pct} />
                  </td>
                  <td>{row.amountYi != null ? `${row.amountYi}亿` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel title="领跌">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>涨跌</th>
                <th>成交</th>
              </tr>
            </thead>
            <tbody>
              {(data?.leaders?.down || []).map(row => (
                <tr key={row.code}>
                  <td>{row.name}</td>
                  <td>
                    <Pct value={row.pct} />
                  </td>
                  <td>{row.amountYi != null ? `${row.amountYi}亿` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
    </div>
  );
};

export default Floor;
