import { Modal, Typography } from 'antd';

import Markdown from '@/components/Markdown';
import { useMobile } from '@/hooks/common/mobile';

interface NoteAnalysisProps {
  content: string;
  loading: boolean;
  onClose: () => void;
  visible: boolean;
}

const NoteAnalysis = ({ content, loading, onClose, visible }: NoteAnalysisProps) => {
  const isMobile = useMobile();
  return (
    <Modal
      footer={null}
      loading={loading}
      open={visible}
      title="AI 操盘分析"
      width={isMobile ? '92%' : 800}
      onCancel={onClose}
    >
      <div className="min-h-200px">
        {loading ? (
          <div className="py-20 text-center text-gray-500">正在分析您的操盘数据，请稍候...</div>
        ) : (
          <Typography>
            <Markdown value={content} />
          </Typography>
        )}
      </div>
    </Modal>
  );
};

export default NoteAnalysis;
