import { useState, useEffect, useCallback } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import api from '../api/axios';
import Timer from '../components/Timer';
import QuestionCard from '../components/QuestionCard';
import QuestionNavigator from '../components/QuestionNavigator';

const SESSION_KEY = (testId) => `act_session_${testId}`;

function saveSession(testId, data) {
  try {
    localStorage.setItem(SESSION_KEY(testId), JSON.stringify(data));
  } catch {}
}

function loadSession(testId) {
  try {
    const raw = localStorage.getItem(SESSION_KEY(testId));
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function clearSession(testId) {
  try { localStorage.removeItem(SESSION_KEY(testId)); } catch {}
}

export default function TestTaking() {
  const { testId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();

  // Recover attemptId from location state OR localStorage
  const savedSession = loadSession(testId);
  const attemptId = location.state?.attemptId || savedSession?.attemptId;

  const [test, setTest] = useState(null);
  const [currentSectionIdx, setCurrentSectionIdx] = useState(savedSession?.sectionIdx ?? 0);
  const [currentQuestionIdx, setCurrentQuestionIdx] = useState(savedSession?.questionIdx ?? 0);
  const [answers, setAnswers] = useState({});
  const [markedForReview, setMarkedForReview] = useState(
    new Set(savedSession?.marked || [])
  );
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [confirmType, setConfirmType] = useState(null); // 'section' or 'test'

  function findSectionForQuestion(testData, questionId) {
    for (const s of testData.sections) {
      if (s.questions?.some(q => q.id === questionId)) return s.id;
    }
    return null;
  }

  useEffect(() => {
    if (!attemptId) {
      navigate('/tests');
      return;
    }

    // Save attemptId to localStorage immediately
    saveSession(testId, {
      attemptId,
      sectionIdx: savedSession?.sectionIdx ?? 0,
      questionIdx: savedSession?.questionIdx ?? 0,
      marked: savedSession?.marked || [],
    });

    // Load test data and existing answers in parallel
    Promise.all([
      api.get(`/tests/${testId}`),
      api.get(`/tests/attempts/${attemptId}/answers`).catch(() => ({ data: [] })),
    ])
      .then(([testRes, answersRes]) => {
        const testData = testRes.data;
        setTest(testData);

        // Rebuild answers map from saved answers
        if (answersRes.data?.length) {
          const restored = {};
          for (const a of answersRes.data) {
            const sectionId = a.section_id || findSectionForQuestion(testData, a.question_id);
            if (sectionId && a.selected_answer) {
              restored[`${sectionId}-${a.question_id}`] = a.selected_answer;
            }
          }
          setAnswers(prev => ({ ...prev, ...restored }));
        }
      })
      .catch(() => navigate('/tests'))
      .finally(() => setLoading(false));
  }, [testId, attemptId]);

  // Persist session state on navigation changes
  useEffect(() => {
    if (!attemptId) return;
    saveSession(testId, {
      attemptId,
      sectionIdx: currentSectionIdx,
      questionIdx: currentQuestionIdx,
      marked: [...markedForReview],
    });
  }, [currentSectionIdx, currentQuestionIdx, markedForReview, attemptId, testId]);

  const currentSection = test?.sections?.[currentSectionIdx];
  const questions = currentSection?.questions || [];
  const currentQuestion = questions[currentQuestionIdx];
  const totalQuestions = questions.length;

  const sectionKey = (qId) => `${currentSection?.id}-${qId}`;

  const questionNumbers = questions.map((q) => q.question_number || 0);

  const answeredSet = new Set(
    questions
      .map((q) => answers[sectionKey(q.id)] ? (q.question_number || 0) : null)
      .filter(Boolean)
  );

  const markedSet = new Set(
    [...markedForReview].filter(k => k.startsWith(`${currentSection?.id}-`))
      .map(k => {
        const qId = parseInt(k.split('-')[1]);
        const q = questions.find(q => q.id === qId);
        return q?.question_number || 0;
      })
      .filter(n => n > 0)
  );

  const handleSelectAnswer = useCallback(async (label) => {
    if (!currentQuestion || !attemptId) return;
    const key = sectionKey(currentQuestion.id);
    setAnswers((prev) => ({ ...prev, [key]: label }));

    try {
      await api.post(`/tests/attempts/${attemptId}/answer`, {
        question_id: currentQuestion.id,
        selected_answer: label,
        section_id: currentSection.id,
      });
    } catch (err) {
      console.error('Failed to save answer:', err);
    }
  }, [currentQuestion, attemptId, currentSection]);

  const handleTimeUp = useCallback(() => {
    if (currentSectionIdx < (test?.sections?.length || 1) - 1) {
      moveToNextSection();
    } else {
      handleCompleteTest();
    }
  }, [currentSectionIdx, test]);

  const moveToNextSection = () => {
    setCurrentSectionIdx((prev) => prev + 1);
    setCurrentQuestionIdx(0);
    setShowConfirm(false);
  };

  const handleCompleteTest = async () => {
    setSubmitting(true);
    try {
      await api.post(`/tests/attempts/${attemptId}/complete`);
      clearSession(testId);
      // Clean up timer keys
      test?.sections?.forEach(s => {
        try { localStorage.removeItem(`act_timer_${attemptId}_${s.id}`); } catch {}
      });
      navigate(`/tests/${testId}/results/${attemptId}`);
    } catch (err) {
      alert('Failed to submit test');
      setSubmitting(false);
    }
  };

  const handleConfirmAction = () => {
    if (confirmType === 'section') {
      moveToNextSection();
    } else {
      handleCompleteTest();
    }
  };

  const toggleMark = () => {
    if (!currentQuestion) return;
    const key = sectionKey(currentQuestion.id);
    setMarkedForReview((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 80, fontSize: 18, color: '#666' }}>Loading test...</div>;
  }

  if (!test || !currentSection) {
    return <div style={{ textAlign: 'center', padding: 80 }}>Test not found.</div>;
  }

  const isMarked = currentQuestion && markedForReview.has(sectionKey(currentQuestion.id));
  const isLastSection = currentSectionIdx >= test.sections.length - 1;
  const isEnglish = currentSection?.name === 'English';
  const isMath = currentSection?.name === 'Math';

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: '#f5f5f5' }}>
      {/* Top Bar */}
      <div style={{
        background: 'var(--act-blue)',
        color: 'white',
        padding: '0 20px',
        height: 56,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <span style={{
            background: 'white',
            color: 'var(--act-blue)',
            padding: '2px 10px',
            borderRadius: 4,
            fontWeight: 800,
            fontSize: 16,
          }}>ACT</span>
          <span style={{ fontWeight: 600, fontSize: 15 }}>{test.name}</span>
          <span style={{
            background: 'rgba(255,255,255,0.2)',
            padding: '4px 12px',
            borderRadius: 4,
            fontSize: 13,
          }}>
            {currentSection.name || `Section ${currentSectionIdx + 1}`}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <span style={{ fontSize: 14, opacity: 0.9 }}>
            Question {currentQuestionIdx + 1} of {totalQuestions}
          </span>
          <Timer
            key={currentSection.id}
            totalSeconds={currentSection.time_limit_minutes * 60}
            onTimeUp={handleTimeUp}
            storageKey={`act_timer_${attemptId}_${currentSection.id}`}
          />
        </div>
      </div>

      {/* Section tabs */}
      <div style={{
        background: 'var(--act-light-blue)',
        color: 'rgba(255,255,255,0.9)',
        padding: '6px 20px',
        fontSize: 12,
        display: 'flex',
        gap: 4,
      }}>
        {test.sections.map((s, i) => (
          <button
            key={s.id}
            onClick={() => {
              setCurrentSectionIdx(i);
              setCurrentQuestionIdx(0);
            }}
            style={{
              padding: '4px 14px',
              borderRadius: 4,
              border: 'none',
              background: i === currentSectionIdx ? 'rgba(255,255,255,0.3)' : 'transparent',
              fontWeight: i === currentSectionIdx ? 700 : 400,
              color: 'white',
              fontSize: 13,
              cursor: 'pointer',
              textDecoration: i === currentSectionIdx ? 'none' : 'underline',
              textUnderlineOffset: 3,
            }}
          >
            {s.name || `Section ${i + 1}`}
          </button>
        ))}
      </div>

      {/* Main Content */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Math Question Image Pane (left) */}
        {isMath && currentQuestion?.question_image && (
          <div style={{
            width: '55%',
            borderRight: '2px solid var(--act-border)',
            background: '#fafafa',
            display: 'flex',
            flexDirection: 'column',
            flexShrink: 0,
          }}>
            <div style={{
              padding: '10px 20px',
              background: 'var(--act-blue)',
              color: 'white',
              flexShrink: 0,
            }}>
              <div style={{ fontWeight: 700, fontSize: 13, letterSpacing: 0.5, textTransform: 'uppercase' }}>
                Question {currentQuestion?.question_number || currentQuestionIdx + 1}
              </div>
            </div>
            <div style={{
              flex: 1,
              overflowY: 'auto',
              padding: '12px 8px',
            }}>
              <img
                src={currentQuestion.question_image}
                alt="Question"
                style={{ maxWidth: '75%', width: '75%', height: 'auto', imageRendering: 'auto', display: 'block', margin: '0 auto' }}
              />
            </div>
          </div>
        )}

        {/* Passage Pane (left) - only shown when question has a passage */}
        {!isMath && (currentQuestion?.passage_text || currentQuestion?.passage_image) && (() => {
          const lines = (currentQuestion.passage_text || '').split('\n');
          const passageHeader = lines[0] || '';
          const passageTitle = (lines[1] && !lines[1].match(/^\[/)) ? lines[1] : '';
          const passageBody = lines.slice(passageTitle ? 2 : 1).join('\n').trim();
          const hasImage = !!currentQuestion.passage_image;
          return (
            <div style={{
              width: '45%',
              borderRight: '2px solid var(--act-border)',
              background: '#fafafa',
              display: 'flex',
              flexDirection: 'column',
              flexShrink: 0,
            }}>
              <div style={{
                padding: '10px 20px',
                background: 'var(--act-blue)',
                color: 'white',
                flexShrink: 0,
              }}>
                <div style={{ fontWeight: 700, fontSize: 13, letterSpacing: 0.5, textTransform: 'uppercase' }}>
                  {passageHeader}
                </div>
                {passageTitle && (
                  <div style={{ fontSize: 14, fontStyle: 'italic', marginTop: 2, opacity: 0.9 }}>
                    {passageTitle}
                  </div>
                )}
              </div>
              <div style={{
                flex: 1,
                overflowY: 'auto',
                padding: hasImage ? '12px 8px' : '20px 24px',
                fontSize: 14,
                lineHeight: 1.85,
                color: '#333',
              }}>
                {hasImage ? (
                  <img
                    src={currentQuestion.passage_image}
                    alt="Passage"
                    style={{ maxWidth: isEnglish ? '75%' : '100%', width: isEnglish ? '75%' : '100%', height: 'auto', imageRendering: 'auto', display: 'block', margin: isEnglish ? '0 auto' : undefined }}
                  />
                ) : (
                  <div style={{ whiteSpace: 'pre-wrap' }}>{passageBody}</div>
                )}
              </div>
            </div>
          );
        })()}

        {/* Question Area (right, or full-width if no passage) */}
        <div style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}>
          <div style={{
            flex: 1,
            padding: isEnglish ? '16px 20px' : 32,
            overflowY: 'auto',
            background: 'white',
          }}>
            <QuestionCard
              question={currentQuestion}
              selectedAnswer={currentQuestion ? answers[sectionKey(currentQuestion.id)] : null}
              onSelectAnswer={handleSelectAnswer}
              questionNumber={currentQuestion?.question_number || currentQuestionIdx + 1}
              showResult={false}
              hidePassage
              compact={isEnglish}
              mathMode={isMath && !!currentQuestion?.question_image}
            />
          </div>
        </div>

        {/* Navigator Sidebar */}
        <div style={{
          width: 220,
          borderLeft: '1px solid var(--act-border)',
          background: '#fafafa',
          overflowY: 'auto',
          flexShrink: 0,
        }}>
          <QuestionNavigator
            questionNumbers={questionNumbers}
            currentQuestion={currentQuestion?.question_number || currentQuestionIdx + 1}
            answeredQuestions={answeredSet}
            markedQuestions={markedSet}
            onNavigate={(qNum) => {
              const idx = questions.findIndex(q => q.question_number === qNum);
              if (idx >= 0) setCurrentQuestionIdx(idx);
            }}
          />
        </div>
      </div>

      {/* Bottom Bar */}
      <div style={{
        background: 'white',
        borderTop: '1px solid var(--act-border)',
        padding: '10px 20px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', gap: 10 }}>
          <button
            onClick={() => setCurrentQuestionIdx((p) => Math.max(0, p - 1))}
            disabled={currentQuestionIdx === 0}
            style={{
              padding: '10px 20px',
              border: '2px solid var(--act-border)',
              borderRadius: 6,
              background: 'white',
              fontWeight: 600,
              fontSize: 14,
              color: currentQuestionIdx === 0 ? '#ccc' : 'var(--act-text)',
              cursor: currentQuestionIdx === 0 ? 'default' : 'pointer',
            }}
          >
            Previous
          </button>
          <button
            onClick={() => setCurrentQuestionIdx((p) => Math.min(totalQuestions - 1, p + 1))}
            disabled={currentQuestionIdx >= totalQuestions - 1}
            style={{
              padding: '10px 20px',
              border: '2px solid var(--act-blue)',
              borderRadius: 6,
              background: 'var(--act-blue)',
              color: 'white',
              fontWeight: 600,
              fontSize: 14,
              cursor: currentQuestionIdx >= totalQuestions - 1 ? 'default' : 'pointer',
              opacity: currentQuestionIdx >= totalQuestions - 1 ? 0.5 : 1,
            }}
          >
            Next
          </button>
        </div>

        <div style={{ display: 'flex', gap: 10 }}>
          <button
            onClick={() => {
              // Session is already persisted via useEffect; just navigate away
              navigate('/tests');
            }}
            style={{
              padding: '10px 16px',
              border: '2px solid var(--act-border)',
              borderRadius: 6,
              background: 'white',
              color: 'var(--act-dark-gray)',
              fontWeight: 600,
              fontSize: 13,
              cursor: 'pointer',
            }}
          >
            Pause Test
          </button>
          <button
            onClick={toggleMark}
            style={{
              padding: '10px 16px',
              border: `2px solid ${isMarked ? 'var(--act-orange)' : 'var(--act-border)'}`,
              borderRadius: 6,
              background: isMarked ? '#fff3e0' : 'white',
              color: isMarked ? 'var(--act-orange)' : 'var(--act-dark-gray)',
              fontWeight: 600,
              fontSize: 13,
              cursor: 'pointer',
            }}
          >
            {isMarked ? 'Unmark' : 'Mark for Review'}
          </button>
        </div>

        <button
          onClick={() => {
            setConfirmType(isLastSection ? 'test' : 'section');
            setShowConfirm(true);
          }}
          style={{
            padding: '10px 24px',
            border: 'none',
            borderRadius: 6,
            background: isLastSection ? 'var(--act-green)' : 'var(--act-accent)',
            color: 'white',
            fontWeight: 700,
            fontSize: 14,
            cursor: 'pointer',
          }}
        >
          {isLastSection ? 'Submit Test' : 'Next Section'}
        </button>
      </div>

      {/* Confirm Modal */}
      {showConfirm && (
        <div style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 200,
        }}>
          <div style={{
            background: 'white',
            borderRadius: 12,
            padding: 32,
            maxWidth: 440,
            width: '90%',
            textAlign: 'center',
          }}>
            <h3 style={{ fontSize: 20, marginBottom: 12 }}>
              {confirmType === 'test' ? 'Submit Test?' : 'Move to Next Section?'}
            </h3>
            <p style={{ color: 'var(--act-dark-gray)', fontSize: 14, marginBottom: 8 }}>
              {answeredSet.size} of {totalQuestions} questions answered in this section.
            </p>
            {answeredSet.size < totalQuestions && (
              <p style={{ color: 'var(--act-red)', fontSize: 14, marginBottom: 20 }}>
                You have {totalQuestions - answeredSet.size} unanswered question(s).
              </p>
            )}
            {confirmType === 'section' && (
              <p style={{ color: 'var(--act-dark-gray)', fontSize: 13, marginBottom: 20 }}>
                You can return to any section by clicking its tab.
              </p>
            )}
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
              <button
                onClick={() => setShowConfirm(false)}
                style={{
                  padding: '10px 24px',
                  border: '2px solid var(--act-border)',
                  borderRadius: 6,
                  background: 'white',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Go Back
              </button>
              <button
                onClick={handleConfirmAction}
                disabled={submitting}
                style={{
                  padding: '10px 24px',
                  border: 'none',
                  borderRadius: 6,
                  background: confirmType === 'test' ? 'var(--act-green)' : 'var(--act-blue)',
                  color: 'white',
                  fontWeight: 600,
                  cursor: 'pointer',
                  opacity: submitting ? 0.7 : 1,
                }}
              >
                {submitting ? 'Submitting...' : confirmType === 'test' ? 'Submit Test' : 'Next Section'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
