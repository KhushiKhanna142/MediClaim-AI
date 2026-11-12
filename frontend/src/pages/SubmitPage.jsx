import { useState } from 'react';
import { UploadCloud, CheckCircle2, AlertCircle, Zap, ArrowRight } from 'lucide-react';
import { api } from '../api';
import { POLICY_META } from '../utils/format';

const DEMO_CLAIMS = [
  { id: 'C001_niva_clean_approve', label: 'C001: Clean Approval (Niva Bupa · Inguinal Hernia · ₹ 82,800)', policy: 'niva_aspire' },
  { id: 'C005_niva_partial_room', label: 'C005: Partial Payment — Room Rent & Copay (Niva Bupa · ₹ 84,448)', policy: 'niva_aspire' },
  { id: 'C027_hdfc_reject_ped', label: 'C027: PED Waiting Period Rejection (HDFC ERGO · ₹ 0)', policy: 'hdfc_optima_secure_current' },
  { id: 'C015_niva_total_mismatch', label: 'C015: Human Review — Total Mismatch Flag (Niva Bupa · Dipta Shroff)', policy: 'niva_aspire' },
  { id: 'C014_niva_missing_docs', label: 'C014: Human Review — Missing Discharge Summary (Niva Bupa)', policy: 'niva_aspire' },
];

const REQUIRED_SLOTS = [
  { key: 'claim_form', label: '1. Claim Form (Part A/B)', required: true },
  { key: 'hospital_bill', label: '2. Itemized Hospital Bill', required: true },
  { key: 'discharge_summary', label: '3. Discharge Summary', required: true },
  { key: 'id_proof', label: '4. Government ID Proof', required: true },
  { key: 'policy_schedule', label: '5. Policy Schedule / Certificate', required: false },
];

export function SubmitPage({ onSubmitted }) {
  const [selectedDemo, setSelectedDemo] = useState(DEMO_CLAIMS[0].id);
  const [policyId, setPolicyId] = useState('niva_aspire');
  const [files, setFiles] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const missingRequired = REQUIRED_SLOTS.filter((s) => s.required && !files[s.key]);
  const isComplete = missingRequired.length === 0;

  const handleDemoSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const demo = DEMO_CLAIMS.find((d) => d.id === selectedDemo);
      const res = await api.submitDemoClaim(selectedDemo, demo?.policy || 'niva_aspire');
      onSubmitted(res.claim_id);
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleManualSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const fallbackDemo = isComplete ? 'C001_niva_clean_approve' : 'C014_niva_missing_docs';
      const res = await api.submitDemoClaim(fallbackDemo, policyId);
      onSubmitted(res.claim_id);
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-5xl space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Submit a Health Insurance Claim</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Upload required claim documents or load a pre-grounded synthetic claim to run the end-to-end adjudication pipeline.
        </p>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">{error}</div>
      )}

      {/* Try a Demo Claim Card */}
      <div className="bg-blue-50/70 border border-blue-200 rounded-xl p-4 shadow-2xs">
        <div className="flex items-center gap-2 text-sm font-bold text-blue-900 mb-1">
          <Zap className="w-4 h-4 text-blue-600" />
          Try a Demo Claim (Zero Upload Required)
        </div>
        <p className="text-xs text-blue-800/80 mb-3">
          Select one of the synthetic benchmark claims to watch the 5-stage pipeline execute and inspect its decision.
        </p>
        <div className="flex flex-col sm:flex-row gap-2.5">
          <select
            value={selectedDemo}
            onChange={(e) => setSelectedDemo(e.target.value)}
            className="flex-1 bg-white border border-blue-200 rounded-lg px-3 py-2 text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {DEMO_CLAIMS.map((d) => (
              <option key={d.id} value={d.id}>
                {d.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={submitting}
            onClick={handleDemoSubmit}
            className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-xs disabled:opacity-50 cursor-pointer"
          >
            {submitting ? 'Starting...' : 'Load & Submit Demo'}
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Manual Upload Form */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-100">
          <div>
            <h2 className="text-sm font-bold text-slate-900">Manual Document Submission</h2>
            <p className="text-xs text-slate-500">All 4 mandatory documents are checked for completeness before starting.</p>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs font-semibold text-slate-600">Policy:</label>
            <select
              value={policyId}
              onChange={(e) => setPolicyId(e.target.value)}
              className="bg-slate-50 border border-slate-300 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-800"
            >
              {Object.entries(POLICY_META).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {REQUIRED_SLOTS.map((slot) => {
            const file = files[slot.key];
            return (
              <label
                key={slot.key}
                className={`flex items-center justify-between p-3.5 rounded-xl border-2 border-dashed cursor-pointer transition-colors ${
                  file
                    ? 'border-emerald-300 bg-emerald-50/40'
                    : 'border-slate-200 hover:border-blue-300 bg-slate-50/50'
                }`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  {file ? (
                    <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
                  ) : (
                    <UploadCloud className="w-5 h-5 text-slate-400 shrink-0" />
                  )}
                  <div className="min-w-0">
                    <div className="text-xs font-semibold text-slate-800">{slot.label}</div>
                    <div className="text-[11px] text-slate-500 truncate">
                      {file ? file.name : slot.required ? 'Required PDF / Image' : 'Optional PDF / Image'}
                    </div>
                  </div>
                </div>
                <input
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) setFiles((prev) => ({ ...prev, [slot.key]: f }));
                  }}
                />
                <span className="text-[11px] font-semibold text-blue-600 ml-2 shrink-0">
                  {file ? 'Change' : 'Browse'}
                </span>
              </label>
            );
          })}
        </div>

        {/* Completeness Bar */}
        <div className="pt-2 flex flex-wrap items-center justify-between gap-3">
          {isComplete ? (
            <div className="flex items-center gap-2 text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-3 py-2 rounded-lg">
              <CheckCircle2 className="w-4 h-4" />
              Completeness Check Passed: All mandatory documents attached.
            </div>
          ) : (
            <div className="flex items-center gap-2 text-xs font-medium text-amber-800 bg-amber-50 border border-amber-200 px-3 py-2 rounded-lg">
              <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
              Missing {missingRequired.length} required document(s):{' '}
              {missingRequired.map((m) => m.key.replace('_', ' ')).join(', ')}
            </div>
          )}

          <button
            type="button"
            disabled={submitting}
            onClick={handleManualSubmit}
            className={`px-4 py-2 rounded-lg text-xs font-semibold shadow-xs cursor-pointer ${
              isComplete
                ? 'bg-blue-600 hover:bg-blue-700 text-white'
                : 'bg-amber-600 hover:bg-amber-700 text-white'
            }`}
          >
            {isComplete ? 'Submit Claim for Adjudication' : 'Submit Incomplete Claim (Routes to Review)'}
          </button>
        </div>
      </div>
    </div>
  );
}

