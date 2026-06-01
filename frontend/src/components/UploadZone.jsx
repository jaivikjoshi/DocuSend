import { useCallback, useRef, useState, useEffect } from 'react';
import { Upload, FileText, CheckCircle, XCircle } from 'lucide-react';
import styles from './UploadZone.module.css';

import { supabase } from '../lib/supabaseClient';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
const STORAGE_BUCKET = 'documents';
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

export default function UploadZone({
  user,
  documents,
  processingFiles,
  setProcessingFiles,
  onDocumentAccepted,
  onDocumentUpdate,
}) {
  const [dragging, setDragging] = useState(false);
  const inputRef  = useRef(null);

  const processFiles = useCallback(async (files) => {
    if (!user) return;
    const valid = Array.from(files).filter(f => ALLOWED.has(getExt(f.name)));
    if (!valid.length) return;

    const items = valid.map(f => ({ id: crypto.randomUUID(), name: f.name, status: 'pending', file: f }));
    setProcessingFiles(prev => [...items, ...prev]);

    for (const item of items) {
      let stubDoc = null;
      try {
        // 1. Insert an idempotent processing row before uploading.
        setProcessingFiles(prev =>
          prev.map(p => p.id === item.id ? { ...p, status: 'uploading' } : p)
        );
        const { data: insertedStub, error: stubError } = await supabase
          .from('documents')
          .insert({
            user_id: user.id,
            file_name: item.file.name,
            file_size: item.file.size,
            status: 'processing',
          })
          .select()
          .single();
        if (stubError) throw new Error(`DB Error: ${stubError.message}`);
        stubDoc = insertedStub;
        onDocumentAccepted?.(stubDoc);

        // 2. Upload once to private Supabase Storage.
        const fileExt = getExt(item.name);
        const fileName = `${crypto.randomUUID()}${fileExt}`;
        const storagePath = `${user.id}/${stubDoc.id}/${fileName}`;
        
        const { error: uploadError } = await supabase.storage
          .from(STORAGE_BUCKET)
          .upload(storagePath, item.file, { contentType: item.file.type || undefined });

        if (uploadError) throw new Error(`Upload failed: ${uploadError.message}`);

        const { data: updatedStub, error: pathError } = await supabase
          .from('documents')
          .update({ storage_path: storagePath })
          .eq('id', stubDoc.id)
          .select()
          .single();
        if (pathError) throw new Error(`DB Error: ${pathError.message}`);
        stubDoc = updatedStub;
        onDocumentUpdate?.(stubDoc);

        // 3. Dispatch async processing by storage path. The backend downloads
        // the private object with this user's JWT and verifies row ownership.
        setProcessingFiles(prev =>
          prev.map(p => p.id === item.id ? { ...p, status: 'parsing', documentId: stubDoc.id, path: storagePath } : p)
        );
        const session = await supabase.auth.getSession();
        const token = session.data.session?.access_token;

        const res = await fetch(`${API_URL}/api/process_async`, { 
          method: 'POST', 
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ document_id: stubDoc.id, storage_path: storagePath }),
        });
        
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
          throw new Error(err.detail ?? `HTTP ${res.status}`);
        }

        pollDocument(stubDoc.id, onDocumentUpdate).catch(() => {});
      } catch (e) {
        if (stubDoc?.id) {
          await supabase
            .from('documents')
            .update({ status: 'failed', warnings: [e.message] })
            .eq('id', stubDoc.id);
        }
        setProcessingFiles(prev =>
          prev.map(p => p.id === item.id ? { ...p, status: 'error', error: e.message } : p)
        );
      }
    }
  }, [user, setProcessingFiles, onDocumentAccepted, onDocumentUpdate]);

  // Effect: Watch global documents array to mark processingFiles as "done"
  useEffect(() => {
    setProcessingFiles(prev => {
      let changed = false;
      const next = prev.map(p => {
        if (p.status !== 'done' && p.status !== 'error') {
          const finishedDoc = documents.find(d => 
            (p.documentId ? d.id === p.documentId : d.file_name === p.name) && 
            (d.status === 'processed' || d.status === 'failed' || d.status === 'review')
          );
          if (finishedDoc) {
            changed = true;
            return { ...p, status: finishedDoc.status === 'failed' ? 'error' : 'done', error: finishedDoc.status === 'failed' ? 'Failed in backend' : undefined };
          }
        }
        return p;
      });
      return changed ? next : prev;
    });
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
          {processingFiles.map((item, i) => <FileRow key={item.id ?? `${item.name}-${i}`} item={item} />)}
        </div>
      </div>
    )}
  </div>
);
}

async function pollDocument(documentId, onDocumentUpdate) {
  for (let i = 0; i < 20; i += 1) {
    await new Promise(resolve => setTimeout(resolve, i < 2 ? 800 : 1500));
    const { data, error } = await supabase
      .from('documents')
      .select('*, line_items(*)')
      .eq('id', documentId)
      .single();
    if (error || !data) continue;
    onDocumentUpdate?.(data);
    if (['processed', 'review', 'failed'].includes(data.status)) return data;
  }
  return null;
}
