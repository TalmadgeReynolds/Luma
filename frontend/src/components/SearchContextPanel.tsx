import type { SourceCard } from '../types/api';

type ContentTypeFilter = 'webinar' | 'article' | null;

interface SearchContextPanelProps {
  question: string;
  contentTypeFilter: ContentTypeFilter;
  sources: SourceCard[];
}

function getFilterLabel(contentTypeFilter: ContentTypeFilter): string {
  if (contentTypeFilter === 'webinar') {
    return 'Videos only';
  }

  if (contentTypeFilter === 'article') {
    return 'Articles only';
  }

  return 'All content';
}

export default function SearchContextPanel({
  question,
  contentTypeFilter,
  sources,
}: SearchContextPanelProps) {
  if (!question && sources.length === 0) {
    return null;
  }

  return (
    <details className="search-context-panel" open>
      <summary className="search-context-toggle">Search context</summary>

      <div className="search-context-body">
        <div className="search-context-meta">
          <div className="search-context-block">
            <span className="search-context-label">Question</span>
            <p className="search-context-question">{question}</p>
          </div>

          <div className="search-context-block">
            <span className="search-context-label">Scope</span>
            <span className="search-context-filter">{getFilterLabel(contentTypeFilter)}</span>
          </div>
        </div>

        {sources.length > 0 && (
          <div className="search-context-block">
            <span className="search-context-label">Retrieved sources</span>
            <div className="search-context-sources">
              {sources.map((source) => (
                <div key={source.chunk_id} className="search-context-source">
                  <div className="search-context-source-header">
                    <span className="search-context-source-type">
                      {source.content_type === 'article' ? 'Article' : 'Video'}
                    </span>
                    <span className="search-context-source-title">{source.title}</span>
                    {source.display_time && (
                      <span className="search-context-source-time">{source.display_time}</span>
                    )}
                  </div>

                  {source.section_heading && (
                    <div className="search-context-detail">Section: {source.section_heading}</div>
                  )}

                  {source.speaker_names.length > 0 && (
                    <div className="search-context-detail">
                      Speakers: {source.speaker_names.join(', ')}
                    </div>
                  )}

                  <p className="search-context-excerpt">{source.excerpt}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </details>
  );
}