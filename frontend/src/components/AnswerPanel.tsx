import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import type { SourceCard } from "../types/api";
import CitationLink from "./CitationLink";

interface AnswerPanelProps {
  answer: string;
  confidence: "high" | "medium" | "low";
  notEnoughEvidence: boolean;
  sources: SourceCard[];
}

function resolveChunkCitations(answer: string, sources: SourceCard[]): string {
  return answer.replace(/\(cite:([a-f0-9-]{36})\)/g, (_match, chunkId) => {
    const source = sources.find((s) => s.chunk_id === chunkId);
    if (!source) return "";
    const url =
      source.content_type === "webinar" && source.start_time_seconds !== null
        ? `${source.source_url}#t=${Math.floor(source.start_time_seconds)}`
        : source.source_url;
    return `(${url})`;
  });
}

export default function AnswerPanel({
  answer,
  notEnoughEvidence,
  sources,
}: Omit<AnswerPanelProps, 'confidence'> & { confidence?: AnswerPanelProps['confidence'] }) {
  // Map resolved URL (including #t= fragment for videos) → SourceCard
  // so the citation link renderer can look up metadata for hover previews.
  const sourceByUrl = useMemo(() => {
    const map = new Map<string, SourceCard>();
    for (const s of sources) {
      const url =
        s.content_type === "webinar" && s.start_time_seconds !== null
          ? `${s.source_url}#t=${Math.floor(s.start_time_seconds)}`
          : s.source_url;
      map.set(url, s);
    }
    return map;
  }, [sources]);

  if (notEnoughEvidence) {
    return (
      <div className="answer-panel not-enough-evidence">
        <p>
          <strong>Not enough evidence found.</strong> Try rephrasing your question or
          asking about different topics.
        </p>
      </div>
    );
  }

  if (!answer) {
    return null;
  }

  return (
    <div className="answer-panel">
      <div className="answer-header">
        <h2>Answer</h2>
      </div>
      <div className="answer-text">
        <ReactMarkdown
          components={{
            a: ({ href, children }) => (
              <CitationLink
                href={href ?? '#'}
                source={href ? sourceByUrl.get(href) : undefined}
              >
                {children}
              </CitationLink>
            ),
          }}
        >
          {resolveChunkCitations(answer, sources)}
        </ReactMarkdown>
      </div>
    </div>
  );
}
