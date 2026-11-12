import { useEffect, useState } from 'react';
import {
  FileText,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  Maximize2,
  X,
} from 'lucide-react';
import { api } from '../api';

export function DocumentViewer({ claimId, files = [], defaultFile = 'hospital_bill.pdf', compact = false }) {
  const [selectedFile, setSelectedFile] = useState(
    files.includes(defaultFile) ? defaultFile : files[0] || null
  );
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [dpi, setDpi] = useState(130);
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    if (files.length > 0 && (!selectedFile || !files.includes(selectedFile))) {
      setSelectedFile(files.includes(defaultFile) ? defaultFile : files[0]);
      setPage(1);
    }
  }, [claimId, files, defaultFile]);

  useEffect(() => {
    if (!claimId || !selectedFile) return;
    let cancelled = false;
    api
      .getFileInfo(claimId, selectedFile)
      .then((info) => {
        if (!cancelled) {
          setTotalPages(info.pages || 1);
          setPage(1);
        }
      })
      .catch(() => {
        if (!cancelled) setTotalPages(1);
      });
    return () => {
      cancelled = true;
    };
  }, [claimId, selectedFile]);

  const formatDocLabel = (name) =>
    name.replace('.pdf', '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <div className="space-y-3">
      {/* Documents Checklist Card */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between bg-slate-50/70">
          <div className="flex items-center gap-2 font-semibold text-sm text-slate-800">
            <FileText className="w-4 h-4 text-blue-600" />
            Documents ({files.length})
          </div>
          <span className="text-[11px] font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
            Verified
          </span>
        </div>
        <div className="p-2 divide-y divide-slate-100 max-h-48 overflow-y-auto">
          {files.length === 0 ? (
            <p className="text-xs text-slate-500 p-2">No documents attached.</p>
          ) : (
            files.map((fname) => {
              const active = fname === selectedFile;
              return (
                <button
                  key={fname}
                  type="button"
                  onClick={() => setSelectedFile(fname)}
                  className={`w-full flex items-center justify-between px-2.5 py-2 text-left rounded-lg text-xs transition-colors ${
                    active
                      ? 'bg-blue-50 text-blue-700 font-semibold'
                      : 'text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  <span className="flex items-center gap-2 truncate">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                    <span className="truncate">{formatDocLabel(fname)}</span>
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono ml-2">.pdf</span>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Interactive PDF Page Frame */}
      {selectedFile && (
        <div className="bg-slate-800 rounded-xl overflow-hidden shadow-sm border border-slate-700">
          {/* Top Page Navigation Bar */}
          <div className="flex items-center justify-between px-3 py-2 bg-slate-900 text-slate-200 text-xs">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="p-1 rounded hover:bg-slate-700 disabled:opacity-35"
              title="Previous page"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="font-medium tabular-nums">
              {page} / {totalPages}
            </span>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="p-1 rounded hover:bg-slate-700 disabled:opacity-35"
              title="Next page"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          {/* Rendered Page Image */}
          <div className={`p-3 bg-slate-700/60 flex justify-center overflow-auto ${compact ? 'max-h-96' : 'max-h-[540px]'}`}>
            <img
              src={api.getFilePageUrl(claimId, selectedFile, page, dpi)}
              alt={`${selectedFile} page ${page}`}
              className="bg-white rounded shadow-md max-w-full h-auto object-contain"
            />
          </div>

          {/* Bottom Zoom Bar */}
          <div className="flex items-center justify-between px-4 py-2 bg-slate-900 text-slate-300 text-xs">
            <button
              type="button"
              onClick={() => setDpi((d) => Math.min(220, d + 25))}
              className="p-1 rounded hover:bg-slate-700 flex items-center gap-1"
              title="Zoom in"
            >
              <ZoomIn className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => setDpi((d) => Math.max(80, d - 25))}
              className="p-1 rounded hover:bg-slate-700 flex items-center gap-1"
              title="Zoom out"
            >
              <ZoomOut className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => setFullscreen(true)}
              className="p-1 rounded hover:bg-slate-700 flex items-center gap-1"
              title="Fullscreen"
            >
              <Maximize2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Fullscreen Modal */}
      {fullscreen && selectedFile && (
        <div className="fixed inset-0 z-50 bg-slate-900/75 flex items-center justify-center p-6">
          <div className="bg-white rounded-2xl max-w-4xl w-full max-h-[90vh] flex flex-col overflow-hidden shadow-2xl">
            <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between">
              <span className="font-semibold text-sm text-slate-800">
                {formatDocLabel(selectedFile)} — Page {page} of {totalPages}
              </span>
              <button
                type="button"
                onClick={() => setFullscreen(false)}
                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 overflow-auto bg-slate-100 flex justify-center">
              <img
                src={api.getFilePageUrl(claimId, selectedFile, page, 180)}
                alt={`${selectedFile} fullscreen`}
                className="bg-white shadow-lg rounded max-w-full"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

