import { useState, useEffect, useRef } from 'react';

export default function Timer({ totalSeconds, onTimeUp, storageKey }) {
  const getInitialRemaining = () => {
    if (storageKey) {
      try {
        const saved = localStorage.getItem(storageKey);
        if (saved) {
          const { startedAt, total } = JSON.parse(saved);
          const elapsed = Math.floor((Date.now() - startedAt) / 1000);
          const left = Math.max(0, total - elapsed);
          return left;
        }
      } catch {}
    }
    return totalSeconds;
  };

  const [remaining, setRemaining] = useState(getInitialRemaining);
  const intervalRef = useRef(null);

  // Save start timestamp when section changes
  useEffect(() => {
    if (storageKey) {
      try {
        const existing = localStorage.getItem(storageKey);
        if (!existing) {
          localStorage.setItem(storageKey, JSON.stringify({
            startedAt: Date.now(),
            total: totalSeconds,
          }));
        }
      } catch {}
    }
    setRemaining(getInitialRemaining());
  }, [totalSeconds, storageKey]);

  useEffect(() => {
    intervalRef.current = setInterval(() => {
      setRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(intervalRef.current);
          if (storageKey) {
            try { localStorage.removeItem(storageKey); } catch {}
          }
          onTimeUp?.();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(intervalRef.current);
  }, [totalSeconds, storageKey]);

  const mins = Math.floor(remaining / 60);
  const secs = remaining % 60;
  const isLow = remaining < 300;
  const isCritical = remaining < 60;

  return (
    <div
      style={{
        fontFamily: "'Courier New', monospace",
        fontSize: 22,
        fontWeight: 700,
        color: isCritical ? '#fff' : isLow ? 'var(--act-red)' : '#fff',
        background: isCritical ? 'var(--act-red)' : isLow ? '#fff3e0' : 'rgba(255,255,255,0.1)',
        padding: '6px 16px',
        borderRadius: 6,
        minWidth: 90,
        textAlign: 'center',
        animation: isCritical ? 'pulse 1s infinite' : 'none',
      }}
    >
      {String(mins).padStart(2, '0')}:{String(secs).padStart(2, '0')}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.6; }
        }
      `}</style>
    </div>
  );
}
