import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../../api/axios';

export default function AdminDashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [users, setUsers] = useState([]);
  const [tests, setTests] = useState([]);
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [newUser, setNewUser] = useState({ username: '', email: '', password: '' });
  const [creating, setCreating] = useState(false);
  const [sendEmailData, setSendEmailData] = useState(null);
  const [sending, setSending] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const [performance, setPerformance] = useState(null);
  const [loadingPerf, setLoadingPerf] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get('/admin/dashboard'),
      api.get('/admin/users'),
      api.get('/tests/'),
    ])
      .then(([resStats, resUsers, resTests]) => {
        setStats(resStats.data);
        setUsers(resUsers.data);
        setTests(resTests.data);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const seedSubjects = async () => {
    try {
      const res = await api.post('/admin/seed-subjects');
      alert(res.data.message);
      window.location.reload();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to seed subjects');
    }
  };

  const deleteAllQuestions = async () => {
    if (!confirm('Are you sure you want to delete ALL questions, tests, and attempt data? This cannot be undone.')) return;
    if (!confirm('This will permanently remove everything. Type YES to confirm.')) return;
    try {
      const res = await api.delete('/admin/questions/all');
      alert(res.data.message);
      window.location.reload();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to delete');
    }
  };

  const handleCreateUser = async () => {
    if (!newUser.username || !newUser.email || !newUser.password) {
      alert('All fields are required');
      return;
    }
    setCreating(true);
    try {
      const res = await api.post('/admin/users', newUser);
      setUsers((prev) => [res.data, ...prev]);
      setShowCreateUser(false);
      setNewUser({ username: '', email: '', password: '' });
      alert(`User "${res.data.username}" created successfully`);
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to create user');
    } finally {
      setCreating(false);
    }
  };

  const handleSendEmail = async () => {
    if (!sendEmailData) return;
    setSending(true);
    try {
      const res = await api.post('/admin/send-test-email', sendEmailData);
      if (res.data.email_sent) {
        alert(res.data.message);
      } else {
        alert(`${res.data.message}\n\nTest link: ${res.data.test_url}`);
      }
      setSendEmailData(null);
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to send');
    } finally {
      setSending(false);
    }
  };

  const loadPerformance = async (user) => {
    setSelectedUser(user);
    setLoadingPerf(true);
    try {
      const res = await api.get(`/admin/users/${user.id}/performance`);
      setPerformance(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingPerf(false);
    }
  };

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 60 }}>Loading...</div>;
  }

  const subjectColors = { English: '#1565c0', Math: '#2e7d32', Reading: '#6a1b9a', Science: '#e65100' };

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: '32px 20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--act-blue)' }}>Admin Dashboard</h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={seedSubjects} style={{
            padding: '8px 16px', border: '1px solid var(--act-border)', borderRadius: 6,
            background: 'white', fontSize: 13, fontWeight: 600, cursor: 'pointer',
          }}>
            Seed Subjects
          </button>
          <button onClick={deleteAllQuestions} style={{
            padding: '8px 16px', border: '1px solid var(--act-red)', borderRadius: 6,
            background: 'white', color: 'var(--act-red)', fontSize: 13, fontWeight: 600, cursor: 'pointer',
          }}>
            Delete All Questions
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 32 }}>
        <StatCard label="Questions" value={stats?.total_questions || 0} color="var(--act-blue)" />
        <StatCard label="Tests" value={stats?.total_tests || 0} color="var(--act-accent)" />
        <StatCard label="Users" value={stats?.total_users || 0} color="var(--act-green)" />
        <StatCard label="Attempts" value={stats?.total_attempts || 0} color="var(--act-orange)" />
      </div>

      {/* User Management */}
      <div style={{
        background: 'white', borderRadius: 8, padding: 24, marginBottom: 24,
        border: '1px solid var(--act-border)',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ fontSize: 16, fontWeight: 700 }}>Users</h3>
          <button onClick={() => setShowCreateUser(!showCreateUser)} style={{
            padding: '8px 16px', background: 'var(--act-blue)', color: 'white',
            border: 'none', borderRadius: 6, fontWeight: 600, cursor: 'pointer', fontSize: 13,
          }}>
            + New User
          </button>
        </div>

        {/* Create User Form */}
        {showCreateUser && (
          <div style={{
            background: '#f0f4ff', borderRadius: 8, padding: 20, marginBottom: 16,
            border: '1px solid #d0d8f0',
          }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: 12, alignItems: 'end' }}>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Username</label>
                <input value={newUser.username} onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
                  style={{ width: '100%', padding: '8px 10px', border: '1px solid #ccc', borderRadius: 4, fontSize: 14 }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Email</label>
                <input type="email" value={newUser.email} onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
                  style={{ width: '100%', padding: '8px 10px', border: '1px solid #ccc', borderRadius: 4, fontSize: 14 }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Password</label>
                <input value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                  style={{ width: '100%', padding: '8px 10px', border: '1px solid #ccc', borderRadius: 4, fontSize: 14 }} />
              </div>
              <button onClick={handleCreateUser} disabled={creating} style={{
                padding: '8px 20px', background: 'var(--act-green)', color: 'white',
                border: 'none', borderRadius: 6, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap',
              }}>
                {creating ? 'Creating...' : 'Create'}
              </button>
            </div>
          </div>
        )}

        {/* Users Table */}
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid var(--act-border)' }}>
                <th style={{ textAlign: 'left', padding: '8px 12px', fontWeight: 600, color: '#555' }}>Username</th>
                <th style={{ textAlign: 'left', padding: '8px 12px', fontWeight: 600, color: '#555' }}>Email</th>
                <th style={{ textAlign: 'left', padding: '8px 12px', fontWeight: 600, color: '#555' }}>Role</th>
                <th style={{ textAlign: 'left', padding: '8px 12px', fontWeight: 600, color: '#555' }}>Created</th>
                <th style={{ textAlign: 'center', padding: '8px 12px', fontWeight: 600, color: '#555' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: '10px 12px', fontWeight: 600 }}>{u.username}</td>
                  <td style={{ padding: '10px 12px', color: '#666' }}>{u.email}</td>
                  <td style={{ padding: '10px 12px' }}>
                    <span style={{
                      background: u.is_admin ? '#e3f2fd' : '#f5f5f5',
                      color: u.is_admin ? '#1565c0' : '#666',
                      padding: '2px 10px', borderRadius: 12, fontSize: 12, fontWeight: 600,
                    }}>
                      {u.is_admin ? 'Admin' : 'Student'}
                    </span>
                  </td>
                  <td style={{ padding: '10px 12px', color: '#999', fontSize: 13 }}>
                    {u.created_at ? new Date(u.created_at).toLocaleDateString() : ''}
                  </td>
                  <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'center' }}>
                      <button onClick={() => setSendEmailData({ user_id: u.id, test_id: tests[0]?.id || '', password: '' })}
                        style={{
                          padding: '4px 10px', border: '1px solid var(--act-blue)', borderRadius: 4,
                          background: 'white', color: 'var(--act-blue)', fontSize: 12, cursor: 'pointer', fontWeight: 600,
                        }}>
                        Send Test
                      </button>
                      {!u.is_admin && (
                        <button onClick={() => loadPerformance(u)}
                          style={{
                            padding: '4px 10px', border: '1px solid var(--act-green)', borderRadius: 4,
                            background: 'white', color: 'var(--act-green)', fontSize: 12, cursor: 'pointer', fontWeight: 600,
                          }}>
                          Performance
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Send Test Email Modal */}
      {sendEmailData && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }} onClick={() => setSendEmailData(null)}>
          <div style={{
            background: 'white', borderRadius: 12, padding: 32, width: 450,
            boxShadow: '0 4px 24px rgba(0,0,0,0.2)',
          }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--act-blue)', marginBottom: 20 }}>
              Send Test Link
            </h3>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>User</label>
              <div style={{ padding: '8px 12px', background: '#f5f5f5', borderRadius: 4, fontSize: 14 }}>
                {users.find((u) => u.id === sendEmailData.user_id)?.username} ({users.find((u) => u.id === sendEmailData.user_id)?.email})
              </div>
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Select Test</label>
              <select value={sendEmailData.test_id}
                onChange={(e) => setSendEmailData({ ...sendEmailData, test_id: parseInt(e.target.value) })}
                style={{ width: '100%', padding: '8px 10px', border: '1px solid #ccc', borderRadius: 4, fontSize: 14 }}>
                <option value="">Choose a test...</option>
                {tests.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                Password <span style={{ fontWeight: 400, color: '#999' }}>(include in email)</span>
              </label>
              <input value={sendEmailData.password || ''}
                onChange={(e) => setSendEmailData({ ...sendEmailData, password: e.target.value })}
                placeholder="Leave blank to not include"
                style={{ width: '100%', padding: '8px 10px', border: '1px solid #ccc', borderRadius: 4, fontSize: 14 }} />
            </div>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button onClick={() => setSendEmailData(null)} style={{
                padding: '10px 20px', border: '1px solid var(--act-border)', borderRadius: 6,
                background: 'white', fontWeight: 600, cursor: 'pointer',
              }}>Cancel</button>
              <button onClick={handleSendEmail} disabled={sending || !sendEmailData.test_id} style={{
                padding: '10px 24px', border: 'none', borderRadius: 6,
                background: 'var(--act-blue)', color: 'white', fontWeight: 600, cursor: 'pointer',
                opacity: sending || !sendEmailData.test_id ? 0.6 : 1,
              }}>
                {sending ? 'Sending...' : 'Send Email'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Performance Modal */}
      {selectedUser && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }} onClick={() => { setSelectedUser(null); setPerformance(null); }}>
          <div style={{
            background: 'white', borderRadius: 12, padding: 32, width: 700, maxHeight: '80vh', overflowY: 'auto',
            boxShadow: '0 4px 24px rgba(0,0,0,0.2)',
          }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--act-blue)' }}>
                Performance: {selectedUser.username}
              </h3>
              <button onClick={() => { setSelectedUser(null); setPerformance(null); }}
                style={{ border: 'none', background: 'none', fontSize: 24, cursor: 'pointer', color: '#999' }}>&times;</button>
            </div>

            {loadingPerf ? (
              <div style={{ textAlign: 'center', padding: 40, color: '#666' }}>Loading...</div>
            ) : performance?.attempts?.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>No completed tests yet.</div>
            ) : (
              performance?.attempts?.map((attempt) => (
                <div key={attempt.attempt_id} style={{
                  border: '1px solid var(--act-border)', borderRadius: 8, padding: 20, marginBottom: 16,
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                    <div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--act-blue)' }}>{attempt.test_name}</div>
                      <div style={{ fontSize: 12, color: '#999' }}>
                        {attempt.completed_at ? new Date(attempt.completed_at).toLocaleString() : ''}
                      </div>
                    </div>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: 32, fontWeight: 800, color: 'var(--act-blue)' }}>{attempt.composite_score}</div>
                      <div style={{ fontSize: 11, color: '#999' }}>Composite</div>
                    </div>
                  </div>
                  <div style={{ fontSize: 13, marginBottom: 8, color: '#666' }}>
                    {attempt.total_correct} / {attempt.total_questions} correct ({Math.round(attempt.total_correct / attempt.total_questions * 100)}%)
                  </div>

                  {/* Section scores */}
                  {attempt.section_scores.map((sec) => (
                    <div key={sec.section_name} style={{ marginBottom: 12 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                        <span style={{ fontSize: 14, fontWeight: 600, color: subjectColors[sec.subject] || '#333' }}>
                          {sec.section_name}
                        </span>
                        <span style={{ fontSize: 13 }}>
                          <strong>{sec.correct}/{sec.total}</strong>
                          <span style={{ color: '#999', marginLeft: 6 }}>({sec.percentage}%)</span>
                          <span style={{
                            background: subjectColors[sec.subject] || '#333', color: 'white',
                            padding: '2px 8px', borderRadius: 10, fontSize: 12, fontWeight: 700, marginLeft: 8,
                          }}>{sec.scaled_score}</span>
                        </span>
                      </div>
                      <div style={{ height: 6, background: '#f0f0f0', borderRadius: 3 }}>
                        <div style={{
                          height: '100%', borderRadius: 3,
                          width: `${sec.percentage}%`,
                          background: subjectColors[sec.subject] || '#666',
                        }} />
                      </div>

                      {/* Topic breakdown */}
                      {Object.keys(sec.topics || {}).length > 0 && (
                        <div style={{ marginTop: 6, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                          {Object.entries(sec.topics).map(([topic, data]) => (
                            <span key={topic} style={{
                              fontSize: 11, padding: '2px 8px', borderRadius: 3,
                              background: data.percentage >= 70 ? '#e8f5e9' : data.percentage >= 40 ? '#fff3e0' : '#ffebee',
                              color: data.percentage >= 70 ? '#2e7d32' : data.percentage >= 40 ? '#e65100' : '#c62828',
                              fontWeight: 500,
                            }}>
                              {topic}: {data.correct}/{data.total} ({data.percentage}%)
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Questions by Subject */}
      {stats?.questions_by_subject && Object.keys(stats.questions_by_subject).length > 0 && (
        <div style={{
          background: 'white', borderRadius: 8, padding: 24, marginBottom: 24,
          border: '1px solid var(--act-border)',
        }}>
          <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>Questions by Subject</h3>
          {Object.entries(stats.questions_by_subject).map(([name, count]) => (
            <div key={name} style={{ display: 'flex', alignItems: 'center', marginBottom: 12 }}>
              <span style={{ width: 80, fontSize: 14, fontWeight: 500 }}>{name}</span>
              <div style={{ flex: 1, height: 24, background: '#f0f0f0', borderRadius: 4, marginRight: 12 }}>
                <div style={{
                  height: '100%',
                  width: `${Math.min(100, (count / Math.max(1, stats.total_questions)) * 100)}%`,
                  background: subjectColors[name] || 'var(--act-blue)',
                  borderRadius: 4,
                  minWidth: count > 0 ? 4 : 0,
                }} />
              </div>
              <span style={{ fontSize: 14, fontWeight: 600, width: 40, textAlign: 'right' }}>{count}</span>
            </div>
          ))}
        </div>
      )}

      {/* Uploaded PDFs */}
      {stats?.sources?.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Uploaded Question Banks</h3>
          {stats.sources.map((src) => (
            <div key={src.source_test} style={{
              background: 'white', borderRadius: 8, padding: 20, marginBottom: 12,
              border: '1px solid var(--act-border)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                <div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--act-blue)' }}>{src.source_test}</div>
                  <div style={{ fontSize: 13, color: 'var(--act-dark-gray)', marginTop: 2 }}>
                    {src.total_questions} questions
                    {src.created_at && ` \u00b7 Imported ${new Date(src.created_at).toLocaleDateString()}`}
                  </div>
                </div>
                <span style={{
                  background: 'var(--act-blue)', color: 'white', padding: '4px 14px',
                  borderRadius: 12, fontSize: 14, fontWeight: 700,
                }}>{src.total_questions}</span>
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
                {Object.entries(src.by_subject).map(([name, count]) => (
                  <span key={name} style={{
                    background: subjectColors[name] || '#616161', color: 'white', padding: '3px 10px',
                    borderRadius: 4, fontSize: 12, fontWeight: 600,
                  }}>
                    {name}: {count}
                  </span>
                ))}
              </div>
              {Object.keys(src.by_topic).length > 0 && (
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {Object.entries(src.by_topic).sort((a, b) => b[1] - a[1]).map(([topic, count]) => (
                    <span key={topic} style={{
                      background: '#e3f2fd', color: '#1565c0', padding: '2px 8px',
                      borderRadius: 3, fontSize: 11, fontWeight: 500,
                    }}>
                      {topic} ({count})
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Quick Links */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        <QuickLink to="/admin/questions" title="Manage Questions" desc="Add, edit, or delete questions in the bank" />
        <QuickLink to="/admin/tests/create" title="Create Test" desc="Build a new test from the question bank" />
        <QuickLink to="/admin/upload-pdf" title="Upload PDF" desc="Parse questions from ACT PDF files" />
      </div>
    </div>
  );
}

function StatCard({ label, value, color }) {
  return (
    <div style={{
      background: 'white', borderRadius: 8, padding: 20,
      border: '1px solid var(--act-border)', textAlign: 'center',
    }}>
      <div style={{ fontSize: 32, fontWeight: 800, color }}>{value}</div>
      <div style={{ fontSize: 13, color: 'var(--act-dark-gray)', marginTop: 4 }}>{label}</div>
    </div>
  );
}

function QuickLink({ to, title, desc }) {
  return (
    <Link to={to} style={{
      background: 'white', borderRadius: 8, padding: 20, textDecoration: 'none',
      border: '1px solid var(--act-border)', transition: 'box-shadow 0.2s',
      display: 'block',
    }}>
      <h4 style={{ fontSize: 16, fontWeight: 700, color: 'var(--act-blue)', marginBottom: 6 }}>{title}</h4>
      <p style={{ fontSize: 13, color: 'var(--act-dark-gray)', lineHeight: 1.5 }}>{desc}</p>
    </Link>
  );
}
