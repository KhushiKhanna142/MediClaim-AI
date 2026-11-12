import { useEffect, useState } from 'react';
import { CheckCircle2, Clock, AlertTriangle, Loader2, ArrowRight, RotateCcw } from 'lucide-react';
import { api } from '../api';
import { formatINR, getPolicyMeta } from '../utils/format';

const STAGES = [
  { key: 'read_documents', label: 'Read Documents', desc: 'RapidOCR & PyMuPDF' },
  { key: 'extract_fields', label: 'Extract Fields', desc: 'Structured Schema' },
  { key: 'validate', label: 'Validate', desc: 'Completeness & Totals' },
  { key: 'read_policy', label: 'Read Policy', desc: 'Hybrid RAG + Rerank' },
  { key: 'decide', label: 'Decide', desc: 'Deterministic Engine' },
];

export function ProcessingPage({ claimId, onNavigate }) {
  const [claim, setClaim] = useState(null);
  const [statusData, setStatusData] = useState(null);
  const [animStep, setAnimStep] = useState(5);

  useEffect(() => {
    if (!claimId) return;
    let cancelled = false;
    setAnimStep(1);

    Promise.all([api.getClaim(claimId), api.getClaimStatus(claimId)]).then(([c, st]) => {
      if (cancelled) return;
      setClaim(c);
      setStatusData(st);
    });

    // Smooth visual progression for demo clarity
    const timer = setInterval(() => {
      setAnimStep((prev) => {
        if (prev >= 5) {
          clearInterval(timer);
          return 5;
        }
        return prev + 1;
      });
    }, 350);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [claimId]);

  if (!claim) {
    return (
      <div className="p-8 text-center text-sm text-slate-500">
        Loading pipeline status...
      </div>
    );
  }

  const meta = getPolicyMeta(claim.policy_id);
  const stages = statusData?.stage_states || claim.stage_states || {};
  const timings = statusData?.timings || claim.timings || {};
  const isReview = claim.status === 'needs_review' || claim.decision?.decision === 'needs_review';
  const totalSec = Object.values(timings).reduce((acc, v) => acc + Number(v || 0), 0);

  return (
    <div className="max-w-5xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900">
            Pipeline Execution — <span className="text-blue-700 font-mono text-base">{claim.id}</span>
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Live stage progression, OCR timings, validation checks, and policy adjudication.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setAnimStep(1)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-slate-300 text-xs font-semibold text-slate-700 hover:bg-slate-50"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          Replay Progress
        </button>
      </div>

      {/* Metadata Strip */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 grid grid-cols-1 sm:grid-cols-3 gap-4 shadow-xs">
        <div>
          <div className="text-[11px] font-semibold uppercase text-slate-400">Policy</div>
          <div className="text-sm font-bold text-slate-900">{meta.label}</div>
        </div>
        <div>
          <div className="text-[11px] font-semibold uppercase text-slate-400">Patient</div>
          <div className="text-sm font-bold text-slate-900">{claim.patient_name || 'Demo Patient'}</div>
        </div>
        <div>
          <div className="text-[11px] font-semibold uppercase text-slate-400">Billed Amount</div>
          <div className="text-sm font-bold text-slate-900 tabular-nums">{formatINR(claim.billed_amount)}</div>
        </div>
      </div>

      {/* 5-Stage Progress Strip */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-xs">
        <div className="grid grid-cols-1 sm:grid-cols-5 gap-4">
          {STAGES.map((st, idx) => {
            const stepNum = idx + 1;
            const rawState = stages[st.key] || 'done';
            let displayState = 'pending';
            if (stepNum < animStep) displayState = rawState === 'failed' ? 'failed' : 'done';
            else if (stepNum === animStep) displayState = animStep < 5 ? 'running' : rawState;

            const elapsed = Number(timings[st.key] || 0).toFixed(1);

            return (
              <div
                key={st.key}
                className={`p-3.5 rounded-xl border text-center transition-all ${
                  displayState === 'done'
                    ? 'bg-emerald-50/50 border-emerald-200'
                    : displayState === 'running'
                    ? 'bg-blue-50 border-blue-300 ring-2 ring-blue-100'
                    : displayState === 'failed'
                    ? 'bg-amber-50 border-amber-300'
                    : 'bg-slate-50 border-slate-200'
                }`}
              >
                <div className="flex justify-center mb-2">
                  {displayState === 'done' && <CheckCircle2 className="w-6 h-6 text-emerald-600" />}
                  {displayState === 'running' && <Loader2 className="w-6 h-6 text-blue-600 animate-spin" />}
                  {displayState === 'failed' && <AlertTriangle className="w-6 h-6 text-amber-600" />}
                  {displayState === 'pending' && <Clock className="w-6 h-6 text-slate-400" />}
                </div>
                <div className="text-xs font-bold text-slate-900">{st.label}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">{st.desc}</div>
                <div className="text-[11px] font-mono text-slate-600 mt-2 tabular-nums">
                  {displayState === 'pending' ? '—' : `${elapsed}s`}
                </div>
              </div>
            );
          })}
        </div>

        {/* Completion Banner */}
        {animStep >= 5 && (
          <div className="mt-6 pt-5 border-t border-slate-100">
            {isReview ? (
              <div className="bg-amber-50 border border-amber-300 rounded-xl p-4 flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                  <div>
                    <div className="text-sm font-bold text-amber-900">Sent to Human Review Queue</div>
                    <p className="text-xs text-amber-800 mt-0.5">
                      Validation raised flags:{' '}
                      <code>
                        {(claim.decision?.escalation_reasons || claim.decision?.flags || ['needs_review']).join(', ')}
                      </code>
                      . The system paused before policy reading to prevent an unsafe decision.
                    </p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => onNavigate('Review Detail')}
                    className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-xs font-semibold"
                  >
                    Open in Review Detail
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => onNavigate('Decision')}
                    className="px-3.5 py-2 rounded-lg bg-white border border-amber-300 text-amber-900 text-xs font-semibold hover:bg-amber-100/50"
                  >
                    View Decision
                  </button>
                </div>
              </div>
            ) : (
              <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-start gap-3">
                  <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                  <div>
                    <div className="text-sm font-bold text-emerald-900">
                      Adjudication Completed in {totalSec.toFixed(1)}s
                    </div>
                    <p className="text-xs text-emerald-800 mt-0.5">
                      Outcome: <strong>{(claim.decision?.decision || claim.status).toUpperCase()}</strong> &nbsp;·&nbsp; Payable:{' '}
                      <strong className="tabular-nums">{formatINR(claim.payable_amount)}</strong>
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => onNavigate('Decision')}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-xs"
                >
                  Open Decision & Evidence
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

