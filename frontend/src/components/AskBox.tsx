import React, { useState } from 'react';

interface AskBoxProps {
  onSubmit: (question: string) => void;
  loading: boolean;
}

export default function AskBox({ onSubmit, loading }: AskBoxProps) {
  const [question, setQuestion] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (question.trim()) {
      onSubmit(question.trim());
    }
  };

  return (
    <form onSubmit={handleSubmit} className="ask-box">
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
    </form>
  );
}
