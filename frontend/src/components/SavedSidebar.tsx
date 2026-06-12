import type { SavedItem } from '../types/api';

interface SavedSidebarProps {
  items: SavedItem[];
  onRemove: (id: string) => void;
}

const TYPE_LABELS: Record<SavedItem['type'], string> = {
  search_term: 'Term',
  stat: 'Stat',
  source: 'Source',
  topic: 'Topic',
};

export default function SavedSidebar({ items, onRemove }: SavedSidebarProps) {
  if (items.length === 0) return null;

  return (
    <div className="saved-sidebar">
      <div className="saved-sidebar-header">
        <span className="saved-sidebar-title">Saved ({items.length})</span>
      </div>
      <div className="saved-items-list">
        {items.map((item) => (
          <div key={item.id} className="saved-item">
            <span className={`saved-item-type saved-item-type-${item.type}`}>
              {TYPE_LABELS[item.type]}
            </span>
            <span className="saved-item-label">{item.label}</span>
            {item.detail && item.type !== 'source' && (
              <span className="saved-item-detail">{item.detail}</span>
            )}
            <button
              className="saved-item-remove"
              onClick={() => onRemove(item.id)}
              title="Remove"
              aria-label={`Remove: ${item.label}`}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
