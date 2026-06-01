import { useState } from 'react';
import { Download, FileJson, FileArchive, CheckCircle, Sheet, Upload } from 'lucide-react';
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

function parseCsvHeader(text) {
  const firstLine = text.split(/\r?\n/).find(line => line.trim().length > 0) || '';
  const columns = [];
  let current = '';
  let quoted = false;

  for (let i = 0; i < firstLine.length; i += 1) {
    const char = firstLine[i];
    const next = firstLine[i + 1];
    if (char === '"' && quoted && next === '"') {
      current += '"';
      i += 1;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (char === ',' && !quoted) {
      columns.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }
  columns.push(current.trim());
  return columns.filter(Boolean);
}

function normalizeColumn(column) {
  return column.toLowerCase().replace(/[^a-z0-9]+/g, '');
}

function templateValue(doc, column) {
  const key = normalizeColumn(column);
  const warnings = (doc.warnings || []).join(' | ');
  const values = {
    date: doc.date || doc.document_date || '',
    documentdate: doc.date || doc.document_date || '',
    vendor: doc.vendor || '',
    payee: doc.vendor || '',
    merchant: doc.vendor || '',
    supplier: doc.vendor || '',
    description: doc.invoice_number || doc.file_name || '',
    memo: doc.invoice_number || doc.file_name || '',
    invoicenumber: doc.invoice_number || '',
    invoice: doc.invoice_number || '',
    receiptfile: doc.file_name || '',
    filename: doc.file_name || '',
    file: doc.file_name || '',
    amount: doc.total ?? '',
    total: doc.total ?? '',
    totalamount: doc.total ?? '',
    tax: doc.tax ?? '',
    subtotal: doc.subtotal ?? '',
    tip: doc.tip ?? '',
    discount: doc.discount ?? '',
    currency: doc.currency || 'USD',
    category: doc.document_type === 'unknown' ? 'Uncategorized' : 'Office Supplies',
    documenttype: doc.document_type || '',
    type: doc.document_type || '',
    paymentmethod: doc.payment_method || '',
    payment: doc.payment_method || '',
    status: doc.status || '',
    confidence: doc.confidence ?? '',
    reviewrequired: doc.status === 'review' || warnings ? 'Yes' : 'No',
    warnings,
    notes: doc.review_notes || '',
  };
  return values[key] ?? '';
}

function templateCsv(documents, columns) {
  const rows = documents.map(doc => columns.map(column => templateValue(doc, column)));
  return [columns, ...rows].map(row => row.map(csvValue).join(',')).join('\n');
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

function TemplateExport({ documents }) {
  const [template, setTemplate] = useState(null);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);

  const handleTemplate = async (event) => {
    setError('');
    setDone(false);
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError('Upload a CSV template with the column headers you want.');
      return;
    }
    const text = await file.text();
    const columns = parseCsvHeader(text);
    if (!columns.length) {
      setError('Template must include at least one header column.');
      return;
    }
    setTemplate({ name: file.name, columns });
  };

  const handleExport = () => {
    if (!template) {
      setError('Upload a CSV template first.');
      return;
    }
    saveBlob(
      new Blob([templateCsv(documents, template.columns)], { type: 'text/csv' }),
      `docusend-template-${template.name.replace(/\.csv$/i, '')}.csv`,
    );
    setDone(true);
    setTimeout(() => setDone(false), 3000);
  };

  return (
    <div className={`card ${styles.templateCard}`}>
      <div className={styles.exportIcon}>
        <Upload size={28} />
      </div>
      <div className={styles.exportInfo}>
        <h3>Template CSV Export</h3>
        <p>Upload a CSV template and DocuSend will export documents using that exact header order.</p>
        {template && (
          <p className={styles.templateMeta}>
            {template.name} · {template.columns.length} column{template.columns.length !== 1 ? 's' : ''}
          </p>
        )}
        {error && <p className={styles.exportError}>{error}</p>}
      </div>
      <div className={styles.templateActions}>
        <label className={`btn btn-secondary ${styles.templateUpload}`}>
          <Upload size={15} /> Upload
          <input type="file" accept=".csv,text/csv" onChange={handleTemplate} className="sr-only" />
        </label>
        <button
          id="btn-export-template"
          className={`btn btn-primary ${styles.exportBtn}`}
          onClick={handleExport}
          disabled={!documents.length || !template}
        >
          {done ? <><CheckCircle size={15} /> Downloaded!</> : <><Download size={15} /> Export</>}
        </button>
      </div>
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

          <TemplateExport documents={documents} />

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
