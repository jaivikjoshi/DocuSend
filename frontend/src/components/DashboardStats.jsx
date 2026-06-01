import { AlertTriangle, CircleDollarSign, FileText, Gauge, ReceiptText, RotateCcw } from 'lucide-react';
import styles from './DashboardStats.module.css';

function money(value) {
  return Number(value || 0).toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  });
}

function percent(value) {
  if (value == null) return '—';
  return `${Math.round(value)}%`;
}

function docDate(doc) {
  const raw = doc.date || doc.document_date || doc.created_at;
  return raw ? new Date(raw) : null;
}

function isSameMonth(date, now) {
  return date && date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth();
}

function calculateStats(documents) {
  const now = new Date();
  const withConfidence = documents.filter(doc => doc.confidence != null);
  const needsReview = documents.filter(doc =>
    doc.status === 'review' ||
    Number(doc.confidence || 0) < 75 ||
    (Array.isArray(doc.warnings) && doc.warnings.length > 0)
  );

  return {
    totalDocuments: documents.length,
    needsReview: needsReview.length,
    totalSpend: documents.reduce((sum, doc) => sum + Number(doc.total || 0), 0),
    avgConfidence: withConfidence.length
      ? withConfidence.reduce((sum, doc) => sum + Number(doc.confidence || 0), 0) / withConfidence.length
      : null,
    taxCaptured: documents.reduce((sum, doc) => sum + Number(doc.tax || 0), 0),
    failedJobs: documents.filter(doc => doc.status === 'failed').length,
    thisMonthSpend: documents.reduce((sum, doc) => (
      isSameMonth(docDate(doc), now) ? sum + Number(doc.total || 0) : sum
    ), 0),
  };
}

function StatCard({ icon: Icon, label, value, tone = 'default' }) {
  return (
    <div className={`${styles.card} ${styles[tone] || ''}`}>
      <div className={styles.iconWrap}>
        <Icon size={18} />
      </div>
      <div className={styles.copy}>
        <span className={styles.label}>{label}</span>
        <strong className={styles.value}>{value}</strong>
      </div>
    </div>
  );
}

export default function DashboardStats({ documents }) {
  const stats = calculateStats(documents);

  return (
    <section className={styles.grid} aria-label="Dashboard stats">
      <StatCard icon={FileText} label="Documents" value={stats.totalDocuments} />
      <StatCard icon={AlertTriangle} label="Needs Review" value={stats.needsReview} tone={stats.needsReview ? 'warning' : 'success'} />
      <StatCard icon={CircleDollarSign} label="Total Spend" value={money(stats.totalSpend)} />
      <StatCard icon={Gauge} label="Avg Confidence" value={percent(stats.avgConfidence)} tone={stats.avgConfidence != null && stats.avgConfidence < 75 ? 'warning' : 'success'} />
      <StatCard icon={ReceiptText} label="Tax Captured" value={money(stats.taxCaptured)} />
      <StatCard icon={RotateCcw} label="Failed Jobs" value={stats.failedJobs} tone={stats.failedJobs ? 'error' : 'success'} />
      <div className={styles.wideCard}>
        <span>This Month</span>
        <strong>{money(stats.thisMonthSpend)}</strong>
      </div>
    </section>
  );
}
