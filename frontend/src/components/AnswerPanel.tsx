import ReactMarkdown from "react-markdown";

interface AnswerPanelProps {
  answer: string;
  confidence: "high" | "medium" | "low";
  notEnoughEvidence: boolean;
}

export default function AnswerPanel({
  answer,
  confidence,
  notEnoughEvidence,
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
        <ReactMarkdown>{answer}</ReactMarkdown>
      </div>
    </div>
  );
}
