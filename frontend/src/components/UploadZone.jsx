import { useCallback, useRef, useState, useEffect } from 'react';
import { Upload, FileText, CheckCircle, XCircle } from 'lucide-react';
import styles from './UploadZone.module.css';

import { supabase } from '../lib/supabaseClient';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
const ALLOWED = new Set(['.pdf', '.png', '.jpg', '.jpeg', '.webp', '.tiff', '.tif']);

function getExt(name) {
  return name.slice(name.lastIndexOf('.')).toLowerCase();
}

function FileRow({ item }) {
  const statusIcon = {
    pending:    <div className="spinner" />,
    uploading:  <div className="spinner" />,
    parsing:    <div className="spinner" style={{ borderColor: 'rgba(255, 255, 255, 0.2)', borderTopColor: 'var(--accent)' }} />,
    done:       <CheckCircle size={16} style={{ color: 'var(--conf-high)' }} />,
    error:      <XCircle    size={16} style={{ color: 'var(--error)' }} />,
  }[item.status];

  return (
    <div className={styles.fileRow}>
      <FileText size={15} style={{ color: 'var(--sage)', flexShrink: 0 }} />
      <span className={styles.fileName}>{item.name}</span>
      <span className={`badge ${
        item.status === 'done'  ? 'badge-success' :
        item.status === 'error' ? 'badge-error'   : 'badge-muted'
      } ${styles.status}`}>
        {statusIcon}
        {item.status === 'done' ? 'Done' : item.status === 'error' ? 'Error' : item.status === 'uploading' ? 'Uploading…' : item.status === 'parsing' ? 'Parsing in Background…' : 'Pending…'}
      </span>
      {item.error && <span className={styles.errorMsg}>{item.error}</span>}
    </div>
  );
}

export default function UploadZone({ user, documents, processingFiles, setProcessingFiles }) {
  const [dragging, setDragging] = useState(false);
  const inputRef  = useRef(null);

  const processFiles = useCallback(async (files) => {
    if (!user) return;
    const valid = Array.from(files).filter(f => ALLOWED.has(getExt(f.name)));
    if (!valid.length) return;

    const items = valid.map(f => ({ name: f.name, status: 'pending', file: f }));
    setProcessingFiles(prev => [...items, ...prev]);

    const results = [];

    for (const item of items) {
      try {
        // 1. Upload to Supabase Storage
        setProcessingFiles(prev =>
          prev.map(p => p.name === item.name ? { ...p, status: 'uploading' } : p)
        );
        const fileExt = getExt(item.name);
        const fileName = `${crypto.randomUUID()}${fileExt}`;
        const storagePath = `${user.id}/${fileName}`;
        
        const { error: uploadError } = await supabase.storage
          .from('document-receipts')
          .upload(storagePath, item.file);

        if (uploadError) throw new Error(`Upload failed: ${uploadError.message}`);

        // 2. Insert stub row into DB
        setProcessingFiles(prev =>
          prev.map(p => p.name === item.name ? { ...p, status: 'parsing', path: storagePath } : p)
        );
        const { data: stubDoc, error: stubError } = await supabase
          .from('documents')
          .insert({
            user_id: user.id,
            file_name: item.file.name,
            file_size: item.file.size,
            status: 'processing',
            storage_path: storagePath,
          })
          .select()
          .single();
        if (stubError) throw new Error(`DB Error: ${stubError.message}`);

        // 3. Dispatch Async Process
        const formData = new FormData();
        formData.append('file', item.file);
        formData.append('document_id', stubDoc.id);

        const session = await supabase.auth.getSession();
        const token = session.data.session?.access_token;

        const res = await fetch(`${API_URL}/api/process_async`, { 
          method: 'POST', 
          body: formData,
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });
        
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
          throw new Error(err.detail ?? `HTTP ${res.status}`);
        }
        
        // Done with dispatch. The Realtime subscription in DashboardPage 
        // will update the table when backend finishes.
      } catch (e) {
        setProcessingFiles(prev =>
          prev.map(p => p.name === item.name ? { ...p, status: 'error', error: e.message } : p)
        );
      }
    }
  }, [user, setProcessingFiles]);

  // Effect: Watch global documents array to mark processingFiles as "done"
  useEffect(() => {
    setProcessingFiles(prev => prev.map(p => {
      if (p.status !== 'done' && p.status !== 'error') {
        const finishedDoc = documents.find(d => d.file_name === p.name && (d.status === 'processed' || d.status === 'failed'));
        if (finishedDoc) {
          return { ...p, status: finishedDoc.status === 'processed' ? 'done' : 'error', error: finishedDoc.status === 'failed' ? 'Failed in backend' : undefined };
        }
      }
      return p;
    }));
  }, [documents, setProcessingFiles]);

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    processFiles(e.dataTransfer.files);
  };

  const onDragOver = (e) => { e.preventDefault(); setDragging(true); };
  const onDragLeave = () => setDragging(false);

  const onInputChange = (e) => {
    processFiles(e.target.files);
    e.target.value = '';
  };

  return (
    <div>
      <div
        id="upload-zone"
        className={`${styles.zone} ${dragging ? styles.zoneDragging : ''}`}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        aria-label="Upload documents"
        onKeyDown={e => e.key === 'Enter' && inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.webp,.tiff,.tif"
          multiple
          className="sr-only"
          onChange={onInputChange}
          id="file-input"
        />
        <div className={`${styles.iconWrap} ${dragging ? styles.iconWrapActive : ''}`}>
          <Upload size={28} />
        </div>
        <div className={styles.zoneText}>
          <span className={styles.zoneTitle}>
            {dragging ? 'Drop files here' : 'Drop files or click to browse'}
          </span>
          <span className={styles.zoneSub}>PDF, PNG, JPG, WEBP, TIFF — up to 20 files at once</span>
        </div>
        <div className={styles.formats}>
          {['PDF', 'PNG', 'JPG', 'WEBP', 'TIFF'].map(f => (
            <span key={f} className="badge badge-muted">{f}</span>
          ))}
        </div>
      </div>

      {processingFiles.length > 0 && (
        <div className={`card ${styles.fileList}`}>
          <div className={styles.fileListHeader}>
            <span>Processing Queue</span>
            <span className="badge badge-pine">{processingFiles.length}</span>
          </div>
          <div className={styles.fileListBody}>
            {processingFiles.map((item, i) => <FileRow key={`${item.name}-${i}`} item={item} />)}
          </div>
        </div>
      )}
    </div>
  );
}
