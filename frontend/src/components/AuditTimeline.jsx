import { CheckCircle2 } from 'lucide-react';

export function AuditTimeline({ entries = [], createdTime }) {
  const defaultEvents = [
    { label: 'Claim created', ts: createdTime ? createdTime.slice(0, 16).replace('T', ', ') : 'Seeded' },
    { label: 'Processing completed', ts: createdTime ? createdTime.slice(0, 16).replace('T', ', ') : 'Seeded' },
    { label: 'Decision generated', ts: createdTime ? createdTime.slice(0, 16).replace('T', ', ') : 'Seeded' },
  ];

  return (
    <div className="space-y-3">
      {entries.length === 0 ? (
        <div className="relative pl-5 space-y-3 before:content-[''] before:absolute before:left-[7px] before:top-2 before:bottom-2 before:w-0.5 before:bg-emerald-200">
          {defaultEvents.map((ev, i) => (
            <div key={i} className="relative flex items-center justify-between text-xs">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 bg-white absolute -left-5" />
              <span className="text-slate-700 font-medium">{ev.label}</span>
              <span className="text-slate-400 text-[11px] tabular-nums">{ev.ts}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="relative pl-5 space-y-3.5 before:content-[''] before:absolute before:left-[7px] before:top-2 before:bottom-2 before:w-0.5 before:bg-blue-200">
          {entries.map((item) => (
            <div key={item.review_id} className="relative text-xs">
              <CheckCircle2 className="w-3.5 h-3.5 text-blue-600 bg-white absolute -left-5 top-0.5" />
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-900">
                  {item.action.replace('_', ' ').toUpperCase()} by {item.reviewer}
                </span>
                <span className="text-[11px] text-slate-400 tabular-nums">
                  {(item.created_time || '').slice(0, 16).replace('T', ', ')}
                </span>
              </div>
              {item.reason && (
                <p className="text-slate-600 italic mt-0.5">"{item.reason}"</p>
              )}
              {item.field_edits && item.field_edits.length > 0 && (
                <ul className="mt-1 space-y-0.5 text-[11px] text-slate-700 bg-slate-50 p-1.5 rounded border border-slate-200">
                  {item.field_edits.map((fe, idx) => (
                    <li key={idx}>
                      <code className="text-blue-700">{fe.field_name}</code>: {fe.old_value} →{' '}
                      <strong>{fe.new_value}</strong>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

