import { Icon } from '@iconify/react';
import Image from '@tiptap/extension-image';
import Link from '@tiptap/extension-link';
import Underline from '@tiptap/extension-underline';
import { EditorContent, ReactNodeViewRenderer, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Button, Input, Modal, Space } from 'antd';
import { useEffect, useRef, useState } from 'react';

import ResizableImage from './ResizableImage';

interface Props {
  onChange?: (html: string) => void;
  value?: string;
}

const RichTextEditor = ({ onChange, value = '' }: Props) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const lastHtmlRef = useRef(value);
  const prevValueRef = useRef(value);

  const editor = useEditor({
    content: value,
    editorProps: {
      attributes: {
        class:
          'min-h-200px rounded border border-gray-200 px-3 py-2 outline-none focus:border-blue-400 [&_img]:max-w-full [&_img]:h-auto'
      }
    },
    extensions: [
      StarterKit,
      Underline,
      Image.extend({
        addAttributes() {
          return {
            ...this.parent?.(),
            width: {
              default: null
            }
          };
        },
        addNodeView() {
          return ReactNodeViewRenderer(ResizableImage);
        }
      }),
      Link.configure({
        autolink: true,
        openOnClick: true
      })
    ],
    onUpdate: ({ editor: ed }) => {
      const html = ed.getHTML();
      lastHtmlRef.current = html;
      onChange?.(html);
    }
  });

  const [linkOpen, setLinkOpen] = useState(false);
  const [linkUrl, setLinkUrl] = useState('');

  useEffect(() => {
    if (!editor) return;

    // Try to fix broken base64 images where '+' might have been replaced by spaces during storage/transport
    // This addresses the issue where images don't show up when editing an existing note
    const fixedValue = (value || '').replace(/(src="data:image\/[^;]+;base64,)([^"]+)"/g, (match, prefix, data) => {
      // Only replace if we find spaces in what should be a base64 string
      if (data.includes(' ')) {
        return `${prefix}${data.replace(/ /g, '+')}"`;
      }
      return match;
    });

    const valueChanged = fixedValue !== prevValueRef.current;
    prevValueRef.current = fixedValue;

    // If value matches what we last emitted, no need to update
    if (fixedValue === lastHtmlRef.current) return;

    // Only update content if:
    // 1. Value actually changed from parent (not just a re-render with same value)
    // 2. Value is different from current editor content
    if (valueChanged && fixedValue !== editor.getHTML()) {
      editor.commands.setContent(fixedValue);
      // Update lastHtmlRef to match the new content we just set
      lastHtmlRef.current = fixedValue;
    }
  }, [value, editor]);

  const addImage = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = e => {
        if (editor && typeof e.target?.result === 'string') {
          editor.chain().focus().setImage({ src: e.target.result }).run();
          // Manually trigger update if needed, though run() should do it
        }
      };
      reader.readAsDataURL(file);
    }
    // Always clear the input value to allow selecting the same file again
    if (event.target) {
      event.target.value = '';
    }
  };

  return (
    <div className="w-full">
      <Space className="mb-2">
        <Button
          icon={<Icon icon="mdi:format-bold" />}
          type={editor?.isActive('bold') ? 'primary' : 'default'}
          onClick={() => editor?.chain().focus().toggleBold().run()}
        />
        <Button
          icon={<Icon icon="mdi:format-italic" />}
          type={editor?.isActive('italic') ? 'primary' : 'default'}
          onClick={() => editor?.chain().focus().toggleItalic().run()}
        />
        <Button
          icon={<Icon icon="mdi:format-underline" />}
          type={editor?.isActive('underline') ? 'primary' : 'default'}
          onClick={() => editor?.chain().focus().toggleUnderline().run()}
        />
        <Button
          icon={<Icon icon="mdi:format-list-bulleted" />}
          type={editor?.isActive('bulletList') ? 'primary' : 'default'}
          onClick={() => editor?.chain().focus().toggleBulletList().run()}
        />
        <Button
          icon={<Icon icon="mdi:format-list-numbered" />}
          type={editor?.isActive('orderedList') ? 'primary' : 'default'}
          onClick={() => editor?.chain().focus().toggleOrderedList().run()}
        />
        <Button
          icon={<Icon icon="mdi:format-quote-close" />}
          type={editor?.isActive('blockquote') ? 'primary' : 'default'}
          onClick={() => editor?.chain().focus().toggleBlockquote().run()}
        />
        <Button
          icon={<Icon icon="mdi:code-tags" />}
          type={editor?.isActive('codeBlock') ? 'primary' : 'default'}
          onClick={() => editor?.chain().focus().toggleCodeBlock().run()}
        />
        <Button
          icon={<Icon icon="mdi:image" />}
          onClick={() => fileInputRef.current?.click()}
        />
        <Button
          icon={<Icon icon="mdi:link-variant" />}
          onClick={() => setLinkOpen(true)}
        />
        <Button onClick={() => editor?.chain().focus().unsetLink().run()}>移除链接</Button>
        <Button onClick={() => editor?.chain().focus().unsetAllMarks().clearNodes().run()}>清除格式</Button>
      </Space>
      <input
        accept="image/*"
        ref={fileInputRef}
        style={{ display: 'none' }}
        type="file"
        onChange={addImage}
      />
      <EditorContent editor={editor} />
      <Modal
        open={linkOpen}
        title="插入链接"
        onCancel={() => setLinkOpen(false)}
        onOk={() => {
          if (linkUrl) editor?.chain().focus().setLink({ href: linkUrl }).run();
          setLinkOpen(false);
          setLinkUrl('');
        }}
      >
        <Input
          placeholder="https://"
          value={linkUrl}
          onChange={e => setLinkUrl(e.target.value)}
        />
      </Modal>
    </div>
  );
};

export default RichTextEditor;
