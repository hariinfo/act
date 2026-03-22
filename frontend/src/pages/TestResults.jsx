import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import api from '../api/axios';
import ScoreCard from '../components/ScoreCard';
import QuestionCard from '../components/QuestionCard';

export default function TestResults() {
  const { testId, attemptId } = useParams();
  const [results, setResults] = useState(null);
  const [test, setTest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showReview, setShowReview] = useState(false);
  const [reviewQuestions, setReviewQuestions] = useState([]);

  useEffect(() => {
    Promise.all([
      api.get(`/tests/attempts/${attemptId}/results`),
      api.get(`/tests/${testId}?attempt_id=${attemptId}`),
    ])
      .then(([resResults, resTest]) => {
        setResults(resResults.data);
        setTest(resTest.data);

        // Build review data from test questions and answers
        const allQuestions = [];
        for (const section of resTest.data.sections) {
          for (const q of section.questions) {
            const answer = resResults.data.answers.find((a) => a.question_id === q.id);
            allQuestions.push({
              ...q,
              selectedAnswer: answer?.selected_answer,
              isCorrect: answer?.is_correct,
              correct_answer: answer?.correct_answer || q.correct_answer,
            });
          }
        }
        setReviewQuestions(allQuestions);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [testId, attemptId]);

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 60, color: '#666' }}>Loading results...</div>;
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '32px 20px' }}>
      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <h1 style={{ fontSize: 24, color: 'var(--act-blue)', marginBottom: 4 }}>Test Complete!</h1>
        <p style={{ color: 'var(--act-dark-gray)' }}>{results?.test_name}</p>
      </div>

      <ScoreCard results={results} />

      <div style={{ textAlign: 'center', marginTop: 32, display: 'flex', gap: 12, justifyContent: 'center' }}>
        <button
          onClick={() => setShowReview(!showReview)}
          style={{
            padding: '12px 28px',
            border: '2px solid var(--act-blue)',
            borderRadius: 6,
            background: showReview ? 'var(--act-blue)' : 'white',
            color: showReview ? 'white' : 'var(--act-blue)',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          {showReview ? 'Hide Review' : 'Review Answers'}
        </button>
        <Link to="/tests" style={{
          padding: '12px 28px',
          border: 'none',
          borderRadius: 6,
          background: 'var(--act-blue)',
          color: 'white',
          fontWeight: 600,
          textDecoration: 'none',
          display: 'inline-block',
        }}>
          Back to Tests
        </Link>
      </div>

      {showReview && (
        <div style={{ marginTop: 32 }}>
          <h2 style={{ fontSize: 20, marginBottom: 20, color: 'var(--act-blue)' }}>Answer Review</h2>
          {reviewQuestions.map((q, idx) => (
            <div key={q.id} style={{
              background: 'white',
              borderRadius: 8,
              padding: 24,
              marginBottom: 16,
              border: `1px solid ${q.isCorrect ? '#c8e6c9' : q.selectedAnswer ? '#ffcdd2' : 'var(--act-border)'}`,
            }}>
              <QuestionCard
                question={q}
                selectedAnswer={q.selectedAnswer}
                questionNumber={q.question_number || idx + 1}
                showResult={true}
                correctAnswer={q.correct_answer || null}
              />
              {!q.selectedAnswer && (
                <div style={{
                  marginTop: 12,
                  marginLeft: 48,
                  color: 'var(--act-orange)',
                  fontSize: 14,
                  fontWeight: 600,
                }}>
                  Not answered
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
