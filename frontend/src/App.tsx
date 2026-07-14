import { useState } from 'react';
import AskBox from './components/AskBox';
import AnswerPanel from './components/AnswerPanel';
import SourceCard from './components/SourceCard';
import SuggestedQuestions from './components/SuggestedQuestions';
import { askQuestion } from './api/client';
import type { SourceCard as SourceCardType } from './types/api';

type ContentTypeFilter = 'webinar' | 'article' | null;

function App() {
  const [answer, setAnswer] = useState('');
  const [sources, setSources] = useState<SourceCardType[]>([]);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const [confidence, setConfidence] = useState<"high" | "medium" | "low">("high");
  const [notEnoughEvidence, setNotEnoughEvidence] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (
    newQuestion: string,
    contentTypeFilter: ContentTypeFilter = null,
  ) => {
    setLoading(true);
    setError(null);
    setAnswer('');
    setSources([]);
    setSuggestedQuestions([]);
    setNotEnoughEvidence(false);

    try {
      const response = await askQuestion(newQuestion, contentTypeFilter);
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
      {/* Hero background image */}
      <div className="space-bg" aria-hidden="true" />

      {/* Navigation */}
      <nav className="nav">
        <div className="nav-logo">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 3C7.03 3 3 7.03 3 12s4.03 9 9 9 9-4.03 9-9-4.03-9-9-9zm0 16c-2.76 0-5-2.24-5-5 0-1.38.56-2.63 1.46-3.54C9.2 11.2 10.5 12 12 12s2.8-.8 3.54-1.54C16.44 11.37 17 12.62 17 14c0 2.76-2.24 5-5 5z" fill="white"/>
          </svg>
          <span>Luma</span>
        </div>
        <div className="nav-links">
          <a href="#" className="nav-link">PRODUCT</a>
          <a href="#" className="nav-link">PRICING</a>
          <a href="#" className="nav-link">ENTERPRISE</a>
          <a href="#" className="nav-link">NEWS</a>
          <a href="#" className="nav-link">JOIN US</a>
          <button className="nav-signin">SIGN IN</button>
        </div>
      </nav>

      {/* Hero */}
      <section className="hero">
        <h1 className="hero-title">Luma Learning Center</h1>
        <p className="hero-subtitle">
          Tutorials, guides, and inspiration to<br />
          help you get the most out of Luma.
        </p>
        <AskBox onSubmit={handleSubmit} loading={loading} />
      </section>

      {/* Results */}
      {(error || loading || answer) && (
        <div className="results-section">
          <div className="results-inner">
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
                  sources={sources}
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
                  onQuestionClick={(question) => handleSubmit(question, null)}
                />
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
