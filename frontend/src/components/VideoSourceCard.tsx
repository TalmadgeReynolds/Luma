import { useRef, useState } from 'react';
import type { SourceCard as SourceCardType } from '../types/api';

const EXCERPT_MAX = 140;

function truncate(text: string): string {
  if (text.length <= EXCERPT_MAX) return text;
  return text.slice(0, EXCERPT_MAX).trimEnd() + '…';
}

interface VideoChunk {
  chunk_id: string;
  start_time_seconds: number | null;
  display_time: string | null;
  excerpt: string;
}

interface VideoSourceCardProps {
  title: string;
  sourceUrl: string;
  chunks: VideoChunk[];
}

export function toVideoChunks(sources: SourceCardType[]): VideoChunk[] {
  return sources.map((s) => ({
    chunk_id: s.chunk_id,
    start_time_seconds: s.start_time_seconds,
    display_time: s.display_time,
    excerpt: s.excerpt,
  }));
}

export default function VideoSourceCard({ title, sourceUrl, chunks }: VideoSourceCardProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [activeChunkId, setActiveChunkId] = useState<string>(chunks[0]?.chunk_id ?? '');

  const handleLoadedMetadata = () => {
    const first = chunks[0];
    if (videoRef.current && first?.start_time_seconds != null) {
      videoRef.current.currentTime = first.start_time_seconds;
    }
  };

  const seekToChunk = (chunk: VideoChunk) => {
    setActiveChunkId(chunk.chunk_id);
    if (videoRef.current && chunk.start_time_seconds != null) {
      videoRef.current.currentTime = chunk.start_time_seconds;
      videoRef.current.play().catch(() => {});
    }
  };

  return (
    <div className="video-source-card">
      <div className="video-source-card__header">
        <span className="video-source-card__title">{title}</span>
        <a
          href={sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="video-source-card__open-link"
        >
          Open Video →
        </a>
      </div>

      <video
        ref={videoRef}
        className="video-source-card__player"
        src={sourceUrl}
        controls
        crossOrigin="anonymous"
        onLoadedMetadata={handleLoadedMetadata}
      />

      <ul className="video-source-card__chunks">
        {chunks.map((chunk) => (
          <li
            key={chunk.chunk_id}
            className={`video-source-card__chunk${activeChunkId === chunk.chunk_id ? ' video-source-card__chunk--active' : ''}`}
            onClick={() => seekToChunk(chunk)}
          >
            {chunk.display_time && (
              <span className="video-source-card__time">{chunk.display_time}</span>
            )}
            <span className="video-source-card__excerpt">{truncate(chunk.excerpt)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
