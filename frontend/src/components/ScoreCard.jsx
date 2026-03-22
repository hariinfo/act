export default function ScoreCard({ results }) {
  if (!results) return null;

  return (
    <div style={{ maxWidth: 700, margin: '0 auto' }}>
      {/* Composite Score */}
      <div style={{
        textAlign: 'center',
        padding: 32,
        background: 'var(--act-blue)',
        borderRadius: 12,
        color: 'white',
        marginBottom: 24,
      }}>
        <div style={{ fontSize: 14, textTransform: 'uppercase', letterSpacing: 2, opacity: 0.8, marginBottom: 8 }}>
          Composite Score
        </div>
        <div style={{ fontSize: 72, fontWeight: 800, lineHeight: 1 }}>
          {results.composite_score}
        </div>
        <div style={{ fontSize: 16, opacity: 0.7, marginTop: 8 }}>out of 36</div>
        <div style={{ marginTop: 16, fontSize: 14, opacity: 0.9 }}>
          {results.total_correct} of {results.total_questions} correct ({results.overall_percentage}%)
        </div>
      </div>

      {/* Section Scores */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280, 1fr))', gap: 16 }}>
        {results.section_scores.map((section) => (
          <div key={section.section_id} style={{
            background: 'white',
            borderRadius: 8,
            padding: 20,
            border: '1px solid var(--act-border)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: 16 }}>{section.subject_name}</div>
                <div style={{ fontSize: 12, color: 'var(--act-dark-gray)' }}>{section.section_name}</div>
              </div>
              <div style={{
                fontSize: 28,
                fontWeight: 800,
                color: 'var(--act-blue)',
              }}>
                {section.scaled_score}
              </div>
            </div>

            {/* Progress bar */}
            <div style={{
              background: '#e0e0e0',
              borderRadius: 4,
              height: 8,
              overflow: 'hidden',
              marginBottom: 8,
            }}>
              <div style={{
                height: '100%',
                width: `${section.percentage}%`,
                background: section.percentage >= 70 ? 'var(--act-green)' :
                  section.percentage >= 40 ? 'var(--act-orange)' : 'var(--act-red)',
                borderRadius: 4,
                transition: 'width 0.5s ease',
              }} />
            </div>

            <div style={{ fontSize: 13, color: 'var(--act-dark-gray)' }}>
              {section.correct} / {section.total} correct ({section.percentage}%)
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
