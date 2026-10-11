import { Form, Input, Modal } from 'antd';
import { useEffect } from 'react';

interface CoachSettingsProps {
  onClose: () => void;
  visible: boolean;
}

const CoachSettings = ({ onClose, visible }: CoachSettingsProps) => {
  const [form] = Form.useForm();

  useEffect(() => {
    if (visible) {
      const val = localStorage.getItem('DASHSCOPE_API_KEY') || '';
      form.setFieldsValue({ apiKey: val });
    }
  }, [visible, form]);

  const handleOk = async () => {
    const values = await form.validateFields();
    localStorage.setItem('DASHSCOPE_API_KEY', values.apiKey || '');
    onClose();
  };

  return (
    <Modal
      open={visible}
      title="投资教练密钥设置"
      onCancel={onClose}
      onOk={handleOk}
    >
      <Form
        form={form}
        layout="vertical"
      >
        <Form.Item
          label="DASHSCOPE_API_KEY"
          name="apiKey"
          rules={[{ message: '请输入密钥', required: true }]}
        >
          <Input placeholder="sk-开头的密钥" />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default CoachSettings;
