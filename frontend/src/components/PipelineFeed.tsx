import { useState } from 'react';
import type { ProgressEvent, SavedItem } from '../types/api';

interface PipelineFeedProps {
  events: ProgressEvent[];
  loading: boolean;
  onSave: (item: Omit<SavedItem, 'id' | 'savedAt'>) => void;
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return 'Date unknown';
  const [year, month, day] = dateStr.split('-');
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export default function PipelineFeed({ events, loading, onSave }: PipelineFeedProps) {
  const [pinned, setPinned] = useState<Set<string>>(new Set());
  const [collapsed, setCollapsed] = useState(false);

  const rewritingEvent = events.find((e) => e.stage === 'rewriting');
  const rankingEvent = events.find((e) => e.stage === 'ranking');

  const searchTerms = rewritingEvent?.data?.search_terms ?? [];
  const sourceTitles = rankingEvent?.data?.source_titles ?? [];

  const handlePin = (key: string, item: Omit<SavedItem, 'id' | 'savedAt'>) => {
    if (pinned.has(key)) return;
    setPinned((prev) => new Set([...prev, key]));
    onSave(item);
  };

  const hasContent = searchTerms.length > 0 || sourceTitles.length > 0;

  if (!hasContent && !loading) return null;

  return (
    <div className="search-preview">
      <button
        className="search-preview-toggle"
        onClick={() => setCollapsed((c) => !c)}
        aria-expanded={!collapsed}
      >
        <span>{collapsed ? '▶' : '▼'}</span>
        <span className="search-preview-toggle-label">Search context</span>
      </button>

      {loading && hasContent && (
        <div className="search-preview-status search-preview-status-inline">
          <span className="stage-spinner" />
          <span>{rankingEvent ? 'Generating answer...' : 'Searching...'}</span>
        </div>
      )}

      {!collapsed && (
        <div className="search-preview-body">
          {!hasContent && loading && (
            <div className="search-preview-status">
              <span>Finding relevant sources...</span>
            </div>
          )}

      {searchTerms.length > 0 && (
        <div className="search-preview-section">
          <span className="search-preview-label">Interpreted as</span>
          <div className="search-preview-terms">
            {searchTerms.map((term) => {
              const key = `term:${term}`;
              return (
                <span key={term} className="search-term-chip">
                  <span className="chip-label">{term}</span>
                  <button
                    className={`chip-pin ${pinned.has(key) ? 'pinned' : ''}`}
                    onClick={() => handlePin(key, { type: 'search_term', label: term })}
                    title={pinned.has(key) ? 'Saved' : 'Save term'}
                    aria-label={`Save: ${term}`}
                  >
                    {pinned.has(key) ? '✓' : '+'}
                  </button>
                </span>
              );
            })}
          </div>
        </div>
      )}

      {sourceTitles.length > 0 && (
        <div className="search-preview-section">
          <span className="search-preview-label">Considering</span>
          <div className="search-preview-sources">
            {sourceTitles.map((source) => {
              const sourceKey = `source:${source.title}`;
              const displayName = source.content_type === 'webinar'
                ? formatDate(source.webinar_date)
                : source.title;

              return (
                <div key={source.title} className="source-preview-row">
                  <div className="source-preview-main">
                    <span className="source-type-icon" aria-label={source.content_type}>
                      {source.content_type === 'webinar' ? '▶' : '≡'}
                    </span>
                    <div className="source-preview-body">
                      <div className="source-preview-header">
                        <span className="source-preview-title">{displayName}</span>
                        <button
                          className={`chip-pin ${pinned.has(sourceKey) ? 'pinned' : ''}`}
                          onClick={() =>
                            handlePin(sourceKey, {
                              type: 'source',
                              label: displayName,
                              detail: source.content_type,
                            })
                          }
                          title={pinned.has(sourceKey) ? 'Saved' : 'Save source'}
                          aria-label={`Save: ${displayName}`}
                        >
                          {pinned.has(sourceKey) ? '✓' : '+'}
                        </button>
                      </div>
                      {source.topics.length > 0 && (
                        <div className="source-topic-chips">
                          {source.topics.map((topic) => {
                            const topicKey = `topic:${source.title}:${topic}`;
                            return (
                              <span key={topic} className="search-term-chip topic-chip">
                                <span className="chip-label">{topic}</span>
                                <button
                                  className={`chip-pin ${pinned.has(topicKey) ? 'pinned' : ''}`}
                                  onClick={() =>
                                    handlePin(topicKey, { type: 'topic', label: topic })
                                  }
                                  title={pinned.has(topicKey) ? 'Saved' : 'Save topic'}
                                  aria-label={`Save topic: ${topic}`}
                                >
                                  {pinned.has(topicKey) ? '✓' : '+'}
                                </button>
                              </span>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
        </div>
      )}
    </div>
  );
}
