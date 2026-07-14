interface SuggestedQuestionsProps {
  questions: string[];
  onQuestionClick: (question: string) => void;
}

export default function SuggestedQuestions({
  questions,
  onQuestionClick,
}: SuggestedQuestionsProps) {
  if (questions.length === 0) {
    return null;
  }

  return (
    <div className="suggested-questions">
      <h3>Suggested Questions:</h3>
      <div className="suggested-questions-list">
        {questions.map((question, index) => (
          <button
            key={index}
            onClick={() => onQuestionClick(question)}
            className="suggested-question-button"
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  );
}
