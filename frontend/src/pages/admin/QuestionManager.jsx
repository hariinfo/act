import { useState, useEffect } from 'react';
import api from '../../api/axios';

const emptyQuestion = {
  subject_id: '', question_text: '', option_a: '', option_b: '', option_c: '', option_d: '',
  option_e: '', correct_answer: 'A', explanation: '', difficulty: 3, source_test: '', passage_text: '',
};

export default function QuestionManager() {
  const [questions, setQuestions] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({ ...emptyQuestion });
  const [filters, setFilters] = useState({ subject_id: '', difficulty: '', search: '' });
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 20;

  const loadQuestions = () => {
    const params = { skip: page * PAGE_SIZE, limit: PAGE_SIZE };
    if (filters.subject_id) params.subject_id = filters.subject_id;
    if (filters.difficulty) params.difficulty = filters.difficulty;
    if (filters.search) params.search = filters.search;
    api.get('/questions/', { params })
      .then((res) => setQuestions(res.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    api.get('/questions/subjects').then((res) => setSubjects(res.data));
  }, []);

  useEffect(() => {
    setLoading(true);
    loadQuestions();
  }, [page, filters]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const data = { ...form, subject_id: parseInt(form.subject_id), difficulty: parseInt(form.difficulty) };
    if (!data.option_e) delete data.option_e;
    if (!data.explanation) delete data.explanation;
    if (!data.passage_text) delete data.passage_text;
    if (!data.source_test) delete data.source_test;

    try {
      if (editingId) {
        await api.put(`/questions/${editingId}`, data);
      } else {
        await api.post('/questions/', data);
      }
      setShowForm(false);
      setEditingId(null);
      setForm({ ...emptyQuestion });
      loadQuestions();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to save question');
    }
  };

  const handleEdit = (q) => {
    setForm({
      subject_id: q.subject_id,
      question_text: q.question_text,
      option_a: q.option_a,
      option_b: q.option_b,
      option_c: q.option_c,
      option_d: q.option_d,
      option_e: q.option_e || '',
      correct_answer: q.correct_answer,
      explanation: q.explanation || '',
      difficulty: q.difficulty,
      source_test: q.source_test || '',
      passage_text: q.passage_text || '',
    });
    setEditingId(q.id);
    setShowForm(true);
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this question?')) return;
    await api.delete(`/questions/${id}`);
    loadQuestions();
  };

  const inputStyle = {
    width: '100%', padding: '8px 10px', border: '1px solid var(--act-border)',
    borderRadius: 4, fontSize: 14,
  };

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: '32px 20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--act-blue)' }}>Question Bank</h1>
        <button onClick={() => { setShowForm(true); setEditingId(null); setForm({ ...emptyQuestion }); }} style={{
          padding: '10px 20px', background: 'var(--act-blue)', color: 'white', border: 'none',
          borderRadius: 6, fontWeight: 600, cursor: 'pointer',
        }}>
          + Add Question
        </button>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <select value={filters.subject_id} onChange={(e) => { setFilters({ ...filters, subject_id: e.target.value }); setPage(0); }}
          style={{ padding: '8px 12px', border: '1px solid var(--act-border)', borderRadius: 4 }}>
          <option value="">All Subjects</option>
          {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <select value={filters.difficulty} onChange={(e) => { setFilters({ ...filters, difficulty: e.target.value }); setPage(0); }}
          style={{ padding: '8px 12px', border: '1px solid var(--act-border)', borderRadius: 4 }}>
          <option value="">All Difficulties</option>
          {[1, 2, 3, 4, 5].map((d) => <option key={d} value={d}>Difficulty {d}</option>)}
        </select>
        <input
          placeholder="Search questions..."
          value={filters.search}
          onChange={(e) => { setFilters({ ...filters, search: e.target.value }); setPage(0); }}
          style={{ flex: 1, padding: '8px 12px', border: '1px solid var(--act-border)', borderRadius: 4 }}
        />
      </div>

      {/* Questions Table */}
      <div style={{ background: 'white', borderRadius: 8, border: '1px solid var(--act-border)', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
          <thead>
            <tr style={{ background: '#f5f5f5' }}>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600 }}>ID</th>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600 }}>Question</th>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600 }}>Subject</th>
              <th style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 600 }}>Answer</th>
              <th style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 600 }}>Diff.</th>
              <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600 }}>Source</th>
              <th style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 600 }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {questions.map((q) => (
              <tr key={q.id} style={{ borderTop: '1px solid var(--act-border)' }}>
                <td style={{ padding: '10px 12px' }}>{q.id}</td>
                <td style={{ padding: '10px 12px', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {q.question_text}
                </td>
                <td style={{ padding: '10px 12px' }}>
                  {subjects.find((s) => s.id === q.subject_id)?.name || q.subject_id}
                </td>
                <td style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 700 }}>{q.correct_answer}</td>
                <td style={{ padding: '10px 12px', textAlign: 'center' }}>{q.difficulty}</td>
                <td style={{ padding: '10px 12px', fontSize: 12 }}>{q.source_test || '-'}</td>
                <td style={{ padding: '10px 12px', textAlign: 'right' }}>
                  <button onClick={() => handleEdit(q)} style={{
                    padding: '4px 10px', border: '1px solid var(--act-accent)', borderRadius: 4,
                    background: 'white', color: 'var(--act-accent)', fontSize: 12, cursor: 'pointer', marginRight: 6,
                  }}>Edit</button>
                  <button onClick={() => handleDelete(q.id)} style={{
                    padding: '4px 10px', border: '1px solid var(--act-red)', borderRadius: 4,
                    background: 'white', color: 'var(--act-red)', fontSize: 12, cursor: 'pointer',
                  }}>Delete</button>
                </td>
              </tr>
            ))}
            {questions.length === 0 && (
              <tr><td colSpan="7" style={{ padding: 20, textAlign: 'center', color: '#999' }}>No questions found</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div style={{ display: 'flex', justifyContent: 'center', gap: 10, marginTop: 16 }}>
        <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}
          style={{ padding: '6px 14px', border: '1px solid var(--act-border)', borderRadius: 4, cursor: 'pointer', background: 'white' }}>
          Prev
        </button>
        <span style={{ padding: '6px 14px', fontSize: 14 }}>Page {page + 1}</span>
        <button onClick={() => setPage(page + 1)} disabled={questions.length < PAGE_SIZE}
          style={{ padding: '6px 14px', border: '1px solid var(--act-border)', borderRadius: 4, cursor: 'pointer', background: 'white' }}>
          Next
        </button>
      </div>

      {/* Add/Edit Form Modal */}
      {showForm && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
          display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
          zIndex: 200, paddingTop: 40, overflowY: 'auto',
        }}>
          <div style={{
            background: 'white', borderRadius: 12, padding: 32, maxWidth: 700, width: '95%', marginBottom: 40,
          }}>
            <h2 style={{ fontSize: 20, marginBottom: 20, color: 'var(--act-blue)' }}>
              {editingId ? 'Edit Question' : 'Add Question'}
            </h2>
            <form onSubmit={handleSubmit}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 16 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Subject *</label>
                  <select value={form.subject_id} onChange={(e) => setForm({ ...form, subject_id: e.target.value })} required style={inputStyle}>
                    <option value="">Select...</option>
                    {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Difficulty</label>
                  <select value={form.difficulty} onChange={(e) => setForm({ ...form, difficulty: e.target.value })} style={inputStyle}>
                    {[1, 2, 3, 4, 5].map((d) => <option key={d} value={d}>{d}</option>)}
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Source Test</label>
                  <input value={form.source_test} onChange={(e) => setForm({ ...form, source_test: e.target.value })} style={inputStyle} placeholder="e.g. ACT 2020 Form A" />
                </div>
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Passage (optional)</label>
                <textarea value={form.passage_text} onChange={(e) => setForm({ ...form, passage_text: e.target.value })}
                  rows={3} style={{ ...inputStyle, resize: 'vertical' }} placeholder="Reading or science passage text..." />
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Question Text *</label>
                <textarea value={form.question_text} onChange={(e) => setForm({ ...form, question_text: e.target.value })}
                  required rows={3} style={{ ...inputStyle, resize: 'vertical' }} />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                {['A', 'B', 'C', 'D', 'E'].map((label) => (
                  <div key={label}>
                    <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
                      Option {label} {label !== 'E' ? '*' : '(optional)'}
                    </label>
                    <input
                      value={form[`option_${label.toLowerCase()}`]}
                      onChange={(e) => setForm({ ...form, [`option_${label.toLowerCase()}`]: e.target.value })}
                      required={label !== 'E'}
                      style={inputStyle}
                    />
                  </div>
                ))}
                <div>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Correct Answer *</label>
                  <select value={form.correct_answer} onChange={(e) => setForm({ ...form, correct_answer: e.target.value })} required style={inputStyle}>
                    {['A', 'B', 'C', 'D', 'E'].map((l) => <option key={l} value={l}>{l}</option>)}
                  </select>
                </div>
              </div>

              <div style={{ marginBottom: 20 }}>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Explanation (optional)</label>
                <textarea value={form.explanation} onChange={(e) => setForm({ ...form, explanation: e.target.value })}
                  rows={2} style={{ ...inputStyle, resize: 'vertical' }} />
              </div>

              <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
                <button type="button" onClick={() => { setShowForm(false); setEditingId(null); }} style={{
                  padding: '10px 20px', border: '1px solid var(--act-border)', borderRadius: 6,
                  background: 'white', fontWeight: 600, cursor: 'pointer',
                }}>Cancel</button>
                <button type="submit" style={{
                  padding: '10px 24px', border: 'none', borderRadius: 6,
                  background: 'var(--act-blue)', color: 'white', fontWeight: 600, cursor: 'pointer',
                }}>{editingId ? 'Update' : 'Create'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
