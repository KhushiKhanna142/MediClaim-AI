import { useEffect, useState } from 'react';
import { Cpu, AlertTriangle, Database, Settings, ArrowDown } from 'lucide-react';
import { api } from '../api';

export function AboutPage({ reviewerName, onChangeReviewer, demoMode, onToggleDemoMode }) {
  const [info, setInfo] = useState({ versions: {}, gemini_configured: false, model: 'gemini-2.5-flash' });

  useEffect(() => {
    api.getAboutInfo().then(setInfo).catch(() => {});
  }, []);

  const archSteps = [
    { title: '1. Document Ingestion & OCR', desc: 'RapidOCR / PyMuPDF table parsing + Pydantic schema extraction' },
    { title: '2. Deterministic Validation', desc: 'Completeness, date ordering & bill arithmetic checks (No LLM)' },
    { title: '3. Hybrid Clause RAG', desc: 'BM25 + Qdrant BGE-Small dense search + RRF + Cross-Encoder Rerank' },
    { title: '4. Deterministic Decision Engine', desc: 'Exact rupee math: Non-payables, Room cap, Proportionate, Copay, SI Cap' },
    { title: '5. Verifier & Human-in-the-Loop', desc: 'Adversarial sanity check + LangGraph interrupt() for human review' },
  ];

  return (
    <div className="max-w-5xl space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-900">About MediClaim-AI & Settings</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Portfolio engineering project — architecture, runtime diagnostics, limitations, and demonstration settings.
        </p>
      </div>

      {/* Honest Scope Card */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
        <h2 className="text-sm font-bold text-slate-900 mb-1.5">Portfolio Project — Not a Live Insurer Tool</h2>
        <p className="text-xs text-slate-600 leading-relaxed">
          MediClaim-AI demonstrates auditable, zero-leakage health insurance claim adjudication. Rather than letting an LLM perform arithmetic or guess coverage, it isolates policy reading (RAG) from deterministic rupee calculations (<code>src/tools/calculator.py</code>) and routes any uncertain or mismatched claim to a human reviewer with an append-only audit trail.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Architecture Flow */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
          <div className="flex items-center gap-2 text-sm font-bold text-slate-900 mb-4">
            <Cpu className="w-4 h-4 text-blue-600" />
            Pipeline Architecture
          </div>
          <div className="space-y-2">
            {archSteps.map((s, idx) => (
              <div key={s.title}>
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                  <div className="text-xs font-bold text-slate-900">{s.title}</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">{s.desc}</div>
                </div>
                {idx < archSteps.length - 1 && (
                  <div className="flex justify-center py-0.5">
                    <ArrowDown className="w-3.5 h-3.5 text-slate-400" />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Limitations & Dataset */}
        <div className="space-y-4">
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
            <div className="flex items-center gap-2 text-sm font-bold text-slate-900 mb-3">
              <AlertTriangle className="w-4 h-4 text-amber-600" />
              Known Limitations
            </div>
            <ul className="space-y-2 text-xs text-slate-600 list-disc pl-4">
              <li>All 30 claims, patient identities, and bills are synthetically generated.</li>
              <li>Scanned schedules can lose digits under low DPI, so those claims route to human review.</li>
              <li>Only 5 major Indian policy wordings have full rulesets indexed.</li>
              <li>Policy benefit tables are flattened to text during ingestion.</li>
              <li>The policy reader was tuned on the same 30 synthetic claims it is scored on.</li>
            </ul>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
            <div className="flex items-center gap-2 text-sm font-bold text-slate-900 mb-2">
              <Database className="w-4 h-4 text-blue-600" />
              Synthetic Dataset Generation
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              Generated with <code>Faker</code> and <code>ReportLab</code> across 11 categories: Clean Approvals (6), Continuity Credits (2), Room Rent Caps (4), Non-Payable Items (2), Sum Insured Caps (2), Waiting Period Rejections (8), Multi-Hop (2), and Deliberate Integrity Failures (4).
            </p>
          </div>
        </div>
      </div>

      {/* Settings & Runtime Versions */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-4">
        <div className="flex items-center gap-2 text-sm font-bold text-slate-900 border-b border-slate-100 pb-2.5">
          <Settings className="w-4 h-4 text-blue-600" />
          Settings & Runtime Environment
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="text-[11px] font-semibold uppercase text-slate-500">Reviewer Name</label>
            <input
              type="text"
              value={reviewerName}
              onChange={(e) => onChangeReviewer(e.target.value)}
              className="w-full mt-1 text-xs border border-slate-300 rounded-lg px-3 py-2"
            />
          </div>

          <div>
            <label className="text-[11px] font-semibold uppercase text-slate-500">Language Model</label>
            <div className="mt-1 text-xs font-mono bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-800">
              {info.model}
            </div>
          </div>

          <div>
            <label className="text-[11px] font-semibold uppercase text-slate-500">Demo Mode (Zero API Quota)</label>
            <div className="mt-1 flex items-center gap-2">
              <button
                type="button"
                onClick={() => onToggleDemoMode(!demoMode)}
                className={`px-3 py-2 rounded-lg text-xs font-semibold border cursor-pointer ${
                  demoMode
                    ? 'bg-emerald-50 border-emerald-300 text-emerald-800'
                    : 'bg-slate-100 border-slate-300 text-slate-700'
                }`}
              >
                {demoMode ? '✓ Active (Replaying Cached Runs)' : 'Live API Mode'}
              </button>
            </div>
          </div>
        </div>

        <div>
          <div className="text-[11px] font-semibold uppercase text-slate-500 mb-2">
            Installed Environment Versions (Live)
          </div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(info.versions || {}).map(([k, v]) => (
              <span
                key={k}
                className="px-2.5 py-1 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-700"
              >
                <strong>{k}:</strong> <span className="font-mono text-slate-500">{v}</span>
              </span>
            ))}
            <span className="px-2.5 py-1 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-700">
              <strong>API Key:</strong>{' '}
              <span className="font-mono text-slate-500">
                {info.gemini_configured ? 'Configured (hidden)' : 'Not set (Demo Mode)'}
              </span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

