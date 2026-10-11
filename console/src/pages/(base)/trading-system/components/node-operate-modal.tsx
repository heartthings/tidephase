import { Form, Input, Modal, Spin } from 'antd';
import { useEffect } from 'react';

import type { NodeFormValues, NodeOperateType } from '../types';

import ColorPalettePicker from './color-palette-picker';

interface NodeOperateModalProps {
  confirmLoading?: boolean;
  formLoading?: boolean;
  initialValues?: NodeFormValues;
  onClose: () => void;
  onSubmit: (values: NodeFormValues) => void | Promise<void>;
  open: boolean;
  operateType: NodeOperateType;
}

const NodeOperateModal = ({
  confirmLoading,
  formLoading,
  initialValues,
  onClose,
  onSubmit,
  open,
  operateType
}: NodeOperateModalProps) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<NodeFormValues>();

  const titleMap: Record<NodeOperateType, string> = {
    add: t('page.tradingSystem.addRoot'),
    addChild: t('page.tradingSystem.addChild'),
    edit: t('page.tradingSystem.editNode')
  };

  useEffect(() => {
    if (open) {
      form.setFieldsValue(initialValues ?? { color: undefined, description: '', name: '' });
    }
  }, [form, initialValues, open]);

  const handleOk = async () => {
    const values = await form.validateFields();
    await onSubmit(values);
    form.resetFields();
  };

  const showFormSpinner = formLoading && operateType === 'edit';

  return (
    <Modal
      destroyOnClose
      confirmLoading={confirmLoading}
      okButtonProps={{ disabled: showFormSpinner }}
      okText={t('common.confirm')}
      open={open}
      title={titleMap[operateType]}
      width={480}
      onOk={handleOk}
      onCancel={() => {
        form.resetFields();
        onClose();
      }}
    >
      {showFormSpinner ? (
        <div className="flex-center py-48px">
          <Spin />
        </div>
      ) : (
        <Form
          form={form}
          layout="vertical"
          preserve={false}
        >
          <Form.Item
            label={t('page.tradingSystem.nodeName')}
            name="name"
            rules={[{ message: t('page.tradingSystem.nodeNameRequired'), required: true }]}
          >
            <Input
              showCount
              maxLength={32}
              placeholder={t('page.tradingSystem.nodeNamePlaceholder')}
            />
          </Form.Item>
          <Form.Item
            extra={t('page.tradingSystem.nodeDescriptionMarkdownHint')}
            label={t('page.tradingSystem.nodeDescription')}
            name="description"
          >
            <Input.TextArea
              autoSize={{ maxRows: 8, minRows: 3 }}
              placeholder={t('page.tradingSystem.nodeDescriptionPlaceholder')}
            />
          </Form.Item>
          <Form.Item
            extra={t('page.tradingSystem.nodeColorHint')}
            label={t('page.tradingSystem.nodeColor')}
            name="color"
          >
            <ColorPalettePicker />
          </Form.Item>
        </Form>
      )}
    </Modal>
  );
};

export default NodeOperateModal;
