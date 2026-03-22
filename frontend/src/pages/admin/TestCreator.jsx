import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../api/axios';

export default function TestCreator() {
  const navigate = useNavigate();
  const [subjects, setSubjects] = useState([]);
  const [testName, setTestName] = useState('');
  const [testDesc, setTestDesc] = useState('');
  const [totalTime, setTotalTime] = useState(175);
  const [sections, setSections] = useState([]);
  const [availableQuestions, setAvailableQuestions] = useState({});
  const [selectedQuestions, setSelectedQuestions] = useState({});
  const [topicsBySubject, setTopicsBySubject] = useState({});
  const [sourcesList, setSourcesList] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get('/questions/subjects').then((res) => setSubjects(res.data));
    api.get('/questions/stats').then((res) => setSourcesList(res.data.sources || []));
  }, []);

  const loadTopicsForSubject = async (subjectId, source) => {
    // Always load base (unfiltered) topics for the subject
    const baseKey = `${subjectId}:`;
    if (!topicsBySubject[baseKey]) {
      try {
        const res = await api.get('/questions/topics', { params: { subject_id: subjectId } });
        setTopicsBySubject((prev) => ({ ...prev, [baseKey]: res.data }));
      } catch (e) {
        console.error('Failed to load topics', e);
      }
    }
    // Also load source-filtered topics if a source is specified
    if (source) {
      const srcKey = `${subjectId}:${source}`;
      if (!topicsBySubject[srcKey]) {
        try {
          const res = await api.get('/questions/topics', { params: { subject_id: subjectId, source_test: source } });
          setTopicsBySubject((prev) => ({ ...prev, [srcKey]: res.data }));
        } catch (e) {
          console.error('Failed to load source topics', e);
        }
      }
    }
  };

  const getTopicsForSection = (section) => {
    // Try source-filtered first, then fall back to all topics for subject
    if (section.source_test) {
      const srcKey = `${section.subject_id}:${section.source_test}`;
      if (topicsBySubject[srcKey]?.length > 0) return topicsBySubject[srcKey];
    }
    const baseKey = `${section.subject_id}:`;
    return topicsBySubject[baseKey] || [];
  };

  const addSection = () => {
    setSections([...sections, {
      subject_id: subjects[0]?.id || '',
      name: '',
      num_questions: 10,
      time_limit_minutes: 15,
      auto_pick: false,
      topic: '',
      source_test: '',
    }]);
  };

  const updateSection = (idx, field, value) => {
    setSections((prev) => {
      const updated = [...prev];
      updated[idx] = { ...updated[idx], [field]: value };
      return updated;
    });
  };

  const removeSection = (idx) => {
    setSections(sections.filter((_, i) => i !== idx));
    const key = `section-${idx}`;
    const newSelected = { ...selectedQuestions };
    delete newSelected[key];
    setSelectedQuestions(newSelected);
  };

  const loadQuestions = async (subjectId, sectionIdx, topic, source) => {
    const params = { subject_id: subjectId, limit: 200 };
    if (topic) params.topic = topic;
    if (source) params.source_test = source;
    const res = await api.get('/questions/', { params });
    setAvailableQuestions((prev) => ({ ...prev, [`section-${sectionIdx}`]: res.data }));
  };

  const toggleQuestion = (sectionIdx, questionId) => {
    const key = `section-${sectionIdx}`;
    setSelectedQuestions((prev) => {
      const current = new Set(prev[key] || []);
      if (current.has(questionId)) current.delete(questionId);
      else current.add(questionId);
      return { ...prev, [key]: [...current] };
    });
  };

  const handleCreate = async () => {
    if (!testName) { alert('Enter a test name'); return; }
    if (sections.length === 0) { alert('Add at least one section'); return; }

    setSaving(true);
    try {
      const payload = {
        name: testName,
        description: testDesc,
        time_limit_minutes: totalTime,
        sections: sections.map((s, i) => ({
          subject_id: parseInt(s.subject_id),
          name: s.name || subjects.find((sub) => sub.id === parseInt(s.subject_id))?.name || `Section ${i + 1}`,
          num_questions: parseInt(s.num_questions),
          time_limit_minutes: parseInt(s.time_limit_minutes),
          order: i + 1,
          auto_pick: s.auto_pick,
          topic: s.topic || null,
          source_test: s.source_test || null,
          question_ids: s.auto_pick ? [] : (selectedQuestions[`section-${i}`] || []),
        })),
      };
      await api.post('/tests/', payload);
      alert('Test created successfully!');
      navigate('/admin');
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to create test');
    } finally {
      setSaving(false);
    }
  };

  const inputStyle = {
    padding: '8px 10px', border: '1px solid var(--act-border)', borderRadius: 4, fontSize: 14,
  };

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '32px 20px' }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--act-blue)', marginBottom: 24 }}>Create New Test</h1>

      <div style={{ background: 'white', borderRadius: 8, padding: 24, border: '1px solid var(--act-border)', marginBottom: 24 }}>
        <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>Test Details</h3>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16, marginBottom: 16 }}>
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Test Name *</label>
            <input value={testName} onChange={(e) => setTestName(e.target.value)}
              style={{ ...inputStyle, width: '100%' }} placeholder="e.g. ACT Practice Test 1" />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Total Time (min)</label>
            <input type="number" value={totalTime} onChange={(e) => setTotalTime(e.target.value)}
              style={{ ...inputStyle, width: '100%' }} />
          </div>
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Description</label>
          <textarea value={testDesc} onChange={(e) => setTestDesc(e.target.value)}
            rows={2} style={{ ...inputStyle, width: '100%', resize: 'vertical' }} />
        </div>
      </div>

      {/* Sections */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h3 style={{ fontSize: 16, fontWeight: 700 }}>Sections</h3>
        <button onClick={addSection} style={{
          padding: '8px 16px', background: 'var(--act-blue)', color: 'white',
          border: 'none', borderRadius: 6, fontWeight: 600, cursor: 'pointer',
        }}>
          + Add Section
        </button>
      </div>

      {sections.map((section, idx) => (
        <div key={idx} style={{
          background: 'white', borderRadius: 8, padding: 20, marginBottom: 16,
          border: '1px solid var(--act-border)',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h4 style={{ fontSize: 14, fontWeight: 700, color: 'var(--act-blue)' }}>Section {idx + 1}</h4>
            <button onClick={() => removeSection(idx)} style={{
              padding: '4px 10px', border: '1px solid var(--act-red)', borderRadius: 4,
              background: 'white', color: 'var(--act-red)', fontSize: 12, cursor: 'pointer',
            }}>Remove</button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 12, marginBottom: 12 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Subject</label>
              <select value={section.subject_id} onChange={(e) => {
                updateSection(idx, 'subject_id', e.target.value);
                updateSection(idx, 'topic', '');
                loadTopicsForSubject(e.target.value, section.source_test);
                loadQuestions(e.target.value, idx, '', section.source_test);
              }} style={{ ...inputStyle, width: '100%' }}>
                <option value="">Select...</option>
                {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Section Name</label>
              <input value={section.name} onChange={(e) => updateSection(idx, 'name', e.target.value)}
                style={{ ...inputStyle, width: '100%' }} placeholder="e.g. English" />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}># Questions</label>
              <input type="number" value={section.num_questions} onChange={(e) => updateSection(idx, 'num_questions', e.target.value)}
                style={{ ...inputStyle, width: '100%' }} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Time (min)</label>
              <input type="number" value={section.time_limit_minutes} onChange={(e) => updateSection(idx, 'time_limit_minutes', e.target.value)}
                style={{ ...inputStyle, width: '100%' }} />
            </div>
          </div>

          {/* Auto-pick vs Manual pick toggle */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', gap: 16, marginBottom: 8 }}>
              <label style={{
                display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer',
                padding: '8px 14px', borderRadius: 6,
                background: section.auto_pick ? 'var(--act-blue)' : 'white',
                color: section.auto_pick ? 'white' : '#333',
                border: `1px solid ${section.auto_pick ? 'var(--act-blue)' : 'var(--act-border)'}`,
                fontWeight: 600,
              }}>
                <input type="radio" checked={section.auto_pick} onChange={() => updateSection(idx, 'auto_pick', true)}
                  style={{ display: 'none' }} />
                Auto-pick Random
              </label>
              <label style={{
                display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer',
                padding: '8px 14px', borderRadius: 6,
                background: !section.auto_pick ? 'var(--act-blue)' : 'white',
                color: !section.auto_pick ? 'white' : '#333',
                border: `1px solid ${!section.auto_pick ? 'var(--act-blue)' : 'var(--act-border)'}`,
                fontWeight: 600,
              }}>
                <input type="radio" checked={!section.auto_pick} onChange={() => updateSection(idx, 'auto_pick', false)}
                  style={{ display: 'none' }} />
                Pick Manually
              </label>
            </div>

            {/* Auto-pick filters: source + category */}
            {section.auto_pick && section.subject_id && (
              <div style={{
                background: '#f0f4ff', borderRadius: 6, padding: 14, border: '1px solid #d0d8f0',
              }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--act-blue)', marginBottom: 10 }}>
                  Filter questions for random selection:
                </div>
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                  {/* Source (PDF) Filter */}
                  {sourcesList.length > 0 && (
                    <div style={{ flex: 1, minWidth: 180 }}>
                      <label style={{ display: 'block', fontSize: 11, fontWeight: 600, marginBottom: 3, color: '#555' }}>Source (PDF)</label>
                      <select value={section.source_test || ''} onChange={(e) => {
                        updateSection(idx, 'source_test', e.target.value);
                        updateSection(idx, 'topic', '');
                        loadTopicsForSubject(section.subject_id, e.target.value);
                      }} style={{ ...inputStyle, width: '100%', fontSize: 13 }}>
                        <option value="">All Sources</option>
                        {sourcesList.map((s) => (
                          <option key={s} value={s}>{s}</option>
                        ))}
                      </select>
                    </div>
                  )}

                  {/* Category / Topic Filter */}
                  <div style={{ flex: 1, minWidth: 180 }}>
                    <label style={{ display: 'block', fontSize: 11, fontWeight: 600, marginBottom: 3, color: '#555' }}>Category / Topic</label>
                    <select value={section.topic || ''} onChange={(e) => {
                      updateSection(idx, 'topic', e.target.value);
                    }} style={{ ...inputStyle, width: '100%', fontSize: 13 }}>
                      {getTopicsForSection(section).length > 0 ? (
                        <>
                          <option value="">All Topics ({getTopicsForSection(section).reduce((s, t) => s + t.count, 0)} questions)</option>
                          {getTopicsForSection(section).map((t) => (
                            <option key={t.topic} value={t.topic}>{t.topic} ({t.count})</option>
                          ))}
                        </>
                      ) : (
                        <option value="">All Topics</option>
                      )}
                    </select>
                  </div>
                </div>

                {/* Summary */}
                <div style={{ marginTop: 10, fontSize: 12, color: '#444', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontWeight: 600 }}>Will pick:</span>
                  <span style={{
                    background: 'white', padding: '2px 10px', borderRadius: 4, border: '1px solid #d0d8f0',
                  }}>
                    {section.num_questions} random questions
                    {section.topic ? ` from "${section.topic}"` : ''}
                    {section.source_test ? ` in "${section.source_test}"` : ''}
                    {' '}
                    ({(() => {
                      const topicData = getTopicsForSection(section);
                      if (section.topic) {
                        const match = topicData.find((t) => t.topic === section.topic);
                        return match ? `${match.count} available` : '...';
                      }
                      const total = topicData.reduce((s, t) => s + t.count, 0);
                      return total > 0 ? `${total} available` : 'loading...';
                    })()})
                  </span>
                </div>
              </div>
            )}

            {/* Manual pick filters: source + category */}
            {!section.auto_pick && section.subject_id && (
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 4 }}>
                {sourcesList.length > 0 && (
                  <div style={{ flex: 1, minWidth: 180 }}>
                    <label style={{ display: 'block', fontSize: 11, fontWeight: 600, marginBottom: 3, color: '#555' }}>Source (PDF)</label>
                    <select value={section.source_test || ''} onChange={(e) => {
                      updateSection(idx, 'source_test', e.target.value);
                      updateSection(idx, 'topic', '');
                      loadTopicsForSubject(section.subject_id, e.target.value);
                      loadQuestions(section.subject_id, idx, '', e.target.value);
                    }} style={{ ...inputStyle, width: '100%', fontSize: 13 }}>
                      <option value="">All Sources</option>
                      {sourcesList.map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </div>
                )}
                {getTopicsForSection(section).length > 0 && (
                  <div style={{ flex: 1, minWidth: 180 }}>
                    <label style={{ display: 'block', fontSize: 11, fontWeight: 600, marginBottom: 3, color: '#555' }}>Category / Topic</label>
                    <select value={section.topic || ''} onChange={(e) => {
                      updateSection(idx, 'topic', e.target.value);
                      loadQuestions(section.subject_id, idx, e.target.value, section.source_test);
                    }} style={{ ...inputStyle, width: '100%', fontSize: 13 }}>
                      <option value="">All Topics ({getTopicsForSection(section).reduce((s, t) => s + t.count, 0)} questions)</option>
                      {getTopicsForSection(section).map((t) => (
                        <option key={t.topic} value={t.topic}>{t.topic} ({t.count})</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
            )}
          </div>

          {!section.auto_pick && section.subject_id && (
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
                Select Questions ({(selectedQuestions[`section-${idx}`] || []).length} selected)
                <button onClick={() => loadQuestions(section.subject_id, idx, section.topic, section.source_test)} style={{
                  marginLeft: 8, padding: '2px 8px', border: '1px solid var(--act-border)',
                  borderRadius: 3, background: 'white', fontSize: 11, cursor: 'pointer',
                }}>Refresh</button>
              </div>
              <div style={{
                maxHeight: 200, overflowY: 'auto', border: '1px solid var(--act-border)',
                borderRadius: 4, padding: 8,
              }}>
                {(availableQuestions[`section-${idx}`] || []).map((q) => {
                  const isSelected = (selectedQuestions[`section-${idx}`] || []).includes(q.id);
                  return (
                    <label key={q.id} style={{
                      display: 'flex', alignItems: 'flex-start', gap: 8, padding: '6px 4px',
                      fontSize: 13, cursor: 'pointer', background: isSelected ? '#e8eaf6' : 'transparent',
                      borderRadius: 3,
                    }}>
                      <input type="checkbox" checked={isSelected} onChange={() => toggleQuestion(idx, q.id)} style={{ marginTop: 2 }} />
                      <span>
                        <strong>#{q.id}</strong> {q.question_text.substring(0, 100)}{q.question_text.length > 100 ? '...' : ''}
                        {q.topic && <span style={{
                          background: '#e3f2fd', color: '#1565c0', fontSize: 10, padding: '1px 6px',
                          borderRadius: 3, marginLeft: 6, fontWeight: 600,
                        }}>{q.topic}</span>}
                        <span style={{ color: '#999', fontSize: 11, marginLeft: 6 }}>D:{q.difficulty}</span>
                      </span>
                    </label>
                  );
                })}
                {(!availableQuestions[`section-${idx}`] || availableQuestions[`section-${idx}`].length === 0) && (
                  <div style={{ padding: 12, textAlign: 'center', color: '#999', fontSize: 13 }}>
                    No questions loaded. Click Refresh or select a subject.
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      ))}

      {sections.length === 0 && (
        <div style={{
          background: 'white', borderRadius: 8, padding: 40, textAlign: 'center',
          border: '1px dashed var(--act-border)', color: '#999', marginBottom: 20,
        }}>
          Click "Add Section" to start building your test
        </div>
      )}

      <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', marginTop: 20 }}>
        <button onClick={() => navigate('/admin')} style={{
          padding: '12px 24px', border: '1px solid var(--act-border)', borderRadius: 6,
          background: 'white', fontWeight: 600, cursor: 'pointer',
        }}>Cancel</button>
        <button onClick={handleCreate} disabled={saving} style={{
          padding: '12px 32px', border: 'none', borderRadius: 6,
          background: 'var(--act-green)', color: 'white', fontWeight: 700, cursor: 'pointer',
          opacity: saving ? 0.7 : 1,
        }}>
          {saving ? 'Creating...' : 'Create Test'}
        </button>
      </div>
    </div>
  );
}
