import { useEffect, useState } from 'react';
import { AlertTriangle, Zap, CheckCircle2, ShieldAlert, ArrowRight } from 'lucide-react';
import { api } from '../api';
import { formatINR, getPolicyMeta } from '../utils/format';
import { DocumentViewer } from '../components/DocumentViewer';
import { ProvenanceBadge, StatusBadge } from '../components/StatusBadge';
import { AuditTimeline } from '../components/AuditTimeline';

export function ReviewDetailPage({ claimId, claims, reviewerName, onSelectClaim, onNavigate }) {
  const [claim, setClaim] = useState(null);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({});
  const [rerunResult, setRerunResult] = useState(null);
  const [rerunning, setRerunning] = useState(false);

  const [actionType, setActionType] = useState('confirm');
  const [overrideStatus, setOverrideStatus] = useState('approve');
  const [overridePayable, setOverridePayable] = useState(0);
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    if (!claimId) return;
    let cancelled = false;
    setLoading(true);
    setRerunResult(null);
    setMsg(null);

    api.getClaim(claimId).then((data) => {
      if (cancelled) return;
      setClaim(data);
      const ext = data.extracted || {};
      setForm({
        diagnosis: ext.diagnosis || '',
        claimed_total: ext.claimed_total ?? ext.stated_total ?? data.billed_amount ?? 0,
        bill_total: ext.bill_total ?? data.billed_amount ?? 0,
        sum_insured: ext.sum_insured ?? 500000,
        copay_pct: ext.copay_pct ?? 0,
        room_limit_per_day: ext.room_limit_per_day ?? 0,
      });
      setOverridePayable(data.billed_amount || 0);
      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [claimId]);

  const handleRerun = async () => {
    if (!claim) return;
    setRerunning(true);
    setMsg(null);
    try {
      const updates = {
        diagnosis: form.diagnosis,
        claimed_total: Number(form.claimed_total),
        bill_total: Number(form.bill_total),
        sum_insured: Number(form.sum_insured),
        copay_pct: Number(form.copay_pct),
        room_limit_per_day: Number(form.room_limit_per_day) > 0 ? Number(form.room_limit_per_day) : null,
      };

      // Balance items if bill_total was corrected
      const extItems = claim.extracted?.items;
      if (Array.isArray(extItems) && extItems.length > 0) {
        const itemsCopy = extItems.map((it) => ({ ...it }));
        const itemsSum = itemsCopy.reduce((s, it) => s + Number(it.amount || 0), 0);
        if (itemsSum !== Number(form.bill_total)) {
          itemsCopy[0].amount = Number(itemsCopy[0].amount || 0) + (Number(form.bill_total) - itemsSum);
          updates.items = itemsCopy;
        }
      }

      const res = await api.rerunDecision(claim.id, updates);
      setRerunResult(res);
      const refreshed = await api.getClaim(claim.id);
      setClaim(refreshed);
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    } finally {
      setRerunning(false);
    }
  };

  const handleSubmitReview = async () => {
    if (actionType === 'override' && !reason.trim()) {
      setMsg({ type: 'error', text: 'Audit rule: A written reason is required when overriding a system decision.' });
      return;
    }
    setSubmitting(true);
    setMsg(null);
    try {
      const payload = {
        reviewer: reviewerName,
        action: actionType,
        reason: reason.trim() || null,
        field_edits: [
          {
            field_name: 'bill_total',
            old_value: claim.billed_amount,
            new_value: Number(form.bill_total),
          },
        ],
        override_status: actionType === 'override' ? overrideStatus : null,
        override_payable: actionType === 'override' ? Number(overridePayable) : null,
      };
      await api.submitReview(claim.id, payload);
      onNavigate('Decision');
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    } finally {
      setSubmitting(false);
    }
  };

  if (loading || !claim) {
    return <div className="p-8 text-center text-sm text-slate-500">Loading review workspace...</div>;
  }

  const meta = getPolicyMeta(claim.policy_id);
  const valFlags = [...(claim.decision?.flags || []), ...(claim.decision?.escalation_reasons || [])];
  const hasTotalMismatch = valFlags.some((f) => f.includes('total') || f.includes('mismatch'));
  const visionFields = claim.extracted?.vision_filled || [];

  const reviewCandidates = claims.filter((c) => c.status === 'needs_review' || c.id === claim.id);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900">
            Human Review Detail — <span className="text-blue-700 font-mono text-base">{claim.id}</span>
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Reviewer: <strong>{reviewerName}</strong> &nbsp;·&nbsp; Policy: <strong>{meta.label}</strong>
          </p>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={claim.id}
            onChange={(e) => onSelectClaim(e.target.value)}
            className="text-xs bg-white border border-slate-300 rounded-lg px-2.5 py-1.5 font-medium text-slate-700"
          >
            {reviewCandidates.map((c) => (
              <option key={c.id} value={c.id}>
                {c.id} ({c.status})
              </option>
            ))}
          </select>
          <StatusBadge status={claim.status} />
        </div>
      </div>

      {/* Flag Alert */}
      {valFlags.length > 0 && (
        <div className="bg-amber-50 border border-amber-300 rounded-xl px-4 py-3 flex items-center gap-2.5 text-xs text-amber-900">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
          <span>
            <strong>Integrity Flag(s):</strong> {Array.from(new Set(valFlags)).join(', ')}. Verify scanned pages on the left and correct misread figures on the right.
          </span>
        </div>
      )}

      {/* Safety Rule Note */}
      <div className="bg-blue-50/70 border border-blue-200 rounded-lg px-3.5 py-2 text-[11px] text-blue-900 flex items-center gap-2">
        <ShieldAlert className="w-4 h-4 text-blue-600 shrink-0" />
        <span>
          <strong>Safety Rule:</strong> Reviewer edits modify only extracted inputs. Policy findings and deterministic calculator rules remain untouched.
        </span>
      </div>

      {/* Two-Pane Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* LEFT PANE: Document Viewer */}
        <div className="lg:col-span-5">
          <DocumentViewer claimId={claim.id} files={claim.files || []} />
        </div>

        {/* RIGHT PANE: Editable Fields + Deterministic Re-run + Sign-off */}
        <div className="lg:col-span-7 space-y-4">
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
              <h2 className="text-sm font-bold text-slate-900">Extracted Claim Fields (Editable)</h2>
              <span className="text-[11px] text-slate-500">Flagged fields highlighted in amber</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Diagnosis */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-slate-700">Diagnosis</label>
                  <ProvenanceBadge source={visionFields.includes('diagnosis') ? 'vision' : 'text'} />
                </div>
                <input
                  type="text"
                  value={form.diagnosis}
                  onChange={(e) => setForm({ ...form, diagnosis: e.target.value })}
                  className="w-full text-xs rounded-lg border border-slate-300 px-3 py-2 bg-white text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              {/* Sum Insured */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-slate-700">Sum Insured (₹)</label>
                  <ProvenanceBadge source={visionFields.includes('sum_insured') ? 'vision' : 'ocr'} />
                </div>
                <input
                  type="number"
                  value={form.sum_insured}
                  onChange={(e) => setForm({ ...form, sum_insured: e.target.value })}
                  className="w-full text-xs rounded-lg border border-slate-300 px-3 py-2 bg-white text-slate-900 tabular-nums focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              {/* Claimed Total */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-slate-700">
                    Claimed Total (₹) {hasTotalMismatch && '⚠️'}
                  </label>
                  <ProvenanceBadge source="ocr" />
                </div>
                <input
                  type="number"
                  value={form.claimed_total}
                  onChange={(e) => setForm({ ...form, claimed_total: e.target.value })}
                  className={`w-full text-xs rounded-lg border px-3 py-2 tabular-nums focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                    hasTotalMismatch
                      ? 'border-amber-400 bg-amber-50 text-amber-950 font-semibold'
                      : 'border-slate-300 bg-white text-slate-900'
                  }`}
                />
              </div>

              {/* Hospital Bill Total */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-slate-700">
                    Hospital Bill Total (₹) {hasTotalMismatch && '⚠️'}
                  </label>
                  <ProvenanceBadge source="ocr" />
                </div>
                <input
                  type="number"
                  value={form.bill_total}
                  onChange={(e) => setForm({ ...form, bill_total: e.target.value })}
                  className={`w-full text-xs rounded-lg border px-3 py-2 tabular-nums focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                    hasTotalMismatch
                      ? 'border-amber-400 bg-amber-50 text-amber-950 font-semibold'
                      : 'border-slate-300 bg-white text-slate-900'
                  }`}
                />
              </div>

              {/* Copay % */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-slate-700">Co-payment (%)</label>
                  <ProvenanceBadge source="text" />
                </div>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={form.copay_pct}
                  onChange={(e) => setForm({ ...form, copay_pct: e.target.value })}
                  className="w-full text-xs rounded-lg border border-slate-300 px-3 py-2 bg-white text-slate-900 tabular-nums"
                />
              </div>

              {/* Room Limit */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-slate-700">Room Limit / Day (₹, 0 = None)</label>
                  <ProvenanceBadge source="text" />
                </div>
                <input
                  type="number"
                  min={0}
                  value={form.room_limit_per_day}
                  onChange={(e) => setForm({ ...form, room_limit_per_day: e.target.value })}
                  className="w-full text-xs rounded-lg border border-slate-300 px-3 py-2 bg-white text-slate-900 tabular-nums"
                />
              </div>
            </div>

            {/* Deterministic Re-run Button */}
            <div className="pt-2">
              <button
                type="button"
                disabled={rerunning}
                onClick={handleRerun}
                className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
              >
                <Zap className="w-4 h-4 text-amber-400" />
                {rerunning ? 'Recalculating...' : 'Re-run Decision Engine (Deterministic · Zero LLM Cost)'}
              </button>
            </div>

            {/* Before & After Comparison Panel */}
            {rerunResult && (
              <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 space-y-2">
                <div className="flex items-center gap-2 text-xs font-bold text-emerald-800">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  Deterministic Engine Recalculated
                </div>
                <div className="grid grid-cols-3 gap-2 items-center text-xs pt-1">
                  <div>
                    <div className="text-[11px] text-slate-500">Previous Outcome</div>
                    <div className="font-bold text-red-700">
                      {rerunResult.previous_decision.toUpperCase()} · {formatINR(rerunResult.previous_payable)}
                    </div>
                  </div>
                  <div className="flex justify-center">
                    <ArrowRight className="w-4 h-4 text-slate-400" />
                  </div>
                  <div className="text-right">
                    <div className="text-[11px] text-slate-500">Updated Outcome</div>
                    <div className="font-bold text-emerald-800">
                      {rerunResult.new_decision.toUpperCase()} · {formatINR(rerunResult.new_payable)}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Reviewer Resolution Card */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-3">
            <h2 className="text-sm font-bold text-slate-900">Reviewer Resolution & Audit Sign-off</h2>

            {msg && (
              <div className="p-2.5 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700">{msg.text}</div>
            )}

            <div className="flex flex-wrap gap-3 text-xs">
              {[
                { val: 'confirm', label: 'Confirm system decision' },
                { val: 'override', label: 'Override with a reason' },
                { val: 'request_docs', label: 'Request more documents' },
              ].map((opt) => (
                <label
                  key={opt.val}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg border cursor-pointer ${
                    actionType === opt.val
                      ? 'bg-blue-50 border-blue-300 text-blue-900 font-semibold'
                      : 'bg-slate-50 border-slate-200 text-slate-700'
                  }`}
                >
                  <input
                    type="radio"
                    name="revAction"
                    value={opt.val}
                    checked={actionType === opt.val}
                    onChange={(e) => setActionType(e.target.value)}
                  />
                  {opt.label}
                </label>
              ))}
            </div>

            {actionType === 'override' && (
              <div className="grid grid-cols-2 gap-3 pt-1">
                <div>
                  <label className="text-[11px] font-semibold text-slate-600">Override Status</label>
                  <select
                    value={overrideStatus}
                    onChange={(e) => setOverrideStatus(e.target.value)}
                    className="w-full mt-1 text-xs border border-slate-300 rounded-lg px-2.5 py-2 bg-white"
                  >
                    <option value="approve">Approve</option>
                    <option value="partial">Partial</option>
                    <option value="reject">Reject</option>
                  </select>
                </div>
                <div>
                  <label className="text-[11px] font-semibold text-slate-600">Override Payable (₹)</label>
                  <input
                    type="number"
                    value={overridePayable}
                    onChange={(e) => setOverridePayable(e.target.value)}
                    className="w-full mt-1 text-xs border border-slate-300 rounded-lg px-2.5 py-2 bg-white tabular-nums"
                  />
                </div>
              </div>
            )}

            <textarea
              rows={2}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Audit rationale (mandatory for overrides)..."
              className="w-full text-xs rounded-lg border border-slate-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />

            <button
              type="button"
              disabled={submitting}
              onClick={handleSubmitReview}
              className="w-full px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-xs cursor-pointer"
            >
              {submitting ? 'Saving Audit Record...' : 'Submit & Finalize Adjudication'}
            </button>
          </div>

          {/* Audit Timeline */}
          <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
            <h3 className="text-xs font-bold uppercase text-slate-500 mb-3">Append-Only Audit Timeline</h3>
            <AuditTimeline entries={claim.audit_timeline || []} createdTime={claim.created_time} />
          </div>
        </div>
      </div>
    </div>
  );
}

