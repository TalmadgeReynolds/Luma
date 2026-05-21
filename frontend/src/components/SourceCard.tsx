import type { SourceCard as SourceCardType } from '../types/api';

interface SourceCardProps {
  source: SourceCardType;
}

export default function SourceCard({ source }: SourceCardProps) {
  return (
    <div className="source-card">
      <div className="source-header">
        <h3 className="source-title">{source.video_title}</h3>
        <span className="source-time">{source.display_time}</span>
      </div>

      {source.speaker_names.length > 0 && (
        <div className="source-speakers">
          <strong>Speakers:</strong> {source.speaker_names.join(', ')}
        </div>
      )}

      <p className="source-excerpt">{source.excerpt}</p>

      <a
        href={source.video_url}
        target="_blank"
        rel="noopener noreferrer"
        className="source-link"
      >
        Open Clip →
      </a>
    </div>
  );
}
