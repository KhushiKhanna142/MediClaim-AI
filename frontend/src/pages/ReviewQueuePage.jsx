import { useEffect, useState } from 'react';
import { UserCheck, ArrowRight, Filter, AlertTriangle } from 'lucide-react';
import { api } from '../api';
import { formatINR, getPolicyMeta } from '../utils/format';

export function ReviewQueuePage({ reviewerName, onSelectClaim, onNavigate }) {
  const [queue, setQueue] = useState([]);
  const [loading, setLoading] = useState(true);
  const [policyFilter, setPolicyFilter] = useState('All');
  const [reasonFilter, setReasonFilter] = useState('All');
  const [assigneeFilter, setAssigneeFilter] = useState('All');

  const fetchQueue = async () => {
    setLoading(true);
    try {
      const data = await api.getQueue();
      setQueue(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQueue();
  }, []);

  const handleTake = async (claimId) => {
    await api.takeClaim(claimId, reviewerName);
    await fetchQueue();
  };

  const policies = ['All', ...Array.from(new Set(queue.map((c) => c.policy_id)))];
  const reasons = ['All', 'missing_documents', 'total_mismatch', 'verifier_failed', 'low_confidence'];

  const filtered = queue.filter((c) => {
    if (policyFilter !== 'All' && c.policy_id !== policyFilter) return false;
    if (reasonFilter !== 'All') {
      const allTags = [...(c.flags || []), ...(c.reasons || [])].join(' ').toLowerCase();
      if (!allTags.includes(reasonFilter.toLowerCase())) return false;
    }
    if (assigneeFilter === 'Unassigned' && c.assignee) return false;
    if (assigneeFilter === 'My Claims' && c.assignee !== reviewerName) return false;
    return true;
  });

  const myCount = queue.filter((c) => c.assignee === reviewerName).length;
  const unassignedCount = queue.filter((c) => !c.assignee).length;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Human Review Queue</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Claims flagged by deterministic validation or verifier checks awaiting human adjudicator sign-off.
        </p>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
          <div className="text-[11px] font-semibold uppercase text-slate-500">Total Pending Review</div>
          <div className="text-2xl font-extrabold text-slate-900 mt-1 tabular-nums">{queue.length}</div>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
          <div className="text-[11px] font-semibold uppercase text-slate-500">Assigned to {reviewerName.split(',')[0]}</div>
          <div className="text-2xl font-extrabold text-blue-700 mt-1 tabular-nums">{myCount}</div>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
          <div className="text-[11px] font-semibold uppercase text-slate-500">Unassigned Claims</div>
          <div className="text-2xl font-extrabold text-amber-700 mt-1 tabular-nums">{unassignedCount}</div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white border border-slate-200 rounded-xl p-3.5 shadow-xs flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-600">
          <Filter className="w-3.5 h-3.5" />
          Filters:
        </div>
        <select
          value={policyFilter}
          onChange={(e) => setPolicyFilter(e.target.value)}
          className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-slate-700"
        >
          {policies.map((p) => (
            <option key={p} value={p}>
              Policy: {p === 'All' ? 'All' : getPolicyMeta(p).label}
            </option>
          ))}
        </select>

        <select
          value={reasonFilter}
          onChange={(e) => setReasonFilter(e.target.value)}
          className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-slate-700"
        >
          {reasons.map((r) => (
            <option key={r} value={r}>
              Reason: {r === 'All' ? 'All' : r.replace('_', ' ')}
            </option>
          ))}
        </select>

        <select
          value={assigneeFilter}
          onChange={(e) => setAssigneeFilter(e.target.value)}
          className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-slate-700"
        >
          <option value="All">Assignee: All</option>
          <option value="Unassigned">Assignee: Unassigned</option>
          <option value="My Claims">Assignee: My Claims</option>
        </select>
      </div>

      {/* Queue Table */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-xs text-slate-500">Loading review queue...</div>
        ) : filtered.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-500">No claims match the current filters.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 text-slate-600 border-b border-slate-200">
                <tr>
                  <th className="py-3 px-4 font-semibold">Claim ID</th>
                  <th className="py-3 px-4 font-semibold">Policy & Patient</th>
                  <th className="py-3 px-4 font-semibold text-right">Billed Amount</th>
                  <th className="py-3 px-4 font-semibold">Escalation Reasons</th>
                  <th className="py-3 px-4 font-semibold">Assignee</th>
                  <th className="py-3 px-4 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map((c) => {
                  const meta = getPolicyMeta(c.policy_id);
                  const tags = c.flags?.length ? c.flags : ['needs_review'];
                  return (
                    <tr key={c.id} className="hover:bg-slate-50/70">
                      <td className="py-3 px-4 font-mono font-semibold text-blue-700">{c.id}</td>
                      <td className="py-3 px-4">
                        <div className="font-semibold text-slate-900">{meta.label}</div>
                        <div className="text-slate-500">{c.patient_name || '—'}</div>
                      </td>
                      <td className="py-3 px-4 text-right font-semibold text-slate-900 tabular-nums">
                        {formatINR(c.billed_amount)}
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex flex-wrap gap-1">
                          {tags.map((t) => (
                            <span
                              key={t}
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200 font-medium"
                            >
                              <AlertTriangle className="w-3 h-3 text-amber-600" />
                              {t.replace('validation:', '').replace(/_/g, ' ')}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        {c.assignee ? (
                          <span className="inline-flex items-center gap-1 text-slate-700 font-medium">
                            <UserCheck className="w-3.5 h-3.5 text-emerald-600" />
                            {c.assignee.split(',')[0]}
                          </span>
                        ) : (
                          <span className="text-slate-400 italic">Unassigned</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <div className="inline-flex items-center gap-2">
                          {!c.assignee && (
                            <button
                              type="button"
                              onClick={() => handleTake(c.id)}
                              className="px-2.5 py-1.5 rounded-lg bg-white border border-slate-300 text-slate-700 font-semibold hover:bg-slate-50"
                            >
                              Take
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => {
                              onSelectClaim(c.id);
                              onNavigate('Review Detail');
                            }}
                            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold"
                          >
                            Review
                            <ArrowRight className="w-3 h-3" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

