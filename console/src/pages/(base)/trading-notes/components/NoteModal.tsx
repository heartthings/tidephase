import { Form, Input, Modal, Select, Tag } from 'antd';
import { useEffect } from 'react';

import { useMobile } from '@/hooks/common/mobile';
import type { NoteCategory } from '@/service/api/note';
import type { NoteItem } from '@/service/api/notes';

import RichTextEditor from './RichTextEditor';

interface NoteModalProps {
  categories?: NoteCategory[];
  editingNote?: NoteItem | null;
  loading?: boolean;
  onCancel: () => void;
  onSubmit: (data: { categoryId: string; content: string; tags?: string[]; title?: string }) => void;
  visible: boolean;
}

const CATEGORIES: Array<{ label: React.ReactNode; value: string }> = [
  { label: '市场复盘', value: '复盘' },
  { label: '交易计划', value: '计划' },
  { label: '情绪记录', value: '情绪' },
  { label: '突发消息', value: '消息' },
  { label: '其他', value: '其他' }
];

const NoteModal = ({ categories, editingNote, loading, onCancel, onSubmit, visible }: NoteModalProps) => {
  const [form] = Form.useForm();
  const isMobile = useMobile();

  useEffect(() => {
    if (visible) {
      if (editingNote) {
        form.setFieldsValue({
          categoryId: editingNote.categoryId,
          content: editingNote.content,
          tags: editingNote.tags,
          title: editingNote.title
        });
      } else {
        form.resetFields();
        form.setFieldsValue({ categoryId: undefined, tags: [] });
      }
    }
  }, [visible, editingNote, form]);

  const categoryOptions =
    categories && categories.length > 0
      ? categories.map(c => ({
          label: (
            <Tag
              color={c.color || 'blue'}
              key={c.id}
            >
              {c.name}
            </Tag>
          ),
          value: c.id
        }))
      : CATEGORIES;

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      onSubmit(values);
    } catch {
      // ignore
    }
  };

  return (
    <Modal
      confirmLoading={loading}
      open={visible}
      title={editingNote ? '编辑笔记' : '添加笔记'}
      width={isMobile ? '92%' : 800}
      onCancel={onCancel}
      onOk={handleOk}
    >
      <Form
        form={form}
        layout="vertical"
      >
        <Form.Item
          label="标题"
          name="title"
          tooltip="若留空，将自动取内容前 8 个字作为标题"
        >
          <Input placeholder="请输入标题（可留空）" />
        </Form.Item>
        <Form.Item
          label="笔记分类"
          name="categoryId"
          rules={[{ message: '请选择分类', required: true }]}
        >
          <Select options={categoryOptions} />
        </Form.Item>
        <Form.Item
          label="标签"
          name="tags"
          tooltip="输入内容后按回车添加标签，标签可删除"
        >
          <Select
            mode="tags"
            placeholder="输入标签后回车添加"
          />
        </Form.Item>
        <Form.Item
          label="笔记内容"
          name="content"
          rules={[{ message: '请输入内容', required: true }]}
          valuePropName="value"
        >
          <RichTextEditor />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default NoteModal;
