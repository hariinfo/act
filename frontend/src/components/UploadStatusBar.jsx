import { useUpload } from '../context/UploadContext';
import { useNavigate } from 'react-router-dom';

function computeProgress(progress) {
  const totalSections = progress[progress.length - 1]?.total_sections || 4;
  const classifiedSections = progress.filter(p => p.step === 'classified').length;
  const classifyingSections = progress.filter(p => p.step === 'classifying').length;
  const explainedSections = progress.filter(p => p.step === 'explained').length;
  const explainingSections = progress.filter(p => p.step === 'explaining').length;
  const isDone = progress.some(p => p.step === 'done');

  let pct = 5;
  let label = 'Uploading PDF...';
  if (progress.some(p => p.step === 'parsed')) { pct = 10; label = 'PDF parsed'; }
  if (classifyingSections > 0) {
    pct = 10 + (classifiedSections / totalSections) * 40;
    const lastDetail = progress.filter(p => p.step === 'classifying_detail').pop();
    label = lastDetail ? lastDetail.message : `Classifying topics (${classifiedSections}/${totalSections})`;
  }
  if (classifiedSections === totalSections) { pct = 50; label = 'Topics classified'; }
  if (explainingSections > 0) {
    const lastDetail = progress.filter(p => p.step === 'explaining_detail').pop();
    if (lastDetail && lastDetail.question_total) {
      pct = 50 + (explainedSections / totalSections) * 45 + (lastDetail.question_index / lastDetail.question_total) * (45 / totalSections);
      label = lastDetail.message;
    } else {
      pct = 50 + (explainedSections / totalSections) * 45;
      label = `Generating explanations (${explainedSections}/${totalSections})`;
    }
  }
  if (isDone) { pct = 100; label = 'Upload complete!'; }

  return { pct, label, isDone };
}

export default function UploadStatusBar() {
  const { uploads } = useUpload();
  const navigate = useNavigate();

  // Show active uploads (still processing)
  const activeUploads = Object.values(uploads).filter(u => u.uploading);
  if (activeUploads.length === 0) return null;
  if (window.location.pathname === '/admin/upload-pdf') return null;

  const count = activeUploads.length;
  // Show aggregate progress from first active upload
  const first = activeUploads[0];
  const { pct, label } = computeProgress(first.progress || []);

  return (
    <div
      onClick={() => navigate('/admin/upload-pdf')}
      style={{
        position: 'fixed', bottom: 20, right: 20, zIndex: 9999,
        background: 'white', borderRadius: 12, padding: '12px 16px',
        boxShadow: '0 4px 20px rgba(0,0,0,0.15)', border: '1px solid var(--act-border)',
        cursor: 'pointer', minWidth: 280, maxWidth: 340,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 14, height: 14, border: '2px solid var(--act-blue)',
            borderTopColor: 'transparent', borderRadius: '50%',
            animation: 'spin 0.8s linear infinite',
          }} />
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--act-text)' }}>
            {count > 1 ? `Processing ${count} PDFs` : 'PDF Processing'}
          </span>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--act-dark-gray)' }}>
          {Math.round(pct)}%
        </span>
      </div>
      <div style={{ height: 5, background: '#e0e0e0', borderRadius: 3, overflow: 'hidden', marginBottom: 4 }}>
        <div style={{
          height: '100%', borderRadius: 3, transition: 'width 0.5s ease',
          background: 'var(--act-blue)',
          width: `${pct}%`,
        }} />
      </div>
      <div style={{ fontSize: 11, color: 'var(--act-dark-gray)' }}>
        {count > 1 ? `${first.filename}: ${label}` : label} — click to view details
      </div>
    </div>
  );
}
