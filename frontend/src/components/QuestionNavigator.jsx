export default function QuestionNavigator({ questionNumbers, totalQuestions, currentQuestion, answeredQuestions, markedQuestions, onNavigate }) {
  const answered = answeredQuestions || new Set();
  const marked = markedQuestions || new Set();
  const answeredCount = answered.size;

  // Use questionNumbers if provided, otherwise fall back to 1..totalQuestions
  const nums = questionNumbers && questionNumbers.length > 0
    ? questionNumbers
    : Array.from({ length: totalQuestions || 0 }, (_, i) => i + 1);

  return (
    <div style={{ padding: 16 }}>
      <div style={{
        fontSize: 13,
        color: 'var(--act-dark-gray)',
        marginBottom: 12,
        fontWeight: 600,
        textAlign: 'center',
      }}>
        {answeredCount} of {nums.length} answered
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(5, 1fr)',
        gap: 6,
      }}>
        {nums.map((num) => {
          const isCurrent = num === currentQuestion;
          const isAnswered = answered.has(num);
          const isMarked = marked.has(num);

          let bg = 'white';
          let color = 'var(--act-text)';
          let border = '2px solid var(--act-border)';

          if (isAnswered) {
            bg = '#c5cae9';
            color = 'var(--act-blue)';
            border = '2px solid #9fa8da';
          }
          if (isMarked) {
            bg = '#fff3e0';
            border = '2px solid var(--act-orange)';
          }
          if (isCurrent) {
            bg = 'var(--act-blue)';
            color = 'white';
            border = '2px solid var(--act-blue)';
          }

          return (
            <button
              key={num}
              onClick={() => onNavigate(num)}
              style={{
                width: '100%',
                aspectRatio: '1',
                border,
                borderRadius: 4,
                background: bg,
                color,
                fontWeight: isCurrent ? 700 : 500,
                fontSize: 13,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.15s',
                position: 'relative',
              }}
            >
              {num}
              {isMarked && !isCurrent && (
                <span style={{
                  position: 'absolute',
                  top: -2,
                  right: -2,
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: 'var(--act-orange)',
                }} />
              )}
            </button>
          );
        })}
      </div>

      <div style={{ marginTop: 16, fontSize: 11, color: 'var(--act-dark-gray)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
          <span style={{ width: 12, height: 12, background: '#c5cae9', borderRadius: 2, border: '1px solid #9fa8da' }} />
          Answered
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
          <span style={{ width: 12, height: 12, background: '#fff3e0', borderRadius: 2, border: '1px solid var(--act-orange)' }} />
          Marked for review
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 12, height: 12, background: 'var(--act-blue)', borderRadius: 2 }} />
          Current
        </div>
      </div>
    </div>
  );
}
