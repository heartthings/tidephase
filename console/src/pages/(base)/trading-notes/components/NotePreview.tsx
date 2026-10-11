import { Modal, Space, Tag, Typography } from 'antd';
import dayjs from 'dayjs';

import Markdown from '@/components/Markdown';
import { useMobile } from '@/hooks/common/mobile';
import type { NoteItem } from '@/service/api/notes';

const TAG_COLORS = [
  'magenta',
  'red',
  'volcano',
  'orange',
  'gold',
  'lime',
  'green',
  'cyan',
  'blue',
  'geekblue',
  'purple'
];
function getTagColor(text: string) {
  const sum = Array.from(text).reduce((acc, ch) => acc + ch.charCodeAt(0), 0);
  return TAG_COLORS[sum % TAG_COLORS.length];
}

interface NotePreviewProps {
  note?: NoteItem | null;
  onClose: () => void;
  visible: boolean;
}

const NotePreview = ({ note, onClose, visible }: NotePreviewProps) => {
  const isMobile = useMobile();
  return (
    <Modal
      footer={null}
      open={visible}
      title="笔记预览"
      width={isMobile ? '92%' : 700}
      onCancel={onClose}
    >
      {note ? (
        <Space
          className="w-full"
          direction="vertical"
        >
          <Space className="w-full justify-between">
            <span className="text-gray-500">{dayjs(note.createTime).format('YYYY-MM-DD HH:mm:ss')}</span>
            <Tag color="blue">{note.category}</Tag>
          </Space>
          <Typography.Text strong>{note.title || '-'}</Typography.Text>
          <Space
            direction="vertical"
            size={0}
          >
            {Array.isArray(note.tags) && note.tags.length > 0
              ? note.tags.map(t => (
                  <Tag
                    color={getTagColor(t)}
                    key={t}
                  >
                    {t}
                  </Tag>
                ))
              : null}
          </Space>
          <Typography.Paragraph>
            <Markdown value={note.content} />
          </Typography.Paragraph>
        </Space>
      ) : (
        <div className="text-center text-gray-400">暂无数据</div>
      )}
    </Modal>
  );
};

export default NotePreview;
