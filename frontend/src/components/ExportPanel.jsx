import { useState } from 'react';
import { Download, FileJson, FileArchive, CheckCircle } from 'lucide-react';
import { supabase } from '../lib/supabaseClient';
import styles from './ExportPanel.module.css';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

async function downloadExport(documents, format) {
  const session = await supabase.auth.getSession();
  const token = session.data.session?.access_token;
  if (!token) throw new Error('You must be signed in to export documents.');

  const res = await fetch(`${API_URL}/api/export`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ document_ids: documents.map(doc => doc.id), format }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Export failed' }));
    throw new Error(err.detail ?? 'Export failed');
  }
  const blob = await res.blob();
  const disposition = res.headers.get('content-disposition') ?? '';
  const nameMatch   = disposition.match(/filename="?([^"]+)"?/);
  const filename    = nameMatch?.[1] ?? (format === 'json' ? 'export.json' : 'export.zip');

  const url = URL.createObjectURL(blob);
  const a   = document.createElement('a');
  a.href     = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function ExportCard({ id, icon: Icon, title, description, format, documents, disabled }) {
  const [loading, setLoading] = useState(false);
  const [done,    setDone]    = useState(false);
  const [error,   setError]   = useState('');

  const handleClick = async () => {
    setError('');
    setDone(false);
    setLoading(true);
    try {
      await downloadExport(documents, format);
      setDone(true);
      setTimeout(() => setDone(false), 3000);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`card ${styles.exportCard}`}>
      <div className={styles.exportIcon}>
        <Icon size={28} />
      </div>
      <div className={styles.exportInfo}>
        <h3>{title}</h3>
        <p>{description}</p>
        {error && <p className={styles.exportError}>{error}</p>}
      </div>
      <button
        id={id}
        className={`btn btn-primary ${styles.exportBtn}`}
        onClick={handleClick}
        disabled={disabled || loading}
      >
        {loading  ? <><span className="spinner" style={{ borderTopColor: '#fff' }} /> Exporting…</> :
         done     ? <><CheckCircle size={15} /> Downloaded!</> :
         <><Download size={15} /> Download</>}
      </button>
    </div>
  );
}

export default function ExportPanel({ documents }) {
  const hasDocuments = documents.length > 0;

  return (
    <div className={styles.root}>
      {!hasDocuments && (
        <div className="card card-padded">
          <div className="empty-state">
            <Download size={48} />
            <h3>Nothing to export yet</h3>
            <p>Upload and process some documents on the Dashboard first, then come back to export.</p>
          </div>
        </div>
      )}

      {hasDocuments && (
        <>
          <div className={`alert alert-success ${styles.summary}`}>
            <CheckCircle size={16} style={{ flexShrink: 0 }} />
            {documents.length} document{documents.length !== 1 ? 's' : ''} ready to export.
          </div>

          <ExportCard
            id="btn-export-csv"
            icon={FileArchive}
            title="CSV Export (ZIP)"
            description="Two CSV files — one for document summaries, one for line items — zipped together. Best for Excel, Google Sheets, or accounting software."
            format="csv_zip"
            documents={documents}
            disabled={!hasDocuments}
          />

          <ExportCard
            id="btn-export-json"
            icon={FileJson}
            title="JSON Export"
            description="Full structured data for all documents including all fields and line items. Best for developers or importing into another system."
            format="json"
            documents={documents}
            disabled={!hasDocuments}
          />
        </>
      )}
    </div>
  );
}
