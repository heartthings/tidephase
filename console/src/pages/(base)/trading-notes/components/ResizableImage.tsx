import { Icon } from '@iconify/react';
import type { NodeViewProps } from '@tiptap/react';
import { NodeViewWrapper } from '@tiptap/react';
import { useCallback, useEffect, useRef, useState } from 'react';

export default function ResizableImage(props: NodeViewProps) {
  const { node, selected, updateAttributes } = props;
  const [width, setWidth] = useState<string | number>(node.attrs.width || '100%');

  const imageRef = useRef<HTMLImageElement>(null);
  const resizingRef = useRef(false);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);
  const latestWidthRef = useRef<number>(0);

  useEffect(() => {
    if (!resizingRef.current) {
      setWidth(node.attrs.width || '100%');
    }
  }, [node.attrs.width]);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();

      if (!imageRef.current) return;

      resizingRef.current = true;
      startXRef.current = e.clientX;
      startWidthRef.current = imageRef.current.offsetWidth;
      latestWidthRef.current = startWidthRef.current;

      const onMouseMove = (moveEvent: MouseEvent) => {
        if (!resizingRef.current) return;

        const diff = moveEvent.clientX - startXRef.current;
        const newWidth = Math.max(50, startWidthRef.current + diff);

        latestWidthRef.current = newWidth;
        setWidth(newWidth);
      };

      const onMouseUp = () => {
        resizingRef.current = false;
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);

        updateAttributes({ width: latestWidthRef.current });
      };

      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    },
    [updateAttributes]
  );

  return (
    <NodeViewWrapper className="relative inline-block leading-none">
      <img
        alt={node.attrs.alt}
        ref={imageRef}
        src={node.attrs.src}
        style={{ height: 'auto', width }}
        title={node.attrs.title}
        className={`block max-w-full transition-[width] duration-0 ${
          selected ? 'ring-2 ring-primary ring-offset-1' : ''
        }`}
      />
      {selected && (
        <div
          className="absolute bottom-1 right-1 cursor-nwse-resize rounded bg-black/50 p-1 text-white hover:bg-primary"
          onMouseDown={onMouseDown}
        >
          <Icon
            className="h-4 w-4"
            icon="mdi:arrow-expand-all"
          />
        </div>
      )}
    </NodeViewWrapper>
  );
}
