import { Icon } from '@iconify/react';
import { useQuery } from '@tanstack/react-query';
import {
  Badge,
  Button,
  Card,
  DatePicker,
  Input,
  List,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message
} from 'antd';
import dayjs from 'dayjs';
import { useEffect, useState } from 'react';

import { useMobile } from '@/hooks/common/mobile';
import { buildTodayNotesJson, coachCompletionStream } from '@/service/api/coach';
import type { NoteCategory } from '@/service/api/note';
import { fetchEnabledNoteCategories, fetchNoteMonthCount } from '@/service/api/note';
import type { NoteItem } from '@/service/api/notes';
import { useNoteMutations, useNotes } from '@/service/hooks/useNotes';

import CoachSettings from './components/CoachSettings';
import NoteAnalysis from './components/NoteAnalysis';
import NoteModal from './components/NoteModal';
import NotePreview from './components/NotePreview';

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

const TradingNotes = () => {
  const isMobile = useMobile();
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'));
  const [keyword, setKeyword] = useState('');
  const [categoryId, setCategoryId] = useState<string | undefined>(undefined);

  // Modal states
  const [modalVisible, setModalVisible] = useState(false);
  const [editingNote, setEditingNote] = useState<NoteItem | null>(null);

  // Preview state
  const [previewVisible, setPreviewVisible] = useState(false);
  const [previewNote, setPreviewNote] = useState<NoteItem | null>(null);

  // Analysis state
  const [analysisVisible, setAnalysisVisible] = useState(false);
  const [analysisContent, setAnalysisContent] = useState('');

  // Data hooks
  const { data: notes, isLoading } = useNotes({ categoryId, date, keyword });
  const { add, delete: remove, top, update } = useNoteMutations();
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [coachSettingsVisible, setCoachSettingsVisible] = useState(false);
  const { data: categories } = useQuery({
    queryFn: fetchEnabledNoteCategories,
    queryKey: ['note', 'enabledCategories'],
    staleTime: 60_000
  });

  const [viewDate, setViewDate] = useState(dayjs(date));
  const currentMonth = viewDate.format('YYYY-MM');

  useEffect(() => {
    setViewDate(dayjs(date));
  }, [date]);

  const { data: monthlyCounts } = useQuery({
    queryFn: () => fetchNoteMonthCount(currentMonth),
    queryKey: ['note', 'month-counts', currentMonth],
    staleTime: 10 * 1000
  });

  const noteCountMap = useMemo(() => {
    const map = new Map<string, number>();
    if (monthlyCounts) {
      monthlyCounts.forEach(item => {
        const dateStr = item.date.substring(0, 10);
        map.set(dateStr, item.count);
      });
    }
    return map;
  }, [monthlyCounts]);

  const cellRender = (current: any, info: any) => {
    if (info.type !== 'date') return info.originNode;
    const dateStr = dayjs(current).format('YYYY-MM-DD');
    const count = noteCountMap.get(dateStr) || 0;

    if (count > 0) {
      return (
        <div style={{ position: 'relative' }}>
          {info.originNode}
          <Badge
            count={count}
            size="small"
            style={{
              position: 'absolute',
              right: 0,
              top: 0,
              transform: 'scale(0.8) translate(30%, -30%)',
              zIndex: 9
            }}
          />
        </div>
      );
    }
    return info.originNode;
  };

  const categoryColorMap = Object.fromEntries(
    (categories || ([] as NoteCategory[])).map(c => [c.id, c.color || 'blue'])
  ) as Record<string, string>;
  const categoryNameMap = Object.fromEntries((categories || ([] as NoteCategory[])).map(c => [c.id, c.name])) as Record<
    string,
    string
  >;

  const handleAdd = () => {
    setEditingNote(null);
    setModalVisible(true);
  };

  const handleEdit = (note: NoteItem) => {
    setEditingNote(note);
    setModalVisible(true);
  };

  const handlePreview = (note: NoteItem) => {
    setPreviewNote(note);
    setPreviewVisible(true);
  };

  const handleDelete = (id: string) => {
    remove.mutate(id, {
      onSuccess: () => message.success('删除成功')
    });
  };

  const handleTop = (id: string) => {
    top.mutate(id, {
      onSuccess: () => message.success('置顶成功')
    });
  };

  const handleSubmit = (values: { categoryId: string; content: string; tags?: string[]; title?: string }) => {
    if (editingNote) {
      update.mutate(
        { data: values, id: editingNote.id },
        {
          onSuccess: () => {
            message.success('更新成功');
            setModalVisible(false);
          }
        }
      );
    } else {
      const payload = {
        categoryId: values.categoryId,
        content: values.content,
        tags: values.tags ?? [],
        title: values.title ?? ''
      };
      add.mutate(payload, {
        onSuccess: () => {
          message.success('添加成功');
          setModalVisible(false);
        }
      });
    }
  };

  const handleAnalysis = async () => {
    setAnalysisVisible(true);
    setAnalysisContent('');
    setIsAnalyzing(true);
    try {
      const notesJson = await buildTodayNotesJson();
      await coachCompletionStream(notesJson, chunk => {
        setAnalysisContent(prev => (prev ? `${prev}${chunk}` : chunk));
      });
    } finally {
      setIsAnalyzing(false);
    }
  };

  // Columns for desktop
  const columns = [
    {
      dataIndex: 'createTime',
      key: 'createTime',
      render: (time: number) => dayjs(time).format('YYYY-MM-DD HH:mm:ss'),
      title: '时间',
      width: 180
    },
    {
      dataIndex: 'categoryId',
      key: 'category',
      render: (id: string) => <Tag color={categoryColorMap[id] || 'blue'}>{categoryNameMap[id] || '-'}</Tag>,
      title: '分类',
      width: 120
    },
    {
      dataIndex: 'title',
      key: 'title',
      render: (text: string) => <Typography.Text strong>{text || '-'}</Typography.Text>,
      title: '标题',
      width: 200
    },
    {
      dataIndex: 'content',
      key: 'content',
      render: (text: string, record: NoteItem) => {
        const plain = text.replace(/<[^>]+>/g, '');
        const short = plain.length > 88 ? `${plain.slice(0, 88)}...` : plain;
        return (
          <Space>
            <Typography.Text>{short}</Typography.Text>
            <Button
              size="small"
              type="link"
              onClick={() => handlePreview(record)}
            >
              预览
            </Button>
          </Space>
        );
      },
      title: '内容'
    },
    {
      dataIndex: 'tags',
      key: 'tags',
      render: (tags: string[]) => (
        <Space
          direction="vertical"
          size={0}
        >
          {Array.isArray(tags) && tags.length > 0 ? (
            tags.map(t => (
              <Tag
                color={getTagColor(t)}
                key={t}
              >
                {t}
              </Tag>
            ))
          ) : (
            <span className="text-gray-400">-</span>
          )}
        </Space>
      ),
      title: '标签',
      width: 160
    },
    {
      key: 'action',
      render: (_: any, record: NoteItem) => (
        <Space>
          <Button
            size="small"
            type="link"
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确定删除吗？"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button
              danger
              size="small"
              type="link"
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
      title: '操作',
      width: 180
    }
  ];

  const getColumns = () => {
    if (!categories) return columns;
    const tradingPlanCategory = categories.find(c => c.name === '交易计划');
    if (!tradingPlanCategory) return columns;

    return columns.map(col => {
      if (col.key !== 'action') return col;
      return {
        ...col,
        render: (_: any, record: NoteItem) => (
          <Space>
            <Space>
              <Button
                size="small"
                type="link"
                onClick={() => handleEdit(record)}
              >
                编辑
              </Button>
              <Popconfirm
                title="确定删除吗？"
                onConfirm={() => handleDelete(record.id)}
              >
                <Button
                  danger
                  size="small"
                  type="link"
                >
                  删除
                </Button>
              </Popconfirm>
            </Space>
            {record.categoryId === tradingPlanCategory.id && (
              <Button
                size="small"
                type="link"
                onClick={() => handleTop(record.id)}
              >
                置顶计划
              </Button>
            )}
          </Space>
        )
      };
    });
  };

  return (
    <Card
      title="操盘笔记"
      extra={
        isMobile ? (
          <Space
            align="start"
            direction="vertical"
            style={{ width: '100%' }}
          >
            <Space wrap>
              <Button
                icon={<Icon icon="mdi:robot" />}
                onClick={handleAnalysis}
              >
                投资教练
              </Button>
              <Button
                icon={<Icon icon="mdi:cog" />}
                onClick={() => setCoachSettingsVisible(true)}
              >
                设置密钥
              </Button>
              <Button
                icon={<Icon icon="mdi:plus" />}
                type="primary"
                onClick={handleAdd}
              >
                记一笔
              </Button>
            </Space>
            <Space
              direction="vertical"
              style={{ width: '100%' }}
            >
              <DatePicker
                allowClear={false}
                cellRender={cellRender}
                pickerValue={viewDate}
                value={dayjs(date)}
                onChange={d => setDate(d?.format('YYYY-MM-DD') || dayjs().format('YYYY-MM-DD'))}
                onPanelChange={val => setViewDate(val)}
              />
              <Select
                allowClear
                options={(categories || []).map(c => ({ label: c.name, value: c.id }))}
                placeholder="按分类筛选"
                style={{ width: '100%' }}
                value={categoryId}
                onChange={setCategoryId}
              />
              <Input.Search
                allowClear
                placeholder="搜索笔记"
                style={{ width: '100%' }}
                onSearch={setKeyword}
              />
            </Space>
          </Space>
        ) : (
          <Space
            align="center"
            direction="horizontal"
          >
            <Space>
              <DatePicker
                allowClear={false}
                cellRender={cellRender}
                pickerValue={viewDate}
                value={dayjs(date)}
                onChange={d => setDate(d?.format('YYYY-MM-DD') || dayjs().format('YYYY-MM-DD'))}
                onPanelChange={val => setViewDate(val)}
              />
              <Select
                allowClear
                options={(categories || []).map(c => ({ label: c.name, value: c.id }))}
                placeholder="按分类筛选"
                style={{ width: 180 }}
                value={categoryId}
                onChange={setCategoryId}
              />
              <Input.Search
                allowClear
                placeholder="搜索笔记"
                style={{ width: 200 }}
                onSearch={setKeyword}
              />
            </Space>
            <Button
              icon={<Icon icon="mdi:robot" />}
              onClick={handleAnalysis}
            >
              投资教练
            </Button>
            <Button
              icon={<Icon icon="mdi:cog" />}
              onClick={() => setCoachSettingsVisible(true)}
            >
              设置密钥
            </Button>
            <Button
              icon={<Icon icon="mdi:plus" />}
              type="primary"
              onClick={handleAdd}
            >
              记一笔
            </Button>
          </Space>
        )
      }
    >
      {isMobile ? (
        <List
          dataSource={notes}
          loading={isLoading}
          renderItem={item => (
            <List.Item>
              <Card
                size="small"
                style={{ width: '100%' }}
                extra={
                  <Space>
                    <Icon
                      className="cursor-pointer text-gray-600"
                      icon="mdi:eye-outline"
                      onClick={() => handlePreview(item)}
                    />
                    <Icon
                      className="cursor-pointer text-blue-500"
                      icon="mdi:pencil"
                      onClick={() => handleEdit(item)}
                    />
                    <Popconfirm
                      title="确定删除吗？"
                      onConfirm={() => handleDelete(item.id)}
                    >
                      <Icon
                        className="cursor-pointer text-red-500"
                        icon="mdi:delete"
                      />
                    </Popconfirm>
                    {categories?.find(c => c.name === '交易计划')?.id === item.categoryId && (
                      <Icon
                        className="cursor-pointer text-amber-500"
                        icon="mdi:pin"
                        onClick={() => handleTop(item.id)}
                      />
                    )}
                  </Space>
                }
                title={
                  <Space>
                    <Tag color={categoryColorMap[item.categoryId || ''] || 'blue'}>
                      {item.categoryId ? categoryNameMap[item.categoryId] || '-' : '-'}
                    </Tag>
                    <span className="text-xs text-gray-400">{dayjs(item.createTime).format('HH:mm')}</span>
                  </Space>
                }
              >
                <Typography.Text strong>{item.title || '-'}</Typography.Text>
                <Space
                  className="mt-1"
                  direction="vertical"
                  size={0}
                >
                  {Array.isArray(item.tags) && item.tags.length > 0
                    ? item.tags.map(tag => (
                        <Tag
                          color={getTagColor(tag)}
                          key={tag}
                        >
                          {tag}
                        </Tag>
                      ))
                    : null}
                </Space>
                <Typography.Paragraph>
                  {(() => {
                    const plain = item.content.replace(/<[^>]+>/g, '');
                    return plain.length > 88 ? `${plain.slice(0, 88)}...` : plain;
                  })()}
                </Typography.Paragraph>
              </Card>
            </List.Item>
          )}
        />
      ) : (
        <Table
          columns={getColumns()}
          dataSource={notes}
          loading={isLoading}
          pagination={false}
          rowKey="id"
        />
      )}

      <NoteModal
        categories={categories}
        editingNote={editingNote}
        loading={add.isPending || update.isPending}
        visible={modalVisible}
        onCancel={() => setModalVisible(false)}
        onSubmit={handleSubmit}
      />
      <CoachSettings
        visible={coachSettingsVisible}
        onClose={() => setCoachSettingsVisible(false)}
      />

      <NotePreview
        note={previewNote}
        visible={previewVisible}
        onClose={() => setPreviewVisible(false)}
      />

      <NoteAnalysis
        content={analysisContent}
        loading={isAnalyzing}
        visible={analysisVisible}
        onClose={() => setAnalysisVisible(false)}
      />
    </Card>
  );
};

export default TradingNotes;
