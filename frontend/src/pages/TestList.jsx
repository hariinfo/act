import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api/axios';

export default function TestList() {
  const [tests, setTests] = useState([]);
  const [inProgressMap, setInProgressMap] = useState({});
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([
      api.get('/tests/'),
      api.get('/tests/my-attempts').catch(() => ({ data: [] })),
      api.get('/tests/my-history').catch(() => ({ data: [] })),
    ])
      .then(([testsRes, attemptsRes, historyRes]) => {
        setTests(testsRes.data);
        const map = {};
        for (const a of attemptsRes.data) {
          map[a.test_id] = a.id;
        }
        setInProgressMap(map);
        setHistory(historyRes.data);
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

  const restartTest = async (testId) => {
    if (!window.confirm('Are you sure you want to restart? Your current progress will be lost.')) return;
    try {
      const res = await api.post(`/tests/${testId}/restart`);
      navigate(`/tests/${testId}/take`, { state: { attemptId: res.data.id } });
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to restart test');
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
              <div style={{ display: 'flex', gap: 8, flexShrink: 0, marginLeft: 16 }}>
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
                  }}
                >
                  {inProgressMap[test.id] ? 'Resume Test' : 'Start Test'}
                </button>
                {inProgressMap[test.id] && (
                  <button
                    onClick={() => restartTest(test.id)}
                    style={{
                      background: 'white',
                      color: 'var(--act-orange, #e65100)',
                      border: '2px solid var(--act-orange, #e65100)',
                      padding: '12px 24px',
                      borderRadius: 6,
                      fontWeight: 600,
                      fontSize: 14,
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    Restart Test
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Test History */}
      {history.length > 0 && (
        <div style={{ marginTop: 48 }}>
          <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8, color: 'var(--act-blue)' }}>Test History</h2>
          <p style={{ color: 'var(--act-dark-gray)', fontSize: 14, marginBottom: 16 }}>
            Your previously completed tests.
          </p>
          <div style={{
            background: 'white',
            borderRadius: 8,
            border: '1px solid var(--act-border)',
            overflow: 'hidden',
          }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ background: '#f5f7fa', borderBottom: '2px solid var(--act-border)' }}>
                  <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, color: 'var(--act-dark-gray)' }}>Test</th>
                  <th style={{ padding: '12px 16px', textAlign: 'center', fontWeight: 600, color: 'var(--act-dark-gray)' }}>Composite</th>
                  <th style={{ padding: '12px 16px', textAlign: 'center', fontWeight: 600, color: 'var(--act-dark-gray)' }}>Raw Score</th>
                  <th style={{ padding: '12px 16px', textAlign: 'center', fontWeight: 600, color: 'var(--act-dark-gray)' }}>Date</th>
                  <th style={{ padding: '12px 16px', textAlign: 'center', fontWeight: 600, color: 'var(--act-dark-gray)' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {history.map((attempt) => (
                  <tr key={attempt.id} style={{ borderBottom: '1px solid var(--act-border)' }}>
                    <td style={{ padding: '12px 16px', fontWeight: 500 }}>{attempt.test_name}</td>
                    <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                      <span style={{
                        background: attempt.score >= 25 ? '#e8f5e9' : attempt.score >= 18 ? '#fff3e0' : '#ffebee',
                        color: attempt.score >= 25 ? '#2e7d32' : attempt.score >= 18 ? '#e65100' : '#c62828',
                        padding: '4px 12px',
                        borderRadius: 12,
                        fontWeight: 700,
                        fontSize: 13,
                      }}>
                        {attempt.score != null ? `${attempt.score}/36` : '--'}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                      <span style={{ fontWeight: 600, color: 'var(--act-text)' }}>
                        {attempt.total_correct}/{attempt.total_questions}
                      </span>
                      <span style={{ color: 'var(--act-dark-gray)', fontSize: 12, marginLeft: 4 }}>
                        ({attempt.total_questions > 0 ? Math.round(attempt.total_correct / attempt.total_questions * 100) : 0}%)
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'center', color: 'var(--act-dark-gray)' }}>
                      {attempt.completed_at
                        ? new Date(attempt.completed_at).toLocaleDateString(undefined, {
                            month: 'short', day: 'numeric', year: 'numeric',
                            hour: 'numeric', minute: '2-digit',
                          })
                        : '--'}
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                      <div style={{ display: 'flex', gap: 6, justifyContent: 'center' }}>
                        <button
                          onClick={() => navigate(`/tests/${attempt.test_id}/results/${attempt.id}`)}
                          style={{
                            background: 'var(--act-blue)',
                            color: 'white',
                            border: 'none',
                            padding: '6px 16px',
                            borderRadius: 4,
                            fontWeight: 600,
                            fontSize: 13,
                            cursor: 'pointer',
                          }}
                        >
                          View Results
                        </button>
                        <button
                          onClick={async () => {
                            if (!window.confirm('Delete this test record? This cannot be undone.')) return;
                            try {
                              await api.delete(`/tests/attempts/${attempt.id}`);
                              setHistory((prev) => prev.filter((h) => h.id !== attempt.id));
                            } catch (err) {
                              alert('Failed to delete record');
                            }
                          }}
                          style={{
                            background: 'white',
                            color: 'var(--act-red, #c62828)',
                            border: '1px solid var(--act-red, #c62828)',
                            padding: '6px 12px',
                            borderRadius: 4,
                            fontWeight: 600,
                            fontSize: 13,
                            cursor: 'pointer',
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
