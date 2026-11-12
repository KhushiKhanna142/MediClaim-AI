import { useState } from 'react';
import { ChevronDown, ChevronRight, ExternalLink } from 'lucide-react';

export function ClauseCard({
  clauseId,
  section,
  insurer,
  pageStart,
  passage,
  defaultExpanded = false,
  onExplore,
}) {
  const [open, setOpen] = useState(defaultExpanded);

  return (
    <div className="border border-slate-200 rounded-lg bg-white overflow-hidden transition-all">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full px-3.5 py-2.5 flex items-center justify-between text-left hover:bg-slate-50 transition-colors"
      >
        <div className="flex items-center gap-2 min-w-0">
          {open ? (
            <ChevronDown className="w-4 h-4 text-slate-500 shrink-0" />
          ) : (
            <ChevronRight className="w-4 h-4 text-slate-500 shrink-0" />
          )}
          <span className="font-semibold text-xs text-slate-900 truncate">
            Clause {clauseId}
            {section ? ` — ${section}` : ''}
          </span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0 ml-2">
          {insurer && (
            <span className="px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide rounded bg-slate-100 text-slate-700 border border-slate-200">
              {insurer}
            </span>
          )}
          {pageStart && (
            <span className="px-2 py-0.5 text-[10px] font-medium rounded bg-blue-50 text-blue-700 border border-blue-200">
              Pg. {pageStart}
            </span>
          )}
        </div>
      </button>

      {open && (
        <div className="px-4 pb-3 pt-1 border-t border-slate-100 bg-slate-50/50">
          <p className="text-xs text-slate-700 leading-relaxed italic border-l-2 border-blue-500 pl-3 my-1.5">
            "{passage}"
          </p>
          {onExplore && (
            <div className="flex justify-end mt-2">
              <button
                type="button"
                onClick={() => onExplore(clauseId)}
                className="inline-flex items-center gap-1 text-[11px] font-semibold text-blue-600 hover:text-blue-800"
              >
                Open in Policy Explorer
                <ExternalLink className="w-3 h-3" />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

