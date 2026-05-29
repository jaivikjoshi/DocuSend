import { useState, useEffect } from 'react';
import { supabase } from '../lib/supabaseClient';
import Sidebar from '../components/Sidebar';
import UploadZone from '../components/UploadZone';
import DocumentTable from '../components/DocumentTable';
import DocumentDetail from '../components/DocumentDetail';
import ExportPanel from '../components/ExportPanel';

export const VIEWS = {
  DASHBOARD: 'dashboard',
  DOCUMENTS: 'documents',
  EXPORT:    'export',
};

export default function DashboardPage({ session }) {
  const [view,            setView]            = useState(VIEWS.DASHBOARD);
  const [documents,       setDocuments]       = useState([]);
  const [selectedDoc,     setSelectedDoc]     = useState(null);
  const [processingFiles, setProcessingFiles] = useState([]);
  const [loadingDocs,     setLoadingDocs]     = useState(true);

  useEffect(() => {
    async function loadDocuments() {
      setLoadingDocs(true);
      try {
        const { data, error } = await supabase
          .from('documents')
          .select(`*, line_items(*)`)
          .order('created_at', { ascending: false });

        if (error) throw error;
        setDocuments(data || []);
      } catch (err) {
        console.error("Error loading documents:", err);
      } finally {
        setLoadingDocs(false);
      }
    }
    
    if (session?.user?.id) {
      loadDocuments();
    }
  }, [session?.user?.id]);

  const addDocuments = (newDocs) => {
    setDocuments(prev => [...newDocs, ...prev]);
  };

  const updateDocument = (updatedDoc) => {
    setDocuments(prev =>
      prev.map(d => d.id === updatedDoc.id ? updatedDoc : d)
    );
    setSelectedDoc(updatedDoc);
  };

  const deleteDocument = async (docId) => {
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
        activeView={view}
        onViewChange={(v) => { setView(v); setSelectedDoc(null); }}
        documentCount={documents.length}
      />

      <main className="main-content">
        {view === VIEWS.DASHBOARD && (
          <>
            <div className="page-header animate-fade-up">
              <h1>Dashboard</h1>
              <p>Upload receipts and invoices to extract data automatically.</p>
            </div>
            <div className="page-body">
              <UploadZone
                user={session.user}
                onDocumentsProcessed={addDocuments}
                processingFiles={processingFiles}
                setProcessingFiles={setProcessingFiles}
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
              <p>Download your extracted data as JSON or CSV.</p>
            </div>
            <div className="page-body">
              <ExportPanel documents={documents} />
            </div>
          </>
        )}
      </main>
    </div>
  );
}
