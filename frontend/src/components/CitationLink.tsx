import { useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import VideoHoverPopup from './VideoHoverPopup';
import type { SourceCard } from '../types/api';

const OPEN_DELAY = 400;
const CLOSE_DELAY = 120; // small grace period when moving mouse to popup

interface CitationLinkProps {
  href: string;
  children: React.ReactNode;
  source: SourceCard | undefined;
}

export default function CitationLink({ href, children, source }: CitationLinkProps) {
  const linkRef = useRef<HTMLAnchorElement>(null);
  const openTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [anchorRect, setAnchorRect] = useState<DOMRect | null>(null);

  const isVideo = source?.content_type === 'webinar';

  const scheduleOpen = () => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
    openTimerRef.current = setTimeout(() => {
      if (linkRef.current) {
        setAnchorRect(linkRef.current.getBoundingClientRect());
      }
    }, OPEN_DELAY);
  };

  const scheduleClose = () => {
    if (openTimerRef.current) {
      clearTimeout(openTimerRef.current);
      openTimerRef.current = null;
    }
    closeTimerRef.current = setTimeout(() => {
      setAnchorRect(null);
    }, CLOSE_DELAY);
  };

  const cancelClose = () => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  };

  return (
    <>
      <a
        ref={linkRef}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className={`citation-link${isVideo ? ' citation-link--video' : ''}`}
        onMouseEnter={isVideo ? scheduleOpen : undefined}
        onMouseLeave={isVideo ? scheduleClose : undefined}
      >
        {children}
      </a>
      {isVideo && anchorRect && source &&
        createPortal(
          <VideoHoverPopup
            source={source}
            anchorRect={anchorRect}
            onMouseEnter={cancelClose}
            onMouseLeave={scheduleClose}
          />,
          document.body
        )
      }
    </>
  );
}
