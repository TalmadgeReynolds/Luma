import ReactMarkdown from "react-markdown";
import type { SourceCard } from "../types/api";

interface AnswerPanelProps {
  answer: string;
  confidence: "high" | "medium" | "low";
  notEnoughEvidence: boolean;
  sources: SourceCard[];
}

function linkifyCitations(answer: string, sources: SourceCard[]): string {
  let result = answer;

  // Match: (Webinar 'TITLE', HH:MM:SS–HH:MM:SS)
  result = result.replace(
    /\(Webinar '([^']+)',\s*(\d{2}:\d{2}:\d{2}[–-]\d{2}:\d{2}:\d{2})\)/g,
    (match, _title, displayTime) => {
      const source = sources.find(
        (s) => s.content_type === "webinar" && s.display_time === displayTime
      );
      return source ? `[${match}](${source.source_url})` : match;
    }
  );

  // Match: (Article: 'TITLE')
  result = result.replace(
    /\(Article: '([^']+)'\)/g,
    (match, title) => {
      const source = sources.find(
        (s) => s.content_type === "article" && s.title.includes(title)
      );
      return source ? `[${match}](${source.source_url})` : match;
    }
  );

  return result;
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
              <a href={href} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            ),
          }}
        >
          {linkifyCitations(answer, sources)}
        </ReactMarkdown>
      </div>
    </div>
  );
}
