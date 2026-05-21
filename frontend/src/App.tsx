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
        <h1>Webinar Library Answer Engine</h1>
        <p>Ask questions about our webinar content</p>
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
            Searching webinar library...
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
              <section className="sources-section">
                <h2>Sources</h2>
                <div className="sources-grid">
                  {sources.map((source) => (
                    <SourceCard key={source.chunk_id} source={source} />
                  ))}
                </div>
              </section>
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
