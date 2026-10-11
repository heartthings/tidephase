import { Icon } from '@iconify/react';
import { Button } from 'antd';
import { useEffect, useState } from 'react';
import FilerobotImageEditor from 'react-filerobot-image-editor';

interface Props {
  onClose: () => void;
  src: string;
  visible: boolean;
}

const ImageEditorModal = ({ onClose, src, visible }: Props) => {
  const [isEditing, setIsEditing] = useState(false);

  useEffect(() => {
    if (!visible) {
      setIsEditing(false);
    }
  }, [visible]);

  if (!visible || !src) return null;

  if (!isEditing) {
    return (
      <div
        style={{
          alignItems: 'center',
          background: 'rgba(0,0,0,0.85)',
          bottom: 0,
          display: 'flex',
          justifyContent: 'center',
          left: 0,
          position: 'fixed',
          right: 0,
          top: 0,
          zIndex: 2000
        }}
        onClick={onClose}
      >
        <div
          style={{ maxHeight: '90vh', maxWidth: '90vw', position: 'relative' }}
          onClick={e => e.stopPropagation()}
        >
          <img
            alt="preview"
            src={src}
            style={{
              maxHeight: '90vh',
              maxWidth: '90vw',
              objectFit: 'contain'
            }}
          />
          <div className="absolute left-1/2 flex gap-4 -bottom-12 -translate-x-1/2">
            <Button
              icon={<Icon icon="mdi:pencil" />}
              type="primary"
              onClick={() => setIsEditing(true)}
            >
              编辑图片
            </Button>
          </div>
          <button
            className="absolute p-2 text-white -right-12 -top-12 hover:text-gray-300"
            onClick={onClose}
          >
            <Icon
              height={32}
              icon="mdi:close"
              width={32}
            />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        background: 'rgba(0,0,0,0.8)',
        bottom: 0,
        left: 0,
        position: 'fixed',
        right: 0,
        top: 0,
        zIndex: 2000
      }}
    >
      <FilerobotImageEditor
        previewPixelRatio={window.devicePixelRatio}
        savingPixelRatio={4}
        source={src}
        annotationsCommon={{
          fill: '#ff0000'
        }}
        translations={{
          adjust: '调整',
          annotate: '标注',
          back: '返回',
          cancel: '取消',
          close: '关闭',
          crop: '裁剪',
          filters: '滤镜',
          finetune: '微调',
          flip: '翻转',
          load: '加载',
          loading: '加载中...',
          name: '名称',
          original: '原始',
          redo: '重做',
          reset: '重置',
          resize: '调整大小',
          rotate: '旋转',
          save: '保存',
          saveAs: '另存为',
          undo: '撤销',
          watermark: '水印'
        }}
        onClose={onClose}
        onSave={(editedImageObject, designState) => {
          console.log('saved', editedImageObject, designState);
          // Auto download the edited image
          if (editedImageObject.imageBase64) {
            const link = document.createElement('a');
            link.download = editedImageObject.fullName || 'edited-image.png';
            link.href = editedImageObject.imageBase64;
            link.click();
          }
        }}
      />
    </div>
  );
};

export default ImageEditorModal;
