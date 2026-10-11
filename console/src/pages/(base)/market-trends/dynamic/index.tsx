import { DatePicker, List } from 'antd';
import dayjs from 'dayjs';

import { themeColors } from '@/features/theme';
import { useMobile } from '@/hooks/common/mobile';
import { useMarketDynamics } from '@/service/hooks/useMarket';

const MarketDynamic = () => {
  const isMobile = useMobile();
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [keyword, setKeyword] = useState('');

  const { data, isLoading, refetch } = useMarketDynamics(date);
  const colors = useAppSelector(themeColors);
  const lastIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (data && data.length > 0) {
      lastIdRef.current = data[0].id;
    }
  }, [data]);

  useEffect(() => {
    // 页面加载时请求权限
    if (window.Notification && Notification.permission !== 'granted') {
      Notification.requestPermission();
    }

    const interval = setInterval(
      () => {
        const now = dayjs();
        const start = now.set('hour', 9).set('minute', 15).set('second', 0);
        const end = now.set('hour', 15).set('minute', 0).set('second', 0);

        if (now.isAfter(start) && now.isBefore(end)) {
          refetch().then(({ data: newData }) => {
            if (newData && newData.length > 0) {
              const latestItem = newData[0];
              if (latestItem.id !== lastIdRef.current) {
                // eslint-disable-next-line no-new
                new Notification('盘中动态有新消息', {
                  body: latestItem.comment,
                  tag: latestItem.id // 使用ID作为tag，防止重复通知
                });
                lastIdRef.current = latestItem.id;
              }
            }
          });
        }
      },
      2 * 60 * 1000
    ); // 2分钟

    return () => clearInterval(interval);
  }, [refetch]);

  const list = (data || []).filter(item => {
    const text = `${item.comment} ${item.stock}`.toLowerCase();
    return text.includes(keyword.toLowerCase());
  });

  function formatTime(ts: string) {
    const num = Number(ts);
    const ms = ts.length === 13 ? num : num * 1000;
    return dayjs(ms).format('YYYY-MM-DD HH:mm:ss');
  }

  function highlightNumbers(text: string) {
    const parts = text.split(/(\d+(?:\.\d+)?%?)/g);
    return (
      <ATypography.Paragraph ellipsis={{ expandable: true, rows: 3 }}>
        {parts.map((p, i) =>
          /^(\d+(?:\.\d+)?%?)$/.test(p) ? (
            <ATypography.Text
              key={i}
              style={{ color: colors.primary }}
            >
              {p}
            </ATypography.Text>
          ) : (
            <span key={i}>{p}</span>
          )
        )}
      </ATypography.Paragraph>
    );
  }

  function formatStocks(jsonStr: string) {
    let arr: any[] = [];
    try {
      arr = JSON.parse(jsonStr) || [];
    } catch {
      arr = [];
    }
    return (
      <ASpace
        className="w-full"
        direction="vertical"
        size={6}
      >
        {arr.map((it: [string, string, number]) => {
          const [code, name, pctRaw] = it;
          const pct = Number(pctRaw);
          const isUp = pct >= 0;
          const display = `${isUp ? '+' : ''}${pct.toFixed(2)}%`;
          return (
            <div
              className="w-full flex-y-center justify-between"
              key={`${code}-${name}`}
            >
              <ASpace size={8}>
                <ATypography.Text code>{code}</ATypography.Text>
                <ATypography.Text strong>{name}</ATypography.Text>
              </ASpace>
              <ATag
                className="min-w-72px px-8px text-center font-semibold"
                color={isUp ? 'error' : 'success'}
              >
                {display}
              </ATag>
            </div>
          );
        })}
      </ASpace>
    );
  }

  return (
    <ACard
      title="盘中动态"
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
                <div className="mb-2 text-xs text-gray-400">{formatTime(item.time)}</div>
                <div className="mb-2">{highlightNumbers(item.comment)}</div>
                {item.stock && item.stock !== '[]' && (
                  <div className="rounded bg-gray-50 p-2">{formatStocks(item.stock)}</div>
                )}
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
              render: (v: string) => formatTime(v),
              title: '事件时间',
              width: 160
            },
            {
              dataIndex: 'comment',
              key: 'comment',
              render: (v: string) => highlightNumbers(v),
              title: '事件内容'
            },
            {
              dataIndex: 'stock',
              key: 'stock',
              render: (v: string) => formatStocks(v),
              title: '相关个股',
              width: 260
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

export default MarketDynamic;
