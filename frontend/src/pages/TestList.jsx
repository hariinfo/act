import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api/axios';

export default function TestList() {
  const [tests, setTests] = useState([]);
  const [inProgressMap, setInProgressMap] = useState({});
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([
      api.get('/tests/'),
      api.get('/tests/my-attempts').catch(() => ({ data: [] })),
    ])
      .then(([testsRes, attemptsRes]) => {
        setTests(testsRes.data);
        const map = {};
        for (const a of attemptsRes.data) {
          map[a.test_id] = a.id;
        }
        setInProgressMap(map);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const startOrResume = async (testId) => {
    try {
      const res = await api.post(`/tests/${testId}/start`);
      navigate(`/tests/${testId}/take`, { state: { attemptId: res.data.id } });
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to start test');
    }
  };

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 60, color: 'var(--act-dark-gray)' }}>Loading tests...</div>;
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '32px 20px' }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8, color: 'var(--act-blue)' }}>Available Tests</h1>
      <p style={{ color: 'var(--act-dark-gray)', fontSize: 14, marginBottom: 24 }}>
        Select a test to begin your practice session.
      </p>

      {tests.length === 0 ? (
        <div style={{
          background: 'white', borderRadius: 8, padding: 40, textAlign: 'center',
          border: '1px solid var(--act-border)',
        }}>
          <p style={{ fontSize: 16, color: 'var(--act-dark-gray)' }}>No tests available yet. Check back soon!</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 16 }}>
          {tests.map((test) => (
            <div key={test.id} style={{
              background: 'white',
              borderRadius: 8,
              padding: 24,
              border: '1px solid var(--act-border)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              transition: 'box-shadow 0.2s',
            }}>
              <div>
                <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 4 }}>{test.name}</h3>
                {test.description && (
                  <p style={{ fontSize: 14, color: 'var(--act-dark-gray)', marginBottom: 8 }}>{test.description}</p>
                )}
                <div style={{ display: 'flex', gap: 16, fontSize: 13, color: 'var(--act-dark-gray)' }}>
                  <span>{test.total_questions} questions</span>
                  <span>{test.sections?.length || 0} sections</span>
                  <span>{test.time_limit_minutes} min</span>
                </div>
                {test.sections && (
                  <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                    {test.sections.map((s, i) => (
                      <span key={i} style={{
                        background: '#e8eaf6',
                        color: 'var(--act-blue)',
                        padding: '3px 10px',
                        borderRadius: 12,
                        fontSize: 12,
                        fontWeight: 500,
                      }}>
                        {s.name || `Section ${s.order}`} ({s.num_questions}q / {s.time_limit_minutes}m)
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <button
                onClick={() => startOrResume(test.id)}
                style={{
                  background: inProgressMap[test.id] ? 'var(--act-orange, #e65100)' : 'var(--act-blue)',
                  color: 'white',
                  border: 'none',
                  padding: '12px 24px',
                  borderRadius: 6,
                  fontWeight: 600,
                  fontSize: 14,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                  flexShrink: 0,
                  marginLeft: 16,
                }}
              >
                {inProgressMap[test.id] ? 'Resume Test' : 'Start Test'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
