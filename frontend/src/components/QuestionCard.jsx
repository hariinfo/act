const LABELS_ABCDE = ['A', 'B', 'C', 'D', 'E'];
const LABELS_FGHJK = ['F', 'G', 'H', 'J', 'K'];

export default function QuestionCard({ question, selectedAnswer, onSelectAnswer, questionNumber, showResult, correctAnswer, hidePassage, compact, mathMode }) {
  if (!question) return null;

  const optionLabels = question.option_labels === 'FGHJK' ? LABELS_FGHJK : LABELS_ABCDE;

  const options = [
    question.option_a,
    question.option_b,
    question.option_c,
    question.option_d,
    question.option_e,
  ].filter(Boolean);

  return (
    <div style={{ maxWidth: 800 }}>
      {/* Passage - shown inline only when not displayed in split pane */}
      {(question.passage_text || question.passage_image) && !hidePassage && (
        <div style={{
          background: '#fafafa',
          border: '1px solid var(--act-border)',
          borderRadius: 6,
          padding: question.passage_image ? 12 : 20,
          marginBottom: 24,
          maxHeight: 400,
          overflowY: 'auto',
          fontSize: 14,
          lineHeight: 1.8,
        }}>
          <div style={{ fontWeight: 600, fontSize: 12, color: 'var(--act-dark-gray)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>
            Passage
          </div>
          {question.passage_image ? (
            <img src={question.passage_image} alt="Passage" style={{ width: '100%', height: 'auto' }} />
          ) : (
            <div style={{ whiteSpace: 'pre-wrap' }}>{question.passage_text}</div>
          )}
        </div>
      )}

      {/* Question */}
      {!mathMode && (
        <div style={{ marginBottom: compact ? 14 : 24 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: compact ? 8 : 12 }}>
            <span style={{
              background: 'var(--act-blue)',
              color: 'white',
              width: compact ? 28 : 36,
              height: compact ? 28 : 36,
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 700,
              fontSize: compact ? 13 : 16,
              flexShrink: 0,
            }}>
              {questionNumber}
            </span>
            <p style={{ fontSize: compact ? 14 : 16, lineHeight: compact ? 1.5 : 1.7, paddingTop: compact ? 2 : 4 }}>
              {question.question_text}
            </p>
          </div>
          {question.question_image && (
            <div style={{ marginTop: compact ? 8 : 12, marginLeft: compact ? 36 : 48 }}>
              <img src={question.question_image} alt="Question" style={{ maxWidth: '100%', maxHeight: 300, borderRadius: 4 }} />
            </div>
          )}
        </div>
      )}

      {/* Options */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: mathMode ? 12 : (compact ? 6 : 10), marginLeft: mathMode ? 0 : (compact ? 36 : 48), paddingTop: mathMode ? 20 : 0 }}>
        {options.map((text, idx) => {
          const label = optionLabels[idx];
          const isSelected = selectedAnswer === label;
          const isCorrect = showResult && label === correctAnswer;
          const isWrong = showResult && isSelected && label !== correctAnswer;

          let borderColor = 'var(--act-border)';
          let bgColor = 'white';
          let bubbleBg = 'white';
          let bubbleColor = 'var(--act-text)';
          let bubbleBorder = '#999';

          if (isSelected && !showResult) {
            borderColor = 'var(--act-blue)';
            bgColor = '#e8eaf6';
            bubbleBg = 'var(--act-blue)';
            bubbleColor = 'white';
            bubbleBorder = 'var(--act-blue)';
          }
          if (isCorrect) {
            borderColor = 'var(--act-green)';
            bgColor = '#e8f5e9';
            bubbleBg = 'var(--act-green)';
            bubbleColor = 'white';
            bubbleBorder = 'var(--act-green)';
          }
          if (isWrong) {
            borderColor = 'var(--act-red)';
            bgColor = '#ffebee';
            bubbleBg = 'var(--act-red)';
            bubbleColor = 'white';
            bubbleBorder = 'var(--act-red)';
          }

          return (
            <button
              key={label}
              onClick={() => !showResult && onSelectAnswer?.(label)}
              disabled={showResult}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: mathMode ? 'center' : 'flex-start',
                gap: mathMode ? 0 : 14,
                padding: mathMode ? 0 : (compact ? '8px 12px' : '12px 16px'),
                border: mathMode ? 'none' : `2px solid ${borderColor}`,
                borderRadius: mathMode ? '50%' : (compact ? 6 : 8),
                background: mathMode ? 'transparent' : bgColor,
                cursor: showResult ? 'default' : 'pointer',
                transition: 'all 0.15s',
                textAlign: 'left',
                fontSize: compact ? 13 : 15,
                lineHeight: 1.5,
                width: mathMode ? 52 : undefined,
                height: mathMode ? 52 : undefined,
              }}
            >
              <span style={{
                width: mathMode ? 48 : (compact ? 26 : 32),
                height: mathMode ? 48 : (compact ? 26 : 32),
                borderRadius: '50%',
                border: `2px solid ${bubbleBorder}`,
                background: bubbleBg,
                color: bubbleColor,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 700,
                fontSize: mathMode ? 18 : (compact ? 12 : 14),
                flexShrink: 0,
                transition: 'all 0.15s',
              }}>
                {label}
              </span>
              {!mathMode && <span>{text}</span>}
            </button>
          );
        })}
      </div>

      {/* Source badge */}
      {question.source_test && (
        <div style={{
          marginTop: mathMode ? 12 : 16,
          marginLeft: mathMode ? 0 : (compact ? 36 : 48),
          fontSize: 11,
          color: '#999',
          fontStyle: 'italic',
        }}>
          Source: {question.source_test}
        </div>
      )}

      {/* Explanation in review mode */}
      {showResult && question.explanation && (
        <div style={{
          marginTop: 20,
          marginLeft: 48,
          padding: 16,
          background: '#e3f2fd',
          borderRadius: 6,
          border: '1px solid #bbdefb',
          fontSize: 14,
          lineHeight: 1.6,
        }}>
          <strong>Explanation:</strong> {question.explanation}
        </div>
      )}
    </div>
  );
}
