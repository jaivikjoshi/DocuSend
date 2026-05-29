import { useState, useEffect } from 'react';
import { X, Save, Edit3, Trash2 } from 'lucide-react';
import { supabase } from '../lib/supabaseClient';
import styles from './DocumentDetail.module.css';

function ConfBar({ score }) {
  const p = Math.max(0, Math.min(100, score || 0));
  const color = p >= 75 ? 'var(--conf-high)' : p >= 50 ? 'var(--conf-mid)' : 'var(--conf-low)';
  return (
    <div className={styles.confBarWrap}>
      <div className={styles.confBarBg}>
        <div className={styles.confBarFill} style={{ width: `${p}%`, background: color }} />
      </div>
      <span className={styles.confScore} style={{ color }}>{p}%</span>
    </div>
  );
}

export default function DocumentDetail({ doc, onUpdate, onDelete, onClose }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(null);
  const [fileUrl, setFileUrl] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraft(JSON.parse(JSON.stringify(doc)));
    setEditing(false);

    async function getUrl() {
      if (doc.storage_path) {
        const { data, error } = await supabase.storage
          .from('document-receipts')
          .createSignedUrl(doc.storage_path, 3600); // 1 hour
        if (!error && data) {
          setFileUrl(data.signedUrl);
        }
      }
    }
    getUrl();
  }, [doc]);

  if (!draft) return null;

  const handleSave = async () => {
    setSaving(true);
    try {
      const docRecord = {
        vendor: draft.vendor,
        date: draft.date,
        total: draft.total,
        tax: draft.tax,
      };
      
      const { error: docError } = await supabase
        .from('documents')
        .update(docRecord)
        .eq('id', draft.id);

      if (docError) throw docError;

      // Update line items by deleting old and inserting new
      await supabase.from('line_items').delete().eq('document_id', draft.id);
      
      if (draft.line_items && draft.line_items.length > 0) {
        const lineItems = draft.line_items.map(li => ({
          document_id: draft.id,
          user_id: draft.user_id,
          description: li.description,
          quantity: li.quantity,
          unit_price: li.unit_price,
          total: li.total,
          confidence: li.confidence
        }));
        const { error: lineError } = await supabase.from('line_items').insert(lineItems);
        if (lineError) throw lineError;
      }

      onUpdate(draft);
      setEditing(false);
    } catch (err) {
      console.error("Save error:", err);
      alert("Failed to save document.");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = () => {
    if (confirm("Are you sure you want to delete this document?")) {
      onDelete(draft.id);
    }
  };

  const setField = (field, val) => setDraft(prev => ({ ...prev, [field]: val }));

  const addItem = () => setDraft(p => ({
    ...p,
    line_items: [...(p.line_items || []), { description: '', quantity: 1, unit_price: 0, total: 0 }]
  }));

  const updateItem = (i, field, val) => {
    const list = [...(draft.line_items || [])];
    list[i][field] = val;
    if (field === 'quantity' || field === 'unit_price') {
      const q = parseFloat(list[i].quantity) || 0;
      const u = parseFloat(list[i].unit_price) || 0;
      list[i].total = Number((q * u).toFixed(2));
    }
    setDraft(p => ({ ...p, line_items: list }));
  };

  const delItem = (i) => setDraft(p => ({
    ...p,
    line_items: p.line_items.filter((_, idx) => idx !== i)
  }));

  return (
    <div className={`card ${styles.panel} animate-slide-up`} style={{ maxWidth: '100%', border: 'none' }}>
      <header className={styles.header}>
        <div>
          <h2 className={styles.title}>{draft.file_name}</h2>
          <span className={styles.subtitle}>{draft.document_type || 'Unknown Type'}</span>
        </div>
        <div className={styles.actions}>
          <button className="btn btn-ghost btn-sm" style={{ color: 'var(--error)' }} onClick={handleDelete}><Trash2 size={14}/> Delete</button>
          {editing ? (
            <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}><Save size={14}/> {saving ? 'Saving...' : 'Save'}</button>
          ) : (
            <button className="btn btn-secondary btn-sm" onClick={() => setEditing(true)}><Edit3 size={14}/> Edit</button>
          )}
          <button className={`btn btn-ghost btn-sm ${styles.closeBtn}`} onClick={onClose} aria-label="Close panel"><X size={16}/></button>
        </div>
      </header>

      <div className={styles.body} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', padding: '0', height: 'calc(100vh - 200px)' }}>
        
        {/* Left Side: Document Preview */}
        <div style={{ background: '#e5e7eb', borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {fileUrl ? (
             draft.file_name.toLowerCase().endsWith('.pdf') ? (
               <iframe src={fileUrl} style={{ width: '100%', height: '100%', border: 'none' }} title="Document Preview" />
             ) : (
               <img src={fileUrl} alt="Document Preview" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
             )
          ) : (
            <div className="empty-state" style={{ margin: 'auto' }}>
              <div className="spinner"></div>
              <p>Loading preview...</p>
            </div>
          )}
        </div>

        {/* Right Side: Form */}
        <div style={{ padding: '24px', overflowY: 'auto' }}>
          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>Confidence Score</h3>
            <ConfBar score={draft.confidence} />
          </div>

          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>Extracted Data</h3>
            <div className={styles.grid}>
              <div className="form-group">
                <label className="form-label">Vendor</label>
                {editing ? <input className="form-input" value={draft.vendor || ''} onChange={e => setField('vendor', e.target.value)} />
                         : <div className={styles.val}>{draft.vendor || '—'}</div>}
              </div>
              <div className="form-group">
                <label className="form-label">Date</label>
                {editing ? <input type="date" className="form-input" value={draft.date || ''} onChange={e => setField('date', e.target.value)} />
                         : <div className={styles.val}>{draft.date || '—'}</div>}
              </div>
              <div className="form-group">
                <label className="form-label">Total Amount</label>
                {editing ? <input type="number" step="0.01" className="form-input" value={draft.total || ''} onChange={e => setField('total', parseFloat(e.target.value))} />
                         : <div className={styles.val}>${Number(draft.total || 0).toFixed(2)}</div>}
              </div>
              <div className="form-group">
                <label className="form-label">Tax Amount</label>
                {editing ? <input type="number" step="0.01" className="form-input" value={draft.tax || ''} onChange={e => setField('tax', parseFloat(e.target.value))} />
                         : <div className={styles.val}>${Number(draft.tax || 0).toFixed(2)}</div>}
              </div>
            </div>
          </div>

          <div className={styles.section}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <h3 className={styles.sectionTitle} style={{ margin: 0 }}>Line Items</h3>
              {editing && <button className="btn btn-secondary btn-sm" onClick={addItem}>+ Add Item</button>}
            </div>

            {draft.line_items?.length > 0 ? (
              <div className={styles.itemsList}>
                {draft.line_items.map((item, i) => (
                  <div key={i} className={styles.itemRow}>
                    {editing ? (
                      <>
                        <input className="form-input" placeholder="Description" value={item.description || ''} onChange={e => updateItem(i, 'description', e.target.value)} style={{ flex: 2 }} />
                        <input type="number" className="form-input" placeholder="Qty" value={item.quantity || ''} onChange={e => updateItem(i, 'quantity', e.target.value)} style={{ width: '60px' }} />
                        <input type="number" step="0.01" className="form-input" placeholder="Price" value={item.unit_price || ''} onChange={e => updateItem(i, 'unit_price', e.target.value)} style={{ width: '80px' }} />
                        <button className="btn btn-ghost btn-sm" style={{ color: 'var(--error)' }} onClick={() => delItem(i)}><Trash2 size={16}/></button>
                      </>
                    ) : (
                      <>
                        <div className={styles.itemDesc}>{item.description || '—'}</div>
                        <div className={styles.itemNum}>{item.quantity} × ${Number(item.unit_price).toFixed(2)}</div>
                        <div className={styles.itemTotal}>${Number(item.total).toFixed(2)}</div>
                      </>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state" style={{ padding: '24px 0' }}>
                <p>No line items found.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
