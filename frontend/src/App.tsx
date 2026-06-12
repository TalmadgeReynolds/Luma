import { useState, useCallback, useEffect } from 'react';
import AskBox from './components/AskBox';
import AnswerPanel from './components/AnswerPanel';
import SourceCard from './components/SourceCard';
import SuggestedQuestions from './components/SuggestedQuestions';
import PipelineFeed from './components/PipelineFeed';
import SavedSidebar from './components/SavedSidebar';
import { askQuestion, getSavedItems, createSavedItem, deleteSavedItem } from './api/client';
import type { SourceCard as SourceCardType, ProgressEvent, SavedItem } from './types/api';

function App() {
  const [answer, setAnswer] = useState('');
  const [sources, setSources] = useState<SourceCardType[]>([]);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const [confidence, setConfidence] = useState<"high" | "medium" | "low">("high");
  const [notEnoughEvidence, setNotEnoughEvidence] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progressEvents, setProgressEvents] = useState<ProgressEvent[]>([]);
  const [savedItems, setSavedItems] = useState<SavedItem[]>([]);
  const [queryKey, setQueryKey] = useState(0);

  const handleSave = useCallback(async (item: Omit<SavedItem, 'id' | 'savedAt'>) => {
    try {
      const saved = await createSavedItem(item);
      setSavedItems((prev) => [...prev, saved]);
    } catch {
      // Fall back to local-only if API fails
      setSavedItems((prev) => [
        ...prev,
        { ...item, id: crypto.randomUUID(), savedAt: new Date().toISOString() },
      ]);
    }
  }, []);

  const handleRemove = useCallback(async (id: string) => {
    setSavedItems((prev) => prev.filter((item) => item.id !== id));
    try {
      await deleteSavedItem(id);
    } catch {
      // Item already removed from UI; silently ignore
    }
  }, []);

  useEffect(() => {
    getSavedItems().then(setSavedItems).catch(() => {});
  }, []);

  const handleSubmit = async (newQuestion: string, filter: 'webinar' | 'article' | null = null) => {
    setLoading(true);
    setError(null);
    setAnswer('');
    setSources([]);
    setSuggestedQuestions([]);
    setNotEnoughEvidence(false);
    setProgressEvents([]);
    setQueryKey((k) => k + 1);

    try {
      const response = await askQuestion(newQuestion, filter, (event) => {
        setProgressEvents((prev) => [...prev, event]);
      });
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

  const showPipeline = loading || progressEvents.length > 0;

  return (
    <div className="app">
      <header className="app-header">
        <h1>Luma Knowledge Base</h1>
        <p>Ask questions about our webinars and learning center articles</p>
      </header>

      <main className="app-main">
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
              onQuestionClick={handleSubmit}
            />
          </>
        )}

        {error && (
          <div className="error-message">
            <strong>Error:</strong> {error}
          </div>
        )}

        {showPipeline && (
          <PipelineFeed
            key={queryKey}
            events={progressEvents}
            loading={loading}
            onSave={handleSave}
          />
        )}

        <SavedSidebar items={savedItems} onRemove={handleRemove} />

        <AskBox onSubmit={handleSubmit} loading={loading} />
      </main>
    </div>
  );
}

export default App;
