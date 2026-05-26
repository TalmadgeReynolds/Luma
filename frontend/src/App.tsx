import { useState } from 'react';
import AskBox from './components/AskBox';
import AnswerPanel from './components/AnswerPanel';
import SourceCard from './components/SourceCard';
import SuggestedQuestions from './components/SuggestedQuestions';
import { askQuestion } from './api/client';
import type { SourceCard as SourceCardType } from './types/api';

function App() {
  const [answer, setAnswer] = useState('');
  const [sources, setSources] = useState<SourceCardType[]>([]);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const [confidence, setConfidence] = useState<"high" | "medium" | "low">("high");
  const [notEnoughEvidence, setNotEnoughEvidence] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (newQuestion: string) => {
    setLoading(true);
    setError(null);
    setAnswer('');
    setSources([]);
    setSuggestedQuestions([]);
    setNotEnoughEvidence(false);

    try {
      const response = await askQuestion(newQuestion);
      setAnswer(response.answer);
      setSources(response.sources);
      setSuggestedQuestions(response.suggested_questions);
      setConfidence(response.confidence);
      setNotEnoughEvidence(response.not_enough_evidence);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>Luma Knowledge Base</h1>
        <p>Ask questions about our webinars and learning center articles</p>
      </header>

      <main className="app-main">
        <AskBox onSubmit={handleSubmit} loading={loading} />

        {error && (
          <div className="error-message">
            <strong>Error:</strong> {error}
          </div>
        )}

        {loading && (
          <div className="loading-message">
            Searching knowledge base...
          </div>
        )}

        {!loading && !error && answer && (
          <>
            <AnswerPanel
              answer={answer}
              confidence={confidence}
              notEnoughEvidence={notEnoughEvidence}
            />

            {sources.length > 0 && (
              <details className="sources-accordion">
                <summary className="sources-toggle">
                  Sources ({sources.length})
                </summary>
                <div className="sources-list">
                  {sources.map((source) => (
                    <SourceCard key={source.chunk_id} source={source} />
                  ))}
                </div>
              </details>
            )}

            <SuggestedQuestions
              questions={suggestedQuestions}
              onQuestionClick={handleSubmit}
            />
          </>
        )}
      </main>
    </div>
  );
}

export default App;
