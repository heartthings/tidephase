import clsx from 'clsx';

import { RECOMMENDED_NODE_COLORS } from '../node-color';

interface ColorPalettePickerProps {
  onChange?: (value: string | undefined) => void;
  value?: string;
}

const ColorPalettePicker = ({ onChange, value }: ColorPalettePickerProps) => {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col gap-10px">
      <div className="flex flex-wrap gap-8px">
        {RECOMMENDED_NODE_COLORS.map(color => {
          const selected = value?.toUpperCase() === color.toUpperCase();
          return (
            <button
              aria-label={color}
              aria-pressed={selected}
              key={color}
              style={{ backgroundColor: color }}
              title={color}
              type="button"
              className={clsx(
                'h-32px w-32px cursor-pointer rounded-8px border-2 border-solid transition-all',
                selected ? 'scale-110 border-[var(--color-text)] shadow-md' : 'border-transparent hover:scale-105'
              )}
              onClick={() => onChange?.(color)}
            />
          );
        })}
      </div>
      {value ? (
        <button
          className="text-secondary self-start text-12px transition-colors hover:text-primary"
          type="button"
          onClick={() => onChange?.(undefined)}
        >
          {t('page.tradingSystem.nodeColorClear')}
        </button>
      ) : null}
    </div>
  );
};

export default ColorPalettePicker;
