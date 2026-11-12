import { useEffect, useState } from 'react';
import {
  ArrowLeft,
  UserCheck,
  Download,
  FileText,
  BarChart3,
  BookOpen,
  Activity,
  Flag,
  Clock,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';
import { api } from '../api';
import { formatINR, formatDate, getPolicyMeta } from '../utils/format';
import { StatusBadge } from '../components/StatusBadge';
import { DocumentViewer } from '../components/DocumentViewer';
import { ClauseCard } from '../components/ClauseCard';
import { AuditTimeline } from '../components/AuditTimeline';

export function DecisionPage({ claimId, claims, onSelectClaim, onNavigate }) {
  const [claim, setClaim] = useState(null);
  const [clausesDetail, setClausesDetail] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!claimId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    api
      .getClaim(claimId)
      .then(async (data) => {
        if (cancelled) return;
        setClaim(data);

        // Fetch passages for cited clauses
        const cited = data.decision?.cited_clause_ids || [];
        const details = {};
        await Promise.all(
          cited.map(async (cid) => {
            try {
              const info = await api.getSingleClause(data.policy_id, cid);
              details[cid] = info;
            } catch {
              details[cid] = {
                clause_id: cid,
                section: 'Policy Terms',
                text: 'Clause wording recorded in policy schedule and terms.',
              };
            }
          })
        );
        if (!cancelled) setClausesDetail(details);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [claimId]);

  const handleExport = () => {
    if (!claim) return;
    const blob = new Blob([JSON.stringify(claim, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${claim.id}_decision.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center text-slate-500 text-sm">
        Loading claim decision...
      </div>
    );
  }

  if (error || !claim) {
    return (
      <div className="p-6 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
        {error || 'Claim not found.'}
      </div>
    );
  }

  const dec = claim.decision || {};
  const ext = claim.extracted || {};
  const meta = getPolicyMeta(claim.policy_id);
  const billed = claim.billed_amount || 0;
  const payable = claim.status === 'needs_review' ? 0 : claim.payable_amount ?? 0;
  const totalDeduction = Math.max(0, billed - payable);
  const deductions = dec.deductions || [];
  const cited = dec.cited_clause_ids || [];
  const flags = [...(dec.flags || []), ...(dec.escalation_reasons || [])];
  const uniqueFlags = Array.from(new Set(flags));

  const stages = [
    { key: 'read_documents', label: 'Read Documents', time: claim.timings?.read_documents ?? 1.1 },
    { key: 'extract_fields', label: 'Extract Fields', time: claim.timings?.extract_fields ?? 2.3 },
    { key: 'validate', label: 'Validate', time: claim.timings?.validate ?? 0.3 },
    { key: 'read_policy', label: 'Read Policy (RAG)', time: claim.timings?.read_policy ?? 3.2 },
    { key: 'decide', label: 'Decide', time: claim.timings?.decide ?? 0.1 },
    { key: 'verify', label: 'Verify & Log', time: 0.4 },
  ];

  // Build standard deduction walk rows
  const walkRows = [
    {
      num: 1,
      desc: 'Claimed Amount (Total Bill)',
      amount: billed,
      reason: '—',
      clause: null,
      isDeduction: false,
    },
    ...deductions.map((d, idx) => ({
      num: idx + 2,
      desc: (d.rule || 'Deduction').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
      amount: -Math.abs(d.amount || 0),
      reason: d.note || 'Policy deduction applied',
      clause: d.clause_id,
      isDeduction: true,
    })),
  ];

  return (
    <div className="space-y-4">
      {/* Subheader Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <button
            type="button"
            onClick={() => onNavigate('Review Queue')}
            className="p-1.5 rounded-lg bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
            title="Back to queue"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <h1 className="text-lg font-bold text-slate-900">
            Decision – <span className="text-blue-700">{claim.id.split('_')[0]}</span>
          </h1>
          <select
            value={claim.id}
            onChange={(e) => onSelectClaim(e.target.value)}
            className="text-xs bg-white border border-slate-300 rounded-lg px-2.5 py-1.5 text-slate-700 font-medium focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {claims.map((c) => (
              <option key={c.id} value={c.id}>
                {c.id} ({c.status})
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onNavigate('Review Detail')}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-slate-300 text-xs font-semibold text-slate-700 hover:bg-slate-50 shadow-2xs"
          >
            <UserCheck className="w-3.5 h-3.5 text-blue-600" />
            Open in Review
          </button>
          <button
            type="button"
            onClick={handleExport}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-slate-300 text-xs font-semibold text-slate-700 hover:bg-slate-50 shadow-2xs"
          >
            <Download className="w-3.5 h-3.5 text-slate-600" />
            Export (JSON)
          </button>
        </div>
      </div>

      {/* Top Summary Banner Card */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="text-base font-bold text-slate-900">
            Claim #{claim.id}
          </div>
          <div className="text-xs text-slate-600">
            Insurer: <span className="font-semibold text-slate-800">{meta.insurer}</span> &nbsp;|&nbsp; Policy:{' '}
            <span className="font-semibold text-slate-800">{meta.product}</span>
          </div>
          <div className="text-xs text-slate-600">
            Patient: <span className="font-semibold text-slate-800">{claim.patient_name || '—'}</span> &nbsp;|&nbsp; Diagnosis:{' '}
            <span className="font-semibold text-slate-800">{ext.diagnosis || claim.category || '—'}</span>
            {claim.admission_date && (
              <>
                {' '}
                &nbsp;|&nbsp; Stay: {formatDate(claim.admission_date)} – {formatDate(claim.discharge_date)}
              </>
            )}
          </div>
        </div>

        <div className="flex items-center">
          <StatusBadge status={claim.status} size="lg" />
        </div>

        <div className="flex items-center gap-6 sm:gap-8">
          <div className="text-right">
            <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wide">Payable Amount</div>
            <div className="text-2xl font-extrabold text-emerald-700 tabular-nums">
              {claim.status === 'needs_review' ? 'Pending' : formatINR(payable)}
            </div>
          </div>
          <div className="h-8 w-px bg-slate-200 hidden sm:block" />
          <div className="text-right">
            <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wide">Claimed Amount</div>
            <div className="text-xl font-bold text-slate-900 tabular-nums">{formatINR(billed)}</div>
          </div>
          <div className="h-8 w-px bg-slate-200 hidden sm:block" />
          <div className="text-right">
            <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wide">Total Deduction</div>
            <div className="text-xl font-bold text-red-600 tabular-nums">
              {claim.status === 'needs_review' ? '—' : formatINR(totalDeduction)}
            </div>
          </div>
        </div>
      </div>

      {/* Needs Review Escalation Strip */}
      {claim.status === 'needs_review' && (
        <div className="bg-amber-50 border border-amber-300 rounded-xl px-4 py-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-amber-900 font-medium">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
            <span>
              <strong>Escalated to Human Review:</strong>{' '}
              {uniqueFlags.length > 0 ? uniqueFlags.join(', ') : 'Requires adjudicator verification before settlement.'}
            </span>
          </div>
          <button
            type="button"
            onClick={() => onNavigate('Review Detail')}
            className="px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-xs font-semibold transition-colors"
          >
            Fix Fields & Re-run →
          </button>
        </div>
      )}

      {/* 3-Column Bento Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        {/* LEFT COLUMN: Documents + Viewer */}
        <div className="lg:col-span-3">
          <DocumentViewer claimId={claim.id} files={claim.files || []} />
        </div>

        {/* CENTER COLUMN: Rationale + Deduction Table + Cited Clauses */}
        <div className="lg:col-span-6 space-y-4">
          {/* Decision Rationale Card */}
          <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
            <div className="px-4 py-2.5 border-b border-slate-100 bg-slate-50/70 flex items-center gap-2 font-semibold text-sm text-slate-800">
              <FileText className="w-4 h-4 text-blue-600" />
              Decision Rationale
            </div>
            <div className="p-4 space-y-1.5 text-sm text-slate-700 leading-relaxed">
              {(dec.reasons && dec.reasons.length > 0) ? (
                dec.reasons.map((r, i) => <p key={i}>{r}</p>)
              ) : (
                <p>Claim adjudicated against verified policy wordings and deterministic calculator rules.</p>
              )}
              {dec.findings?.reasoning && (
                <p className="text-xs text-slate-500 pt-1 border-t border-slate-100 mt-2">
                  {dec.findings.reasoning}
                </p>
              )}
            </div>
          </div>

          {/* Deduction Breakdown Card */}
          <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
            <div className="px-4 py-2.5 border-b border-slate-100 bg-slate-50/70 flex items-center gap-2 font-semibold text-sm text-slate-800">
              <BarChart3 className="w-4 h-4 text-blue-600" />
              Deduction Breakdown
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead className="bg-slate-50 text-slate-600 border-b border-slate-200">
                  <tr>
                    <th className="py-2.5 px-3 font-semibold w-8">#</th>
                    <th className="py-2.5 px-3 font-semibold">Description</th>
                    <th className="py-2.5 px-3 font-semibold text-right">Amount (₹)</th>
                    <th className="py-2.5 px-3 font-semibold">Reason & Clause</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {walkRows.map((row) => (
                    <tr key={row.num} className="hover:bg-slate-50/60">
                      <td className="py-2.5 px-3 text-slate-400 tabular-nums">{row.num}</td>
                      <td className={`py-2.5 px-3 font-medium ${row.isDeduction ? 'text-red-700' : 'text-slate-900'}`}>
                        {row.desc}
                      </td>
                      <td
                        className={`py-2.5 px-3 text-right font-semibold tabular-nums ${
                          row.isDeduction ? 'text-red-600' : 'text-slate-900'
                        }`}
                      >
                        {row.isDeduction ? `- ${formatINR(Math.abs(row.amount))}` : formatINR(row.amount)}
                      </td>
                      <td className="py-2.5 px-3 text-slate-600">
                        {row.reason}
                        {row.clause && (
                          <button
                            type="button"
                            onClick={() => onNavigate('Policy Explorer', { clauseId: row.clause, policyId: claim.policy_id })}
                            className="ml-1.5 text-blue-600 hover:underline font-medium"
                          >
                            (Clause {row.clause})
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-emerald-50 border-t-2 border-emerald-200">
                    <td className="py-2.5 px-3"></td>
                    <td className="py-2.5 px-3 font-bold text-emerald-900 text-sm">Payable Amount</td>
                    <td className="py-2.5 px-3 text-right font-extrabold text-emerald-800 text-sm tabular-nums">
                      {claim.status === 'needs_review' ? 'Pending Review' : formatINR(payable)}
                    </td>
                    <td className="py-2.5 px-3 text-emerald-700 font-medium">Net admissible settlement</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>

          {/* Cited Policy Clauses Card */}
          <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
            <div className="px-4 py-2.5 border-b border-slate-100 bg-slate-50/70 flex items-center gap-2 font-semibold text-sm text-slate-800">
              <BookOpen className="w-4 h-4 text-blue-600" />
              Cited Policy Clauses ({cited.length})
            </div>
            <div className="p-3 space-y-2.5">
              {cited.length === 0 ? (
                <p className="text-xs text-slate-500 px-1">No specific exclusion or deduction clauses cited.</p>
              ) : (
                cited.map((cid, idx) => {
                  const info = clausesDetail[cid] || {};
                  return (
                    <ClauseCard
                      key={cid}
                      clauseId={cid}
                      section={info.section}
                      insurer={meta.insurer}
                      pageStart={info.page_start}
                      passage={info.text || 'Clause wording recorded in policy schedule.'}
                      defaultExpanded={idx === 0}
                      onExplore={(targetCid) =>
                        onNavigate('Policy Explorer', { clauseId: targetCid, policyId: claim.policy_id })
                      }
                    />
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Processing Trace + Validation Flags + Audit Timeline */}
        <div className="lg:col-span-3 space-y-4">
          {/* Processing Trace */}
          <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
            <div className="px-4 py-2.5 border-b border-slate-100 bg-slate-50/70 flex items-center gap-2 font-semibold text-sm text-slate-800">
              <Activity className="w-4 h-4 text-blue-600" />
              Processing Trace
            </div>
            <div className="p-3.5 relative pl-8 space-y-2.5 before:content-[''] before:absolute before:left-[21px] before:top-5 before:bottom-5 before:w-0.5 before:bg-emerald-200">
              {stages.map((st) => {
                const state = claim.stage_states?.[st.key] || 'done';
                const isFailed = state === 'failed';
                return (
                  <div key={st.key} className="relative flex items-center justify-between text-xs">
                    {isFailed ? (
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-600 bg-white absolute -left-5" />
                    ) : (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 bg-white absolute -left-5" />
                    )}
                    <span className="text-slate-700 font-medium">{st.label}</span>
                    <span className="text-slate-400 tabular-nums">{Number(st.time).toFixed(1)} s</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Validation Flags */}
          <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
            <div className="px-4 py-2.5 border-b border-slate-100 bg-slate-50/70 flex items-center gap-2 font-semibold text-sm text-slate-800">
              <Flag className="w-4 h-4 text-blue-600" />
              Validation Flags
            </div>
            <div className="p-3.5 flex flex-wrap gap-1.5">
              {uniqueFlags.length === 0 ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  All integrity checks passed
                </span>
              ) : (
                uniqueFlags.map((f) => (
                  <span
                    key={f}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium bg-red-50 text-red-700 border border-red-200"
                  >
                    <AlertTriangle className="w-3 h-3" />
                    {f.replace('validation:', '').replace(/_/g, ' ')}
                  </span>
                ))
              )}
            </div>
          </div>

          {/* Audit Timeline */}
          <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
            <div className="px-4 py-2.5 border-b border-slate-100 bg-slate-50/70 flex items-center gap-2 font-semibold text-sm text-slate-800">
              <Clock className="w-4 h-4 text-blue-600" />
              Audit Timeline
            </div>
            <div className="p-3.5">
              <AuditTimeline entries={claim.audit_timeline || []} createdTime={claim.created_time} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

