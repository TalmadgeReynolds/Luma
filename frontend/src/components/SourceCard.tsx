import type { SourceCard as SourceCardType } from '../types/api';

interface SourceCardProps {
  source: SourceCardType;
}

export default function SourceCard({ source }: SourceCardProps) {
  const isArticle = source.content_type === 'article';
  const label = isArticle ? 'Article' : 'Video';
  const linkText = isArticle ? 'Open Article →' : 'Open Video →';

  return (
    <div className="source-card">
      <span className="source-type-badge">{label}</span>
      <a
        href={source.source_url}
        target="_blank"
        rel="noopener noreferrer"
        className="source-title-link"
      >
        {source.title}
      </a>
      {source.excerpt && (
        <p className="source-excerpt">{source.excerpt}</p>
      )}
      <a
        href={source.source_url}
        target="_blank"
        rel="noopener noreferrer"
        className="source-link"
      >
        {linkText}
      </a>
    </div>
  );
}
