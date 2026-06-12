import React, { useState } from 'react';

type ContentFilter = 'webinar' | 'article' | null;

interface AskBoxProps {
  onSubmit: (question: string, filter: ContentFilter) => void;
  loading: boolean;
}

const FILTERS: { value: ContentFilter; label: string }[] = [
  { value: null, label: 'All' },
  { value: 'webinar', label: 'Videos' },
  { value: 'article', label: 'Articles' },
];

export default function AskBox({ onSubmit, loading }: AskBoxProps) {
  const [question, setQuestion] = useState('');
  const [filter, setFilter] = useState<ContentFilter>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (question.trim()) {
      onSubmit(question.trim(), filter);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="ask-box-wrapper">
      <div className="ask-box">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about the webinar library..."
          disabled={loading}
          className="ask-input"
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="ask-button"
        >
          {loading ? 'Searching...' : 'Ask'}
        </button>
      </div>
      <div className="filter-toggle">
        {FILTERS.map((f) => (
          <button
            key={String(f.value)}
            type="button"
            disabled={loading}
            className={`filter-btn ${filter === f.value ? 'active' : ''}`}
            onClick={() => setFilter(f.value)}
          >
            {f.label}
          </button>
        ))}
      </div>
    </form>
  );
}
