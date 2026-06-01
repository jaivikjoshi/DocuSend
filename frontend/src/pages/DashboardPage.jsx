import { useState, useEffect } from 'react';
import { supabase } from '../lib/supabaseClient';
import Sidebar from '../components/Sidebar';
import UploadZone from '../components/UploadZone';
import DocumentTable from '../components/DocumentTable';
import DocumentDetail from '../components/DocumentDetail';
import ExportPanel from '../components/ExportPanel';

const VIEWS = {
  DASHBOARD: 'dashboard',
  DOCUMENTS: 'documents',
  EXPORT:    'export',
};

export default function DashboardPage({ session, isGuest = false, onExitGuest }) {
  const [view,            setView]            = useState(VIEWS.DASHBOARD);
  const [documents,       setDocuments]       = useState([]);
  const [selectedDoc,     setSelectedDoc]     = useState(null);
  const [processingFiles, setProcessingFiles] = useState([]);
  const [loadingDocs,     setLoadingDocs]     = useState(true);
  const [loadError,       setLoadError]       = useState('');

  useEffect(() => {
    async function loadDocuments() {
      setLoadingDocs(true);
      setLoadError('');
      try {
        const { data, error } = await supabase
          .from('documents')
          .select(`*, line_items(*)`)
          .order('created_at', { ascending: false });

        if (error) throw error;
        setDocuments(data || []);
      } catch (err) {
        console.error("Error loading documents:", err);
        setLoadError(err.message || 'Failed to load documents.');
      } finally {
        setLoadingDocs(false);
      }
    }
    
    let channel;
    if (isGuest) {
      setLoadingDocs(false);
      setLoadError('');
    } else if (session?.user?.id) {
      loadDocuments();

      // Realtime listener for async processing updates
      channel = supabase.channel('documents-channel')
        .on(
          'postgres_changes',
          { event: '*', schema: 'public', table: 'documents', filter: `user_id=eq.${session.user.id}` },
          (payload) => {
            if (payload.eventType === 'INSERT') {
              setDocuments(prev => prev.some(d => d.id === payload.new.id) ? prev : [payload.new, ...prev]);
            } else if (payload.eventType === 'UPDATE') {
              setDocuments(prev => prev.map(d => d.id === payload.new.id ? { ...d, ...payload.new } : d));
              setSelectedDoc(prev => prev?.id === payload.new.id ? { ...prev, ...payload.new } : prev);
            } else if (payload.eventType === 'DELETE') {
              setDocuments(prev => prev.filter(d => d.id !== payload.old.id));
              setSelectedDoc(prev => prev?.id === payload.old.id ? null : prev);
            }
          }
        )
        .subscribe();
    }

    return () => {
      if (channel) supabase.removeChannel(channel);
    };
  }, [isGuest, session?.user?.id]);

  const upsertDocument = (doc) => {
    setDocuments(prev =>
      prev.some(d => d.id === doc.id)
        ? prev.map(d => d.id === doc.id ? { ...d, ...doc } : d)
        : [doc, ...prev]
    );
    setSelectedDoc(prev => prev?.id === doc.id ? { ...prev, ...doc } : prev);
  };

  const updateDocument = (updatedDoc) => {
    setDocuments(prev =>
      prev.map(d => d.id === updatedDoc.id ? updatedDoc : d)
    );
    setSelectedDoc(updatedDoc);
  };

  const deleteDocument = async (docId) => {
    if (isGuest) {
      setDocuments(prev => prev.filter(d => d.id !== docId));
      setSelectedDoc(null);
      setView(VIEWS.DASHBOARD);
      return;
    }

    try {
      const { error } = await supabase.from('documents').delete().eq('id', docId);
      if (error) throw error;
      setDocuments(prev => prev.filter(d => d.id !== docId));
      setSelectedDoc(null);
      setView(VIEWS.DASHBOARD);
    } catch (err) {
      console.error("Failed to delete document:", err);
      alert("Failed to delete document");
    }
  };

  const selectDoc = (doc) => {
    setSelectedDoc(doc);
    setView(VIEWS.DOCUMENTS);
  };

  return (
    <div className="app-layout">
      <Sidebar
        user={session.user}
        isGuest={isGuest}
        onExitGuest={onExitGuest}
        activeView={view}
        onViewChange={(v) => { setView(v); setSelectedDoc(null); }}
        documentCount={documents.length}
      />

      <main className="main-content">
        {view === VIEWS.DASHBOARD && (
          <>
            <div className="page-header animate-fade-up">
              <h1>Dashboard</h1>
              <p>{isGuest ? 'Try extraction without saving files or creating an account.' : 'Upload receipts and invoices to extract data automatically.'}</p>
            </div>
            <div className="page-body">
              {isGuest && (
                <div className="alert alert-warning">
                  Guest documents stay in this browser session only. Sign in to save history, private file previews, and cloud exports.
                </div>
              )}
              {loadError && <div className="alert alert-error">{loadError}</div>}
              <UploadZone
                user={session.user}
                isGuest={isGuest}
                documents={documents}
                processingFiles={processingFiles}
                setProcessingFiles={setProcessingFiles}
                onDocumentAccepted={upsertDocument}
                onDocumentUpdate={upsertDocument}
              />
              {documents.length > 0 && (
                <DocumentTable
                  documents={documents}
                  onSelectDocument={selectDoc}
                  selectedDoc={selectedDoc}
                />
              )}
            </div>
          </>
        )}

        {view === VIEWS.DOCUMENTS && (
          <>
            <div className="page-header animate-fade-up">
              <h1>Documents</h1>
              <p>{documents.length} document{documents.length !== 1 ? 's' : ''} processed this session.</p>
            </div>
            <div className="page-body">
              {loadError && <div className="alert alert-error">{loadError}</div>}
              {loadingDocs ? (
                <div className="card card-padded empty-state"><div className="spinner"></div><p>Loading documents...</p></div>
              ) : documents.length === 0 ? (
                <div className="card card-padded">
                  <div className="empty-state">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <h3>No documents yet</h3>
                    <p>Go to the Dashboard tab and upload some documents to get started.</p>
                    <button className="btn btn-primary btn-sm" onClick={() => setView(VIEWS.DASHBOARD)}>
                      Upload Documents
                    </button>
                  </div>
                </div>
              ) : selectedDoc ? (
                <DocumentDetail
                  doc={selectedDoc}
                  isGuest={isGuest}
                  onUpdate={updateDocument}
                  onDelete={deleteDocument}
                  onClose={() => setSelectedDoc(null)}
                />
              ) : (
                <DocumentTable
                  documents={documents}
                  onSelectDocument={setSelectedDoc}
                  selectedDoc={selectedDoc}
                />
              )}
            </div>
          </>
        )}

        {view === VIEWS.EXPORT && (
          <>
            <div className="page-header animate-fade-up">
              <h1>Export</h1>
              <p>{isGuest ? 'Download guest-session data as local JSON or accounting CSV.' : 'Download your extracted data as JSON or CSV.'}</p>
            </div>
            <div className="page-body">
              {loadError && <div className="alert alert-error">{loadError}</div>}
              <ExportPanel documents={documents} isGuest={isGuest} />
            </div>
          </>
        )}
      </main>
    </div>
  );
}
