import { AlertTriangle } from 'lucide-react';
import styles from './DocumentTable.module.css';

function confidenceBadge(score) {
  if (score == null) return <span className="badge badge-muted">—</span>;
  if (score >= 75) return <span className="badge badge-success">{score}%</span>;
  if (score >= 50) return <span className="badge badge-warning">{score}%</span>;
  return <span className="badge badge-error">{score}%</span>;
}

function docTypeBadge(type) {
  const t = (type ?? 'unknown').toLowerCase();
  if (t === 'invoice') return <span className="badge badge-pine">Invoice</span>;
  if (t === 'receipt') return <span className="badge badge-success">Receipt</span>;
  return <span className="badge badge-muted">Unknown</span>;
}

function statusBadge(status) {
  const s = status ?? 'review';
  if (s === 'processed') return <span className="badge badge-success">Processed</span>;
  if (s === 'queued') return <span className="badge badge-muted">Queued</span>;
  if (s === 'processing') return <span className="badge badge-muted">Processing</span>;
  if (s === 'failed') return <span className="badge badge-error">Failed</span>;
  return <span className="badge badge-warning">Review</span>;
}

function fmt(val, prefix = '$') {
  if (val == null) return '—';
  return `${prefix}${Number(val).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function DocumentTable({ documents, onSelectDocument, selectedDoc }) {
  if (!documents.length) return null;

  return (
    <div className={`card ${styles.wrap}`}>
      <div className={styles.header}>
        <span className={styles.title}>Processed Documents</span>
        <span className="badge badge-pine">{documents.length}</span>
      </div>
      <div className={styles.tableWrap}>
        <table className={styles.table} id="documents-table">
          <thead>
            <tr>
              <th>File</th>
              <th>Status</th>
              <th>Type</th>
              <th>Vendor</th>
              <th>Date</th>
              <th>Total</th>
              <th>Confidence</th>
              <th>Source</th>
              <th>Warnings</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc, i) => {
              const isSelected = selectedDoc?.file_name === doc.file_name;
              const warnings   = Array.isArray(doc.warnings) ? doc.warnings : [];
              return (
                <tr
                  key={`${doc.file_name}-${i}`}
                  className={`${styles.row} ${isSelected ? styles.rowSelected : ''}`}
                  onClick={() => onSelectDocument(isSelected ? null : doc)}
                  tabIndex={0}
                  onKeyDown={e => e.key === 'Enter' && onSelectDocument(isSelected ? null : doc)}
                  aria-selected={isSelected}
                  role="row"
                >
                  <td className={styles.fileCell}>
                    <span className={styles.fileName}>{doc.file_name}</span>
                  </td>
                  <td>{statusBadge(doc.status)}</td>
                  <td>{docTypeBadge(doc.document_type)}</td>
                  <td className={styles.vendorCell}>{doc.vendor || '—'}</td>
                  <td>{doc.document_date || doc.date || '—'}</td>
                  <td className={styles.monospace}>{fmt(doc.total)}</td>
                  <td>{confidenceBadge(doc.confidence)}</td>
                  <td>
                    {doc.source_mode === 'gemini'
                      ? <span className="badge" style={{ background: 'linear-gradient(135deg,#4f46e5,#7c3aed)', color: '#fff', boxShadow: '0 0 6px rgba(124,58,237,0.35)' }}>✦ AI</span>
                      : <span className="badge badge-muted">⚙ Regex</span>}
                  </td>
                  <td>
                    {warnings.length > 0
                      ? <span className="badge badge-warning" title={warnings.join('\n')}>
                          <AlertTriangle size={11} /> {warnings.length}
                        </span>
                      : <span className="badge badge-success">✓</span>
                    }
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
