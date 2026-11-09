import { DatePicker, Input } from 'antd';
import dayjs from 'dayjs';
import { useMemo, useState } from 'react';

import { Panel } from '@/features/desk/Panel';
import '@/features/desk/desk.css';
import { useConsoleDesk } from '@/service/hooks/useDesk';

const MarketRadar = () => {
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [keyword, setKeyword] = useState('');
  const { data, isLoading } = useConsoleDesk(date);

  const list = useMemo(() => {
    const rows = data?.live || [];
    const q = keyword.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(item => `${item.plate} ${item.content} ${(item.stocks || []).join(' ')}`.toLowerCase().includes(q));
  }, [data, keyword]);

  return (
    <div className="gs-desk space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="m-0 text-24px">大盘直播</h1>
          <p className="m-0 mt-1 text-13px text-[var(--gs-muted)]">开盘啦 ZhiBoContent，按时间倒序。有板块就亮板块，数字在飞书推送里另做高亮。</p>
        </div>
        <div className="flex gap-2">
          <DatePicker
            allowClear={false}
            value={dayjs(date)}
            onChange={d => setDate(d?.format('YYYY-MM-DD') || dayjs().format('YYYY-MM-DD'))}
          />
          <Input
            allowClear
            placeholder="搜板块 / 内容 / 个股"
            style={{ width: 220 }}
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
          />
        </div>
      </div>

      <Panel
        hint={isLoading ? '加载中' : `${list.length} 条`}
        title={date}
      >
        {list.length === 0 ? (
          <div className="gs-empty">这一天还没有直播</div>
        ) : (
          list.map(item => (
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
              <div className="whitespace-pre-wrap text-13px leading-relaxed">{item.content}</div>
              {item.stocks && item.stocks.length > 0 ? (
                <div className="gs-chip-row">
                  {item.stocks.map(name => (
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
    </div>
  );
};

export default MarketRadar;
