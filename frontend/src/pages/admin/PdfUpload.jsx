import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../api/axios';
import { useUpload } from '../../context/UploadContext';

const sectionColors = {
  English: '#1565c0',
  Math: '#2e7d32',
  Reading: '#6a1b9a',
  Science: '#e65100',
  Unknown: '#616161',
};

function computeProgress(progress) {
  const lastEvent = progress[progress.length - 1];
  const totalSections = lastEvent?.total_sections || 4;
  const classifiedSections = progress.filter(p => p.step === 'classified').length;
  const classifyingSections = progress.filter(p => p.step === 'classifying').length;
  const explainedSections = progress.filter(p => p.step === 'explained').length;
  const explainingSections = progress.filter(p => p.step === 'explaining').length;
  const isDone = progress.some(p => p.step === 'done');

  let pct = 5;
  let phase = 'Uploading...';
  if (progress.some(p => p.step === 'parsed')) { pct = 10; phase = 'PDF parsed'; }
  if (classifyingSections > 0) {
    pct = 10 + (classifiedSections / totalSections) * 40;
    const d = progress.filter(p => p.step === 'classifying_detail').pop();
    phase = d ? d.message : `Classifying topics (${classifiedSections}/${totalSections})`;
  }
  if (classifiedSections === totalSections) { pct = 50; phase = 'Topics classified'; }
  if (explainingSections > 0) {
    const d = progress.filter(p => p.step === 'explaining_detail').pop();
    if (d && d.question_total) {
      pct = 50 + (explainedSections / totalSections) * 45 + (d.question_index / d.question_total) * (45 / totalSections);
      phase = d.message;
    } else {
      pct = 50 + (explainedSections / totalSections) * 45;
      phase = `Generating explanations (${explainedSections}/${totalSections})`;
    }
  }
  if (isDone) { pct = 100; phase = 'Complete!'; }

  return { pct, phase, isDone, totalSections, classifiedSections, classifyingSections, explainedSections, explainingSections };
}

