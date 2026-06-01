import { useState } from 'react';
import { Download, FileJson, FileArchive, CheckCircle, Sheet } from 'lucide-react';
import { supabase } from '../lib/supabaseClient';
import styles from './ExportPanel.module.css';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a   = document.createElement('a');
  a.href     = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function csvValue(value) {
  const text = value == null ? '' : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

function guestAccountingCsv(documents) {
  const columns = ['Date', 'Payee', 'Description', 'Category', 'Amount', 'Tax', 'Currency', 'Receipt File', 'Review Required', 'Warnings'];
  const rows = documents.map(doc => [
    doc.date || doc.document_date || '',
    doc.vendor || '',
    doc.invoice_number || doc.file_name || '',
    doc.document_type === 'unknown' ? 'Uncategorized' : 'Office Supplies',
    doc.total ?? '',
    doc.tax ?? '',
    doc.currency || 'USD',
    doc.file_name || '',
    doc.status === 'review' || (doc.warnings || []).length > 0 ? 'Yes' : 'No',
    (doc.warnings || []).join(' | '),
  ]);
  return [columns, ...rows].map(row => row.map(csvValue).join(',')).join('\n');
}

async function downloadExport(documents, format, isGuest) {
  if (isGuest) {
    if (format === 'json') {
      saveBlob(
        new Blob([JSON.stringify(documents, null, 2)], { type: 'application/json' }),
        'docusend-guest-export.json',
      );
      return;
    }
    if (format === 'accounting_csv') {
      saveBlob(
        new Blob([guestAccountingCsv(documents)], { type: 'text/csv' }),
        'docusend-guest-accounting.csv',
      );
      return;
    }
    throw new Error('Sign in to export the normalized CSV ZIP.');
  }

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

  saveBlob(blob, filename);
}

function ExportCard({ id, icon: Icon, title, description, format, documents, disabled, isGuest }) {
  const [loading, setLoading] = useState(false);
  const [done,    setDone]    = useState(false);
  const [error,   setError]   = useState('');

  const handleClick = async () => {
    setError('');
    setDone(false);
    setLoading(true);
    try {
      await downloadExport(documents, format, isGuest);
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

export default function ExportPanel({ documents, isGuest = false }) {
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

          {!isGuest && (
            <ExportCard
              id="btn-export-csv"
              icon={FileArchive}
              title="CSV Export (ZIP)"
              description="Two CSV files — one for document summaries, one for line items — zipped together. Best for Excel, Google Sheets, or accounting software."
              format="csv_zip"
              documents={documents}
              disabled={!hasDocuments}
              isGuest={isGuest}
            />
          )}

          <ExportCard
            id="btn-export-accounting"
            icon={Sheet}
            title="Accounting CSV"
            description="A flat expense-register format with date, payee, amount, tax, category, review flag, and receipt filename. Best for QuickBooks-style imports or month-end expense reports."
            format="accounting_csv"
            documents={documents}
            disabled={!hasDocuments}
            isGuest={isGuest}
          />

          <ExportCard
            id="btn-export-json"
            icon={FileJson}
            title="JSON Export"
            description="Full structured data for all documents including all fields and line items. Best for developers or importing into another system."
            format="json"
            documents={documents}
            disabled={!hasDocuments}
            isGuest={isGuest}
          />
        </>
      )}
    </div>
  );
}
