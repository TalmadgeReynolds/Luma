import { useRef } from 'react';
import type { SourceCard as SourceCardType } from '../types/api';

interface SourceCardProps {
  source: SourceCardType;
}

export default function SourceCard({ source }: SourceCardProps) {
  const isArticle = source.content_type === 'article';
  const videoRef = useRef<HTMLVideoElement>(null);

  const handleLoadedMetadata = () => {
    if (videoRef.current && source.start_time_seconds !== null) {
      videoRef.current.currentTime = source.start_time_seconds;
    }
  };

  return (
    <div className="source-card">
      <span className="source-type-badge">{isArticle ? 'Article' : 'Video'}</span>
      <a
        href={source.source_url}
        target="_blank"
        rel="noopener noreferrer"
        className="source-title-link"
      >
        {source.title}
      </a>

      {!isArticle && source.source_url && (
        <>
          {source.display_time && (
            <span className="source-timestamp">{source.display_time}</span>
          )}
          <video
            ref={videoRef}
            src={source.source_url}
            controls
            crossOrigin="anonymous"
            className="source-video"
            onLoadedMetadata={handleLoadedMetadata}
          />
        </>
      )}

      {source.excerpt && (
        <p className="source-excerpt">{source.excerpt}</p>
      )}

      <a
        href={source.source_url}
        target="_blank"
        rel="noopener noreferrer"
        className="source-link"
      >
        {isArticle ? 'Open Article →' : 'Open Video →'}
      </a>
    </div>
  );
}
