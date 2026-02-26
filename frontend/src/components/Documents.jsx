import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Upload, FileText, Trash2, RefreshCw, Building2, Plus, X, Globe } from 'lucide-react';
import { documentsApi } from '../api';
import { format } from 'date-fns';

export default function Documents() {
  const [showUpload, setShowUpload] = useState(false);
  const [showEdgar, setShowEdgar] = useState(false);
  const queryClient = useQueryClient();

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['documents'],
    queryFn: () => documentsApi.list(),
  });

  const deleteMutation = useMutation({
    mutationFn: documentsApi.delete,
    onSuccess: () => queryClient.invalidateQueries(['documents']),
  });

  const sourceTypeColors = {
    edgar: 'bg-blue-100 text-blue-700',
    pdf: 'bg-purple-100 text-purple-700',
    manual: 'bg-green-100 text-green-700',
    web: 'bg-orange-100 text-orange-700',
    text: 'bg-slate-100 text-slate-700',
  };

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Documents</h2>
            <p className="text-sm text-slate-500">
              {data?.total || 0} documents indexed
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => refetch()}
              className="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <RefreshCw className="w-5 h-5" />
            </button>
            <button
              onClick={() => setShowEdgar(true)}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-primary-600 bg-primary-50 hover:bg-primary-100 rounded-lg transition-colors"
            >
              <Building2 className="w-4 h-4" />
              Import EDGAR
            </button>
            <button
              onClick={() => setShowUpload(true)}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-lg transition-colors"
            >
              <Upload className="w-4 h-4" />
              Upload
            </button>
          </div>
        </div>
      </header>

      {/* Document list */}
      <div className="flex-1 overflow-y-auto p-6">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
          </div>
        ) : data?.documents?.length === 0 ? (
          <div className="text-center py-12">
            <FileText className="w-12 h-12 mx-auto mb-4 text-slate-300" />
            <h3 className="text-lg font-medium text-slate-900 mb-2">No documents yet</h3>
            <p className="text-slate-500 mb-6">
              Upload PDFs or import SEC filings to get started
            </p>
          </div>
        ) : (
          <div className="grid gap-4">
            {data?.documents?.map((doc) => (
              <div
                key={doc.id}
                className="bg-white rounded-xl border border-slate-200 p-4 hover:shadow-md transition-shadow"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                      <h3 className="font-medium text-slate-900 truncate">{doc.title}</h3>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${sourceTypeColors[doc.source_type] || sourceTypeColors.text}`}>
                        {doc.source_type}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 text-sm text-slate-500">
                      {doc.company_name && (
                        <span className="flex items-center gap-1">
                          <Building2 className="w-4 h-4" />
                          {doc.company_name}
                        </span>
                      )}
                      {doc.filing_type && (
                        <span>{doc.filing_type}</span>
                      )}
                      <span>{doc.chunk_count} chunks</span>
                      <span>{format(new Date(doc.created_at), 'MMM d, yyyy')}</span>
                    </div>
                    {doc.source_url && (
                      <a
                        href={doc.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 text-sm text-primary-600 hover:underline mt-2"
                      >
                        <Globe className="w-3 h-3" />
                        View source
                      </a>
                    )}
                  </div>
                  <button
                    onClick={() => {
                      if (confirm('Delete this document and all its chunks?')) {
                        deleteMutation.mutate(doc.id);
                      }
                    }}
                    className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Upload Modal */}
      {showUpload && (
        <UploadModal onClose={() => setShowUpload(false)} onSuccess={() => {
          setShowUpload(false);
          queryClient.invalidateQueries(['documents']);
        }} />
      )}

      {/* EDGAR Modal */}
      {showEdgar && (
        <EdgarModal onClose={() => setShowEdgar(false)} onSuccess={() => {
          setShowEdgar(false);
          queryClient.invalidateQueries(['documents']);
        }} />
      )}
    </div>
  );
}

function UploadModal({ onClose, onSuccess }) {
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) return;

    setLoading(true);
    setError('');

    try {
      await documentsApi.upload(file, title, null, companyName);
      onSuccess();
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-semibold text-slate-900">Upload Document</h3>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="p-3 rounded-lg bg-red-50 text-red-700 text-sm">{error}</div>
          )}

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">File</label>
            <input
              type="file"
              accept=".pdf,.txt,.md"
              onChange={(e) => setFile(e.target.files[0])}
              className="w-full px-4 py-2 border border-slate-300 rounded-lg"
              required
            />
            <p className="text-xs text-slate-500 mt-1">Supports PDF and text files</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Title (optional)</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full px-4 py-2 border border-slate-300 rounded-lg"
              placeholder="Document title"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Company (optional)</label>
            <input
              type="text"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              className="w-full px-4 py-2 border border-slate-300 rounded-lg"
              placeholder="Company name"
            />
          </div>

          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!file || loading}
              className="flex-1 px-4 py-2 text-white bg-primary-600 hover:bg-primary-700 rounded-lg disabled:opacity-50"
            >
              {loading ? 'Uploading...' : 'Upload'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function EdgarModal({ onClose, onSuccess }) {
  const [cik, setCik] = useState('');
  const [filingType, setFilingType] = useState('10-K');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!cik) return;

    setLoading(true);
    setError('');

    try {
      await documentsApi.ingestEdgar(cik, filingType);
      onSuccess();
    } catch (err) {
      setError(err.response?.data?.detail || 'EDGAR import failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-semibold text-slate-900">Import SEC Filing</h3>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="p-3 rounded-lg bg-red-50 text-red-700 text-sm">{error}</div>
          )}

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">CIK Number</label>
            <input
              type="text"
              value={cik}
              onChange={(e) => setCik(e.target.value)}
              className="w-full px-4 py-2 border border-slate-300 rounded-lg"
              placeholder="e.g., 320193 for Apple"
              required
            />
            <p className="text-xs text-slate-500 mt-1">
              Find CIK numbers at{' '}
              <a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany" target="_blank" className="text-primary-600 hover:underline">
                SEC EDGAR
              </a>
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Filing Type</label>
            <select
              value={filingType}
              onChange={(e) => setFilingType(e.target.value)}
              className="w-full px-4 py-2 border border-slate-300 rounded-lg"
            >
              <option value="10-K">10-K (Annual Report)</option>
              <option value="10-Q">10-Q (Quarterly Report)</option>
              <option value="8-K">8-K (Current Report)</option>
            </select>
          </div>

          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!cik || loading}
              className="flex-1 px-4 py-2 text-white bg-primary-600 hover:bg-primary-700 rounded-lg disabled:opacity-50"
            >
              {loading ? 'Importing...' : 'Import'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
