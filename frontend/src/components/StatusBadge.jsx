import { CheckCircle2, AlertTriangle, XCircle, CircleDot, Clock } from 'lucide-react';

export function StatusBadge({ status, size = 'md' }) {
  const s = (status || '').toLowerCase();
  const sizeCls = size === 'lg' ? 'px-3.5 py-1.5 text-sm' : 'px-2.5 py-1 text-xs';

  if (s === 'approve' || s === 'approved') {
    return (
      <span className={`inline-flex items-center gap-1.5 rounded-full font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 ${sizeCls}`}>
        <CheckCircle2 className="w-4 h-4 text-emerald-600" />
        Approved
      </span>
    );
  }
  if (s === 'partial' || s === 'partially_approved' || s === 'partially approved') {
    return (
      <span className={`inline-flex items-center gap-1.5 rounded-full font-semibold bg-amber-50 text-amber-800 border border-amber-300 ${sizeCls}`}>
        <CircleDot className="w-4 h-4 text-amber-600" />
        Partially Approved
      </span>
    );
  }
  if (s === 'reject' || s === 'rejected') {
    return (
      <span className={`inline-flex items-center gap-1.5 rounded-full font-semibold bg-red-50 text-red-700 border border-red-200 ${sizeCls}`}>
        <XCircle className="w-4 h-4 text-red-600" />
        Rejected
      </span>
    );
  }
  if (s === 'needs_review' || s === 'review' || s === 'sent_to_review') {
    return (
      <span className={`inline-flex items-center gap-1.5 rounded-full font-semibold bg-orange-50 text-orange-800 border border-orange-300 ${sizeCls}`}>
        <AlertTriangle className="w-4 h-4 text-orange-600" />
        Needs Review
      </span>
    );
  }
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-semibold bg-slate-100 text-slate-700 border border-slate-300 ${sizeCls}`}>
      <Clock className="w-4 h-4 text-slate-500" />
      {status || 'Pending'}
    </span>
  );
}

export function ProvenanceBadge({ source = 'text' }) {
  const s = source.toLowerCase();
  if (s.includes('ocr')) {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-semibold bg-cyan-50 text-cyan-800 border border-cyan-200">
        Read by OCR
      </span>
    );
  }
  if (s.includes('vision')) {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-semibold bg-violet-50 text-violet-800 border border-violet-200">
        Filled by vision
      </span>
    );
  }
  if (s.includes('review') || s.includes('edit')) {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
        Edited by reviewer
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-semibold bg-blue-50 text-blue-800 border border-blue-200">
      Read from text
    </span>
  );
}

