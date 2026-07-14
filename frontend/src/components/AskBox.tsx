import React, { useState } from 'react';

type ContentTypeFilter = 'webinar' | 'article' | null;

interface AskBoxProps {
  onSubmit: (question: string, contentTypeFilter: ContentTypeFilter) => void;
  loading: boolean;
  expanded?: boolean;
  onReset?: () => void;
}

export default function AskBox({ onSubmit, loading, expanded = false, onReset }: AskBoxProps) {
  const [question, setQuestion] = useState('');
  const [contentTypeFilter, setContentTypeFilter] = useState<ContentTypeFilter>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (question.trim()) {
      onSubmit(question.trim(), contentTypeFilter);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && question.trim() && !loading) {
      onSubmit(question.trim(), contentTypeFilter);
    }
  };

  const handleReset = () => {
    setQuestion('');
    setContentTypeFilter(null);
    onReset?.();
  };

  return (
    <form onSubmit={handleSubmit} className="ask-box">
      {/* Filter tabs row */}
      <div className="ask-filter-row">
        <button
          type="button"
          className={`filter-tab ${contentTypeFilter === null ? 'active' : ''}`}
          onClick={() => setContentTypeFilter(null)}
          disabled={loading}
        >
          All
        </button>
        <button
          type="button"
          className={`filter-tab ${contentTypeFilter === 'webinar' ? 'active' : ''}`}
          onClick={() => setContentTypeFilter('webinar')}
          disabled={loading}
        >
          Videos
        </button>
        <button
          type="button"
          className={`filter-tab ${contentTypeFilter === 'article' ? 'active' : ''}`}
          onClick={() => setContentTypeFilter('article')}
          disabled={loading}
        >
          Articles
        </button>
        <div className="ask-filter-spacer" />
        <button type="button" className="ask-info-btn" aria-label="Help" tabIndex={-1}>
          ?
        </button>
        {expanded && (
          <button
            type="button"
            className="ask-close-btn"
            onClick={handleReset}
            aria-label="Close"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        )}
      </div>

      {/* Input row */}
      <div className="ask-input-row">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything about creating with Luma"
          disabled={loading}
          className="ask-input"
          aria-label="Ask a question"
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="ask-submit-btn"
          aria-label="Submit"
        >
          {loading ? (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
              <path d="M12 2a10 10 0 0 1 10 10" strokeLinecap="round" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="5" y1="12" x2="19" y2="12" />
              <polyline points="12 5 19 12 12 19" />
            </svg>
          )}
        </button>
      </div>
    </form>
  );
}
