import { useRef } from 'react';
import type { SourceCard } from '../types/api';

const POPUP_WIDTH = 400;
const VIDEO_HEIGHT = 225; // 16:9
const HEADER_HEIGHT = 52;
const TOTAL_HEIGHT = VIDEO_HEIGHT + HEADER_HEIGHT;
const OFFSET = 10; // gap between link and popup edge

interface VideoHoverPopupProps {
  source: SourceCard;
  anchorRect: DOMRect;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

export default function VideoHoverPopup({
  source,
  anchorRect,
  onMouseEnter,
  onMouseLeave,
}: VideoHoverPopupProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  const handleLoadedMetadata = () => {
    if (videoRef.current && source.start_time_seconds !== null) {
      videoRef.current.currentTime = source.start_time_seconds;
    }
  };

  // Center popup horizontally over the anchor link, clamped to viewport
  const viewportWidth = window.innerWidth;
  let left = anchorRect.left + anchorRect.width / 2 - POPUP_WIDTH / 2;
  left = Math.max(8, Math.min(left, viewportWidth - POPUP_WIDTH - 8));

  // Prefer above the link; flip below if not enough room
  const spaceAbove = anchorRect.top;
  let top: number;
  let transformOrigin: string;
  if (spaceAbove >= TOTAL_HEIGHT + OFFSET) {
    top = anchorRect.top - TOTAL_HEIGHT - OFFSET;
    transformOrigin = 'bottom center';
  } else {
    top = anchorRect.bottom + OFFSET;
    transformOrigin = 'top center';
  }

  return (
    <div
      className="video-hover-popup"
      style={{ left, top, transformOrigin }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="video-hover-popup__header">
        <span className="video-hover-popup__title">{source.title}</span>
        {source.display_time && (
          <span className="video-hover-popup__time">{source.display_time}</span>
        )}
      </div>
      <video
        ref={videoRef}
        className="video-hover-popup__video"
        src={source.source_url}
        autoPlay
        muted
        controls
        crossOrigin="anonymous"
        onLoadedMetadata={handleLoadedMetadata}
      />
    </div>
  );
}
