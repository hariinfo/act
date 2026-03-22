import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useEffect, useState } from 'react';
import api from '../api/axios';

export default function Home() {
  const { user, isAdmin } = useAuth();
  const [stats, setStats] = useState(null);

  useEffect(() => {
    api.get('/questions/stats').catch(() => null).then(r => r && setStats(r.data));
  }, []);

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '40px 20px' }}>
      {/* Hero */}
      <div style={{
        textAlign: 'center',
        padding: '60px 20px',
        background: 'linear-gradient(135deg, var(--act-blue) 0%, var(--act-light-blue) 100%)',
        borderRadius: 16,
        color: 'white',
        marginBottom: 40,
      }}>
        <div style={{
          display: 'inline-block',
          background: 'white',
          color: 'var(--act-blue)',
          padding: '8px 24px',
          borderRadius: 8,
          fontWeight: 800,
          fontSize: 36,
          marginBottom: 16,
        }}>
          ACT
        </div>
        <h1 style={{ fontSize: 32, fontWeight: 300, marginBottom: 12 }}>Practice Test Platform</h1>
        <p style={{ fontSize: 16, opacity: 0.85, maxWidth: 500, margin: '0 auto 32px' }}>
          Prepare for the ACT with real practice questions. Timed sections, instant scoring, and detailed review.
        </p>
        <div style={{ display: 'flex', gap: 16, justifyContent: 'center', flexWrap: 'wrap' }}>
          {user ? (
            <Link to="/tests" style={{
              background: 'white',
              color: 'var(--act-blue)',
              padding: '14px 32px',
              borderRadius: 8,
              fontWeight: 700,
              fontSize: 16,
              textDecoration: 'none',
              transition: 'transform 0.15s',
            }}>
              Take a Test
            </Link>
          ) : (
            <>
              <Link to="/register" style={{
                background: 'white',
                color: 'var(--act-blue)',
                padding: '14px 32px',
                borderRadius: 8,
                fontWeight: 700,
                fontSize: 16,
                textDecoration: 'none',
              }}>
                Get Started
              </Link>
              <Link to="/login" style={{
                background: 'transparent',
                color: 'white',
                padding: '14px 32px',
                borderRadius: 8,
                fontWeight: 600,
                fontSize: 16,
                textDecoration: 'none',
                border: '2px solid rgba(255,255,255,0.5)',
              }}>
                Sign In
              </Link>
            </>
          )}
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 40 }}>
          <StatCard label="Total Questions" value={stats.total_questions} />
          <StatCard label="Test Sources" value={stats.sources?.length || 0} />
          {Object.entries(stats.by_subject || {}).map(([name, count]) => (
            <StatCard key={name} label={name} value={`${count} Qs`} />
          ))}
        </div>
      )}

      {/* Features */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: 20 }}>
        <FeatureCard
          title="Timed Practice"
          desc="Experience real ACT timing with section-by-section countdown timers."
        />
        <FeatureCard
          title="Instant Scoring"
          desc="Get your composite and section scores immediately after completing a test."
        />
        <FeatureCard
          title="Question Bank"
          desc="Practice from a growing bank of ACT-style questions across all four subjects."
        />
      </div>

      {isAdmin && (
        <div style={{ textAlign: 'center', marginTop: 40 }}>
          <Link to="/admin" style={{
            display: 'inline-block',
            background: 'var(--act-blue)',
            color: 'white',
            padding: '12px 28px',
            borderRadius: 8,
            fontWeight: 600,
            textDecoration: 'none',
          }}>
            Admin Dashboard
          </Link>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value }) {
  return (
    <div style={{
      background: 'white',
      borderRadius: 8,
      padding: 20,
      textAlign: 'center',
      border: '1px solid var(--act-border)',
    }}>
      <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--act-blue)' }}>{value}</div>
      <div style={{ fontSize: 13, color: 'var(--act-dark-gray)', marginTop: 4 }}>{label}</div>
    </div>
  );
}

function FeatureCard({ title, desc }) {
  return (
    <div style={{
      background: 'white',
      borderRadius: 8,
      padding: 24,
      border: '1px solid var(--act-border)',
    }}>
      <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 8, color: 'var(--act-blue)' }}>{title}</h3>
      <p style={{ fontSize: 14, color: 'var(--act-dark-gray)', lineHeight: 1.6 }}>{desc}</p>
    </div>
  );
}
