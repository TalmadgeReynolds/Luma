import React, { useState } from 'react';

type ContentTypeFilter = 'webinar' | 'article' | null;

interface AskBoxProps {
  onSubmit: (question: string, contentTypeFilter: ContentTypeFilter) => void;
  loading: boolean;
}

export default function AskBox({ onSubmit, loading }: AskBoxProps) {
  const [question, setQuestion] = useState('');
  const [contentTypeFilter, setContentTypeFilter] = useState<ContentTypeFilter>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (question.trim()) {
      onSubmit(question.trim(), contentTypeFilter);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="ask-box">
      <div className="ask-input-group">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about webinars or articles..."
          disabled={loading}
          className="ask-input"
        />
        <div className="content-filter" role="group" aria-label="Content type filter">
          <button
            type="button"
            className={`filter-chip ${contentTypeFilter === null ? 'active' : ''}`}
            onClick={() => setContentTypeFilter(null)}
            disabled={loading}
          >
            All
          </button>
          <button
            type="button"
            className={`filter-chip ${contentTypeFilter === 'webinar' ? 'active' : ''}`}
            onClick={() => setContentTypeFilter('webinar')}
            disabled={loading}
          >
            Videos
          </button>
          <button
            type="button"
            className={`filter-chip ${contentTypeFilter === 'article' ? 'active' : ''}`}
            onClick={() => setContentTypeFilter('article')}
            disabled={loading}
          >
            Articles
          </button>
        </div>
      </div>
      <button
        type="submit"
        disabled={loading || !question.trim()}
        className="ask-button"
      >
        {loading ? 'Searching...' : 'Ask'}
      </button>
    </form>
  );
}
