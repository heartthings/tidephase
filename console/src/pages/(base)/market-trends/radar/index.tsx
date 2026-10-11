import { DatePicker, List } from 'antd';
import dayjs from 'dayjs';

import { themeColors } from '@/features/theme';
import { useMobile } from '@/hooks/common/mobile';
import { useMarketRadars } from '@/service/hooks/useMarket';

const MarketRadar = () => {
  const isMobile = useMobile();
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [keyword, setKeyword] = useState('');

  const { data, isLoading } = useMarketRadars(date);
  const colors = useAppSelector(themeColors);

  const list = (data || []).filter(item => {
    const text = `${item.stockName} ${item.lbStatus} ${item.status} ${item.content}`.toLowerCase();
    return text.includes(keyword.toLowerCase());
  });

  function highlightContent(text: string) {
    const parts = text.split(/(减少|\d+(?:\.\d+)?%?)/g);
    return (
      <div className="whitespace-pre-wrap">
        {parts.map((p, i) => {
          if (p === '减少') {
            return (
              <ATypography.Text
                key={i}
                type="success"
              >
                {p}
              </ATypography.Text>
            );
          }
          if (/^(\d+(?:\.\d+)?%?)$/.test(p)) {
            return (
              <ATypography.Text
                key={i}
                style={{ color: colors.primary }}
              >
                {p}
              </ATypography.Text>
            );
          }
          return <span key={i}>{p}</span>;
        })}
      </div>
    );
  }

  return (
    <ACard
      title="市场雷达"
      extra={
        <ASpace
          align={isMobile ? 'end' : 'center'}
          direction={isMobile ? 'vertical' : 'horizontal'}
        >
          <DatePicker
            value={dayjs(date)}
            onChange={d => setDate(d?.format('YYYY-MM-DD') || dayjs().format('YYYY-MM-DD'))}
          />
          <AInput
            allowClear
            placeholder="搜索关键词"
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
          />
        </ASpace>
      }
    >
      {isMobile ? (
        <List
          dataSource={list}
          loading={isLoading}
          renderItem={item => (
            <List.Item>
              <ACard
                size="small"
                style={{ width: '100%' }}
              >
                <div className="mb-2 text-xs text-gray-400">{item.time}</div>
                <div className="mb-2 flex items-center justify-between">
                  <span className="font-bold">
                    {item.stockName} <span className="text-gray-500 font-normal">({item.lbStatus})</span>
                  </span>
                  <ATag>{item.status}</ATag>
                </div>
                <div>{highlightContent(item.content)}</div>
              </ACard>
            </List.Item>
          )}
        />
      ) : (
        <ATable
          dataSource={list}
          loading={isLoading}
          pagination={false}
          rowKey="id"
          size="small"
          tableLayout="fixed"
          columns={[
            {
              align: 'center',
              dataIndex: 'time',
              key: 'time',
              title: '事件时间',
              width: 160
            },
            {
              key: 'stockName',
              render: (_: any, r: any) => `${r.stockName}（${r.lbStatus}）`,
              title: '股票名称'
            },
            {
              dataIndex: 'status',
              key: 'status',
              title: '事件状态',
              width: 140
            },
            {
              dataIndex: 'content',
              key: 'content',
              render: (v: string) => highlightContent(v),
              title: '事件内容'
            }
          ]}
          onRow={(_, index) => ({
            style: Number(index ?? 0) % 2 === 1 ? { backgroundColor: toRGBA(colors.primary, 0.06) } : undefined
          })}
        />
      )}
    </ACard>
  );
};

function toRGBA(hex: string, alpha = 1) {
  const clean = hex.replace('#', '');
  const full =
    clean.length === 3
      ? clean
          .split('')
          .map(c => c + c)
          .join('')
      : clean;
  const r = Number.parseInt(full.substring(0, 2), 16);
  const g = Number.parseInt(full.substring(2, 4), 16);
  const b = Number.parseInt(full.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export default MarketRadar;
