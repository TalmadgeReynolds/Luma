import ReactMarkdown from "react-markdown";
import type { SourceCard } from "../types/api";

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
  confidence,
  notEnoughEvidence,
  sources,
}: AnswerPanelProps) {
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

  const confidenceClass = `confidence-${confidence}`;

  return (
    <div className="answer-panel">
      <div className="answer-header">
        <h2>Answer</h2>
        <span className={`confidence-badge ${confidenceClass}`}>
          {confidence} confidence
        </span>
      </div>
      <div className="answer-text">
        <ReactMarkdown
          components={{
            a: ({ href, children }) => (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="citation-link"
              >
                {children}
              </a>
            ),
          }}
        >
          {resolveChunkCitations(answer, sources)}
        </ReactMarkdown>
      </div>
    </div>
  );
}
