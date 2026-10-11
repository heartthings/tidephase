import { Icon } from '@iconify/react';
import { useQuery } from '@tanstack/react-query';
import { Card, Skeleton } from 'antd';
import dayjs from 'dayjs';
import { useState } from 'react';

import { fetchHomeSummary } from '@/service/api/home';

import HeaderBanner from './modules/HeaderBanner';
import ImageEditorModal from './modules/ImageEditorModal';

const Home = () => {
  const [imageEditorSrc, setImageEditorSrc] = useState<string | null>(null);

  const { data: summary, isLoading } = useQuery({
    queryFn: fetchHomeSummary,
    queryKey: ['home', 'summary']
  });

  const handleContentClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    if (target.tagName === 'IMG') {
      const src = (target as HTMLImageElement).src;
      if (src) {
        setImageEditorSrc(src);
      }
    }
  };

  const renderContent = () => {
    if (isLoading) {
      return (
        <Skeleton
          active
          paragraph={{ rows: 3 }}
        />
      );
    }
    if (summary?.tradingPlanContent) {
      return (
        <div
          className="prose max-w-none text-gray-600 [&_p]:mb-2 [&_img]:h-auto [&_img]:max-w-full [&_img]:cursor-zoom-in [&_ol]:list-decimal [&_ul]:list-disc [&_ol]:pl-5 [&_ul]:pl-5"
          dangerouslySetInnerHTML={{ __html: summary.tradingPlanContent }}
          onClick={handleContentClick}
        />
      );
    }
    return (
      <div className="flex flex-col items-center justify-center py-12 text-gray-400">
        <Icon
          className="mb-2 text-4xl opacity-20"
          icon="mdi:notebook-outline"
        />
        <span>暂无置顶的交易计划</span>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <HeaderBanner />

      {/* Trading Plan Section */}
      <Card
        bordered={false}
        className="overflow-hidden border-0 rounded-2xl shadow-sm transition-shadow hover:shadow-md"
        styles={{
          body: { padding: '20px 24px' },
          header: {
            background: 'linear-gradient(to right, #f8faff, #ffffff)',
            borderBottom: '1px solid #f0f0f0',
            padding: '16px 24px'
          }
        }}
        title={
          <div className="flex items-center gap-2">
            <div className="size-8 flex items-center justify-center rounded-lg bg-blue-50 text-blue-500">
              <Icon
                className="text-xl"
                icon="mdi:pin"
              />
            </div>
            <span className="text-base text-gray-800 font-medium">最新交易计划</span>
            {summary?.updatedTime && (
              <div className="ml-auto flex items-center gap-1 rounded-full bg-gray-50 px-3 py-1 text-xs text-gray-400">
                <Icon icon="mdi:clock-outline" />
                <span>更新于 {dayjs(summary.updatedTime).format('MM-DD HH:mm')}</span>
              </div>
            )}
          </div>
        }
      >
        <div className="min-h-100px">{renderContent()}</div>
      </Card>

      <ImageEditorModal
        src={imageEditorSrc || ''}
        visible={Boolean(imageEditorSrc)}
        onClose={() => setImageEditorSrc(null)}
      />
    </div>
  );
};

export default Home;