// Individual upload card component
function UploadCard({ upload, onRemove }) {
  const navigate = useNavigate();
  const { updateUpload, setParsedData, removeUpload } = useUpload();
  const [importing, setImporting] = useState(false);
  const [expandedSections, setExpandedSections] = useState(new Set());
  const [expandedQuestions, setExpandedQuestions] = useState(new Set());
  const progressRef = useRef(null);

  const { id, filename, uploading, progress, parsedData, error, testName } = upload;

  useEffect(() => {
    if (progressRef.current) {
      progressRef.current.scrollTop = progressRef.current.scrollHeight;
    }
  }, [progress]);

  useEffect(() => {
    if (parsedData && !expandedSections.size) {
      setExpandedSections(new Set(parsedData.sections?.map((_, i) => i) || []));
    }
  }, [parsedData]);

  const updateQuestion = (sectionIdx, questionIdx, field, value) => {
    setParsedData(id, (prev) => {
      const updated = { ...prev, sections: [...prev.sections] };
      updated.sections[sectionIdx] = {
        ...updated.sections[sectionIdx],
        questions: [...updated.sections[sectionIdx].questions],
      };
      updated.sections[sectionIdx].questions[questionIdx] = {
        ...updated.sections[sectionIdx].questions[questionIdx],
        [field]: value,
      };
      return updated;
    });
  };

  const removeQuestion = (sectionIdx, questionIdx) => {
    setParsedData(id, (prev) => {
      const updated = { ...prev, sections: [...prev.sections] };
      updated.sections[sectionIdx] = {
        ...updated.sections[sectionIdx],
        questions: updated.sections[sectionIdx].questions.filter((_, i) => i !== questionIdx),
      };
      return updated;
    });
  };

  const handleImport = async () => {
    if (!testName) { alert('Enter a test name'); return; }
    if (!parsedData?.sections?.length) { alert('No sections to import'); return; }
    setImporting(true);
    try {
      const payload = {
        test_name: testName,
        source_test: upload.sourceTest || testName,
        sections: parsedData.sections.map((s) => ({
          name: s.name,
          time_limit_minutes: s.time_limit_minutes,
          questions: s.questions.map((q) => ({
            question_number: q.question_number,
            question_text: q.question_text || '',
            option_a: q.option_a || 'A',
            option_b: q.option_b || 'B',
            option_c: q.option_c || 'C',
            option_d: q.option_d || 'D',
            option_e: q.option_e || undefined,
            correct_answer: q.correct_answer || undefined,
            option_labels: q.option_labels || 'ABCDE',
            passage_text: q.passage_text || undefined,
            passage_image: q.passage_image || undefined,
            question_image: q.question_image || undefined,
            topic: q.topic || undefined,
            explanation: q.explanation || undefined,
            difficulty: q.difficulty || 3,
          })),
        })),
      };
      const res = await api.post('/admin/import-test', payload);
      alert(`${res.data.message}\n\n${res.data.total_questions} questions imported across ${res.data.sections.length} sections.`);
      removeUpload(id);
    } catch (err) {
      alert(err.response?.data?.detail || 'Import failed');
    } finally {
      setImporting(false);
    }
  };

  const toggleSection = (idx) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx); else next.add(idx);
      return next;
    });
  };

  const toggleQuestionDetail = (key) => {
    setExpandedQuestions((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  const prog = computeProgress(progress || []);

  return (
    <div style={{
      background: 'white', borderRadius: 12, marginBottom: 24,
      border: `1px solid ${error ? '#ef9a9a' : 'var(--act-border)'}`,
      boxShadow: '0 2px 8px rgba(0,0,0,0.06)', overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '16px 20px', display: 'flex', justifyContent: 'space-between',
        alignItems: 'center', borderBottom: '1px solid #eee',
        background: prog.isDone ? '#f1f8e9' : uploading ? '#e3f2fd' : error ? '#fce4ec' : '#fafafa',
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--act-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {filename}
          </div>
          <div style={{ fontSize: 12, color: 'var(--act-dark-gray)', marginTop: 2 }}>
            {error ? `Error: ${error}` : uploading ? prog.phase : prog.isDone ? 'Ready to import' : 'Waiting...'}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {uploading && (
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--act-blue)' }}>
              {Math.round(prog.pct)}%
            </span>
          )}
          <button
            onClick={() => onRemove(id)}
            style={{
              border: 'none', background: 'none', color: '#999', fontSize: 20,
              cursor: 'pointer', padding: '0 4px', lineHeight: 1,
            }}
            title="Remove"
          >&times;</button>
        </div>
      </div>

      {/* Progress Bar */}
      {(uploading || progress.length > 0) && !parsedData && !error && (
        <div style={{ padding: '12px 20px' }}>
          <div style={{ height: 6, background: '#e0e0e0', borderRadius: 3, overflow: 'hidden', marginBottom: 8 }}>
            <div style={{
              height: '100%', borderRadius: 3, transition: 'width 0.5s ease',
              background: prog.isDone ? 'var(--act-green, #2e7d32)' : 'var(--act-blue)',
              width: `${prog.pct}%`,
            }} />
          </div>
          {/* Phase Steps */}
          <div style={{ display: 'flex', gap: 0 }}>
            {[
              { key: 'parse', label: 'Parse', done: progress.some(p => p.step === 'parsed') },
              { key: 'classify', label: 'Topics', done: prog.classifiedSections === prog.totalSections, active: prog.classifyingSections > 0 },
              { key: 'explain', label: 'Explanations', done: prog.explainedSections === prog.totalSections, active: prog.explainingSections > 0 },
              { key: 'done', label: 'Done', done: prog.isDone },
            ].map((phase, idx) => (
              <div key={phase.key} style={{ flex: 1, textAlign: 'center' }}>
                <div style={{
                  width: 22, height: 22, borderRadius: '50%', margin: '0 auto 4px',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 11, fontWeight: 700,
                  background: phase.done ? 'var(--act-green, #2e7d32)' : phase.active ? 'var(--act-blue)' : '#e0e0e0',
                  color: (phase.done || phase.active) ? 'white' : '#999',
                }}>
                  {phase.done ? '\u2713' : idx + 1}
                </div>
                <div style={{
                  fontSize: 10, fontWeight: phase.active ? 700 : 500,
                  color: phase.done ? 'var(--act-green, #2e7d32)' : phase.active ? 'var(--act-blue)' : '#999',
                }}>{phase.label}</div>
              </div>
            ))}
          </div>
          {/* Detailed Log */}
          <details style={{ marginTop: 8 }}>
            <summary style={{ cursor: 'pointer', fontSize: 11, color: '#999', userSelect: 'none' }}>
              Log ({progress.length} events)
            </summary>
            <div ref={progressRef} style={{
              background: '#1a1a2e', borderRadius: 6, padding: 8, marginTop: 4,
              fontFamily: 'monospace', fontSize: 11, color: '#e0e0e0',
              maxHeight: 120, overflowY: 'auto',
            }}>
              {progress.map((p, i) => (
                <div key={i} style={{ padding: '1px 0', opacity: i === progress.length - 1 ? 1 : 0.6 }}>
                  {p.step === 'done' ? '\u2705' : p.step.endsWith('ed') ? '\u2714' : '\u23F3'} {p.message}
                </div>
              ))}
            </div>
          </details>
        </div>
      )}

      {/* Parsed Results */}
      {parsedData && (
        <div style={{ padding: '0 20px 20px' }}>
          {/* Summary */}
          <div style={{
            background: 'var(--act-blue)', color: 'white', borderRadius: 8, padding: 14, marginTop: 12, marginBottom: 16,
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8,
          }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 2 }}>
                {parsedData.sections.length} Sections — {parsedData.total_questions || parsedData.sections.reduce((s, sec) => s + sec.questions.length, 0)} questions
              </div>
              {parsedData.answers_extracted > 0 && (
                <span style={{ fontSize: 12, opacity: 0.85 }}>{parsedData.answers_extracted} answers extracted</span>
              )}
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              {parsedData.sections.map((s, i) => (
                <span key={i} style={{
                  background: 'rgba(255,255,255,0.2)', padding: '3px 10px',
                  borderRadius: 4, fontSize: 12, fontWeight: 500,
                }}>
                  {s.name}: {s.questions.length}q
                </span>
              ))}
            </div>
          </div>

          {/* Test Name & Import */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap',
          }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <label style={{ display: 'block', fontSize: 11, fontWeight: 600, marginBottom: 3 }}>Test Name</label>
              <input
                value={testName}
                onChange={(e) => updateUpload(id, { testName: e.target.value })}
                style={{ width: '100%', padding: '8px 10px', border: '2px solid var(--act-border)', borderRadius: 6, fontSize: 14 }}
                placeholder="e.g. ACT Practice Test - June 2020"
              />
            </div>
            <button onClick={handleImport} disabled={importing} style={{
              padding: '10px 24px', background: 'var(--act-green)', color: 'white',
              border: 'none', borderRadius: 8, fontWeight: 700, fontSize: 14, cursor: 'pointer',
              opacity: importing ? 0.7 : 1, whiteSpace: 'nowrap', marginTop: 16,
            }}>
              {importing ? 'Importing...' : 'Import & Create Test'}
            </button>
          </div>

          {/* Sections */}
          {parsedData.sections.map((section, sIdx) => {
            const isExpanded = expandedSections.has(sIdx);
            const color = sectionColors[section.name] || sectionColors.Unknown;

            return (
              <div key={sIdx} style={{
                background: 'white', borderRadius: 8, marginBottom: 12,
                border: '1px solid var(--act-border)', overflow: 'hidden',
              }}>
                {/* Section Header */}
                <div
                  onClick={() => toggleSection(sIdx)}
                  style={{
                    padding: '12px 16px', cursor: 'pointer',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    borderLeft: `4px solid ${color}`,
                    background: isExpanded ? '#fafafa' : 'white',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontSize: 16, color: '#999' }}>{isExpanded ? '\u25BC' : '\u25B6'}</span>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 700, color }}>{section.name}</div>
                      <div style={{ fontSize: 12, color: 'var(--act-dark-gray)' }}>
                        {section.questions.length} questions | {section.time_limit_minutes} min
                        {section.images_count > 0 && ` | ${section.images_count} images`}
                      </div>
                    </div>
                  </div>
                  <span style={{
                    background: color, color: 'white', padding: '3px 10px',
                    borderRadius: 12, fontSize: 12, fontWeight: 600,
                  }}>
                    {section.questions.length} Qs
                  </span>
                </div>

                {/* Section Questions */}
                {isExpanded && (
                  <div style={{ padding: '0 16px 12px' }}>
                    {section.questions.map((q, qIdx) => {
                      const qKey = `${id}-${sIdx}-${qIdx}`;
                      const isQExpanded = expandedQuestions.has(qKey);

                      return (
                        <div key={qIdx} style={{
                          border: '1px solid #eee', borderRadius: 6, marginTop: 6, overflow: 'hidden',
                        }}>
                          <div
                            style={{
                              padding: '8px 12px', display: 'flex', alignItems: 'center', gap: 8,
                              background: '#fafafa', cursor: 'pointer',
                            }}
                            onClick={() => toggleQuestionDetail(qKey)}
                          >
                            <span style={{
                              background: color, color: 'white', width: 24, height: 24, borderRadius: '50%',
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              fontSize: 11, fontWeight: 700, flexShrink: 0,
                            }}>
                              {q.question_number}
                            </span>
                            <span style={{ flex: 1, fontSize: 12, color: '#333', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {q.question_text || '(no text)'}
                            </span>
                            {q.question_image && (
                              <span style={{ fontSize: 10, background: '#e3f2fd', color: '#1565c0', padding: '1px 5px', borderRadius: 3, flexShrink: 0 }}>IMG</span>
                            )}
                            {(q.passage_text || q.passage_image) && (
                              <span style={{ fontSize: 10, background: '#f3e5f5', color: '#6a1b9a', padding: '1px 5px', borderRadius: 3, flexShrink: 0 }}>
                                {q.passage_image ? 'P-IMG' : 'P'}
                              </span>
                            )}
                            {q.correct_answer && (
                              <span style={{ fontSize: 10, background: '#e8f5e9', color: '#2e7d32', padding: '1px 5px', borderRadius: 3, flexShrink: 0 }}>{q.correct_answer}</span>
                            )}
                            <select
                              value={q.correct_answer || ''}
                              onChange={(e) => { e.stopPropagation(); updateQuestion(sIdx, qIdx, 'correct_answer', e.target.value); }}
                              onClick={(e) => e.stopPropagation()}
                              style={{ padding: '2px 4px', border: '1px solid #ddd', borderRadius: 3, fontSize: 11, width: 45 }}
                            >
                              <option value="">Ans</option>
                              {(q.option_labels === 'FGHJK' ? ['F', 'G', 'H', 'J', 'K'] : ['A', 'B', 'C', 'D', 'E']).map((l) => <option key={l} value={l}>{l}</option>)}
                            </select>
                            <button
                              onClick={(e) => { e.stopPropagation(); removeQuestion(sIdx, qIdx); }}
                              style={{ border: 'none', background: 'none', color: '#c62828', fontSize: 14, cursor: 'pointer', padding: '0 2px' }}
                              title="Remove question"
                            >
                              &times;
                            </button>
                          </div>

                          {isQExpanded && (
                            <div style={{ padding: 12, borderTop: '1px solid #eee' }}>
                              {q.question_image && (
                                <div style={{ marginBottom: 10 }}>
                                  <div style={{ fontSize: 10, fontWeight: 600, color: '#999', marginBottom: 3 }}>DIAGRAM/IMAGE</div>
                                  <img src={q.question_image} alt={`Q${q.question_number}`}
                                    style={{ maxWidth: '100%', maxHeight: 200, borderRadius: 4, border: '1px solid #eee' }} />
                                </div>
                              )}
                              {q.passage_image && (
                                <div style={{ marginBottom: 10 }}>
                                  <div style={{ fontSize: 10, fontWeight: 600, color: '#999', marginBottom: 3 }}>PASSAGE (rendered)</div>
                                  <img src={q.passage_image} alt="Passage"
                                    style={{ width: '100%', borderRadius: 4, border: '1px solid #eee' }} />
                                </div>
                              )}
                              {q.passage_text && (
                                <details style={{ marginBottom: 10 }}>
                                  <summary style={{ fontSize: 10, fontWeight: 600, color: '#999', cursor: 'pointer' }}>
                                    PASSAGE TEXT {q.passage_image ? '(fallback)' : ''}
                                  </summary>
                                  <textarea
                                    value={q.passage_text}
                                    onChange={(e) => updateQuestion(sIdx, qIdx, 'passage_text', e.target.value)}
                                    rows={3} style={{ width: '100%', padding: 6, border: '1px solid #ddd', borderRadius: 4, fontSize: 11, resize: 'vertical', background: '#fafafa', marginTop: 3 }}
                                  />
                                </details>
                              )}
                              <div style={{ marginBottom: 8 }}>
                                <div style={{ fontSize: 10, fontWeight: 600, color: '#999', marginBottom: 3 }}>QUESTION TEXT</div>
                                <textarea
                                  value={q.question_text}
                                  onChange={(e) => updateQuestion(sIdx, qIdx, 'question_text', e.target.value)}
                                  rows={2} style={{ width: '100%', padding: 6, border: '1px solid #ddd', borderRadius: 4, fontSize: 12, resize: 'vertical' }}
                                />
                              </div>
                              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
                                {['option_a', 'option_b', 'option_c', 'option_d', 'option_e'].map((key, i) => {
                                  if (key === 'option_e' && !q.option_e) return null;
                                  const labels = q.option_labels === 'FGHJK' ? ['F', 'G', 'H', 'J', 'K'] : ['A', 'B', 'C', 'D', 'E'];
                                  return (
                                    <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                      <strong style={{ fontSize: 12, color, width: 14 }}>{labels[i]}.</strong>
                                      <input
                                        value={q[key] || ''}
                                        onChange={(e) => updateQuestion(sIdx, qIdx, key, e.target.value)}
                                        style={{ flex: 1, padding: '3px 6px', border: '1px solid #ddd', borderRadius: 3, fontSize: 11 }}
                                      />
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}


export default function PdfUpload() {
  const navigate = useNavigate();
  const { uploads, startUpload, removeUpload, cancelUpload } = useUpload();
  const [selectedSections, setSelectedSections] = useState({ English: true, Math: true, Reading: true, Science: true });
  const [skipTopics, setSkipTopics] = useState(false);
  const [skipExplanations, setSkipExplanations] = useState(false);
  const [sourceTest, setSourceTest] = useState('');
  const fileRef = useRef(null);

  const handleFilesSelected = (files) => {
    const activeSections = Object.entries(selectedSections).filter(([, v]) => v).map(([k]) => k);
    const options = {};
    if (activeSections.length < 4) options.sectionsFilter = activeSections.join(',');
    if (skipTopics) options.skipTopics = true;
    if (skipExplanations) options.skipExplanations = true;

    for (const file of files) {
      if (!file.name.toLowerCase().endsWith('.pdf')) continue;
      const name = sourceTest || file.name.replace(/\.pdf$/i, '');
      startUpload(file, name, options);
    }
    // Reset source after batch start
    setSourceTest('');
    if (fileRef.current) fileRef.current.value = '';
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const files = Array.from(e.dataTransfer.files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
    if (files.length) handleFilesSelected(files);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const uploadList = Object.values(uploads);

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: '32px 20px' }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--act-blue)', marginBottom: 24 }}>Upload ACT PDFs</h1>

      {/* Upload Area */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        style={{
          background: 'white', borderRadius: 8, padding: 32, marginBottom: 24,
          border: '2px dashed var(--act-border)', textAlign: 'center',
        }}
      >
        <input
          ref={fileRef}
          type="file"
          accept=".pdf"
          multiple
          onChange={(e) => {
            if (e.target.files.length) handleFilesSelected(Array.from(e.target.files));
          }}
          style={{ display: 'none' }}
        />
        <div onClick={() => fileRef.current?.click()} style={{ cursor: 'pointer', padding: 20 }}>
          <div style={{ fontSize: 40, color: 'var(--act-border)', marginBottom: 12 }}>PDF</div>
          <p style={{ fontSize: 16, color: 'var(--act-dark-gray)', marginBottom: 8 }}>
            Click to select one or more ACT PDFs, or drag & drop
          </p>
          <p style={{ fontSize: 13, color: '#999' }}>
            Multiple PDFs will be processed in parallel
          </p>
        </div>

        {/* Parsing Options */}
        <div style={{
          marginTop: 16, padding: '16px 20px', background: '#f5f7fa',
          borderRadius: 8, border: '1px solid var(--act-border)', textAlign: 'left',
          maxWidth: 520, marginLeft: 'auto', marginRight: 'auto',
        }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--act-dark-gray)', marginBottom: 12 }}>
            Parsing Options
          </div>

          {/* Section Selection */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: '#666', marginBottom: 6 }}>Sections to extract:</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {['English', 'Math', 'Reading', 'Science'].map((sec) => (
                <label key={sec} style={{
                  display: 'flex', alignItems: 'center', gap: 5,
                  padding: '4px 10px', borderRadius: 4, cursor: 'pointer', fontSize: 13,
                  background: selectedSections[sec] ? sectionColors[sec] + '18' : '#eee',
                  border: `1px solid ${selectedSections[sec] ? sectionColors[sec] : '#ccc'}`,
                  color: selectedSections[sec] ? sectionColors[sec] : '#999',
                  fontWeight: selectedSections[sec] ? 600 : 400,
                }}>
                  <input
                    type="checkbox"
                    checked={selectedSections[sec]}
                    onChange={(e) => setSelectedSections(prev => ({ ...prev, [sec]: e.target.checked }))}
                    style={{ accentColor: sectionColors[sec] }}
                  />
                  {sec}
                </label>
              ))}
            </div>
          </div>

          {/* LLM Processing Options */}
          <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer', color: '#444' }}>
              <input type="checkbox" checked={skipTopics} onChange={(e) => setSkipTopics(e.target.checked)} />
              Skip topic classification
              <span style={{ fontSize: 11, color: '#999' }}>(faster)</span>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer', color: '#444' }}>
              <input type="checkbox" checked={skipExplanations} onChange={(e) => setSkipExplanations(e.target.checked)} />
              Skip explanation generation
              <span style={{ fontSize: 11, color: '#999' }}>(much faster)</span>
            </label>
          </div>
        </div>
      </div>

      {/* Upload Cards */}
      {uploadList.length > 0 && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--act-text)', margin: 0 }}>
              Uploads ({uploadList.length})
            </h2>
            {uploadList.length > 1 && (
              <div style={{ fontSize: 13, color: 'var(--act-dark-gray)' }}>
                {uploadList.filter(u => u.uploading).length} processing, {uploadList.filter(u => u.parsedData).length} ready
              </div>
            )}
          </div>
          {uploadList.map((upload) => (
            <UploadCard
              key={upload.id}
              upload={upload}
              onRemove={(id) => {
                cancelUpload(id);
                removeUpload(id);
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
