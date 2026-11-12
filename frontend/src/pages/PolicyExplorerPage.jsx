import { useEffect, useState } from 'react';
import { Search, FolderTree, Scale, ChevronDown, ChevronRight } from 'lucide-react';
import { api } from '../api';
import { POLICY_META, getPolicyMeta } from '../utils/format';

const COMPARE_TOPICS = {
  'Pre-Existing Disease (PED) Waiting Period': 'pre-existing disease waiting period PED exclusion',
  'Initial 30-Day Waiting Period': 'initial waiting period thirty 30 days hospitalisation',
  'Room Rent & Proportionate Capping': 'room rent capping limit standard single room proportionate deduction',
  'Non-Payable & Consumables Expenses': 'non medical expenses non-payable items consumables gloves thermometer',
  'AYUSH Alternative Medicine Coverage': 'ayush ayurveda homeopathy unani hospital treatment coverage',
  'Modern Treatment & Robotic Surgery': 'modern treatment methods robotic surgery stem cell therapy',
};

export function PolicyExplorerPage({ initialContext = {} }) {
  const [subTab, setSubTab] = useState(initialContext.clauseId ? 'browse' : 'search');
  const [query, setQuery] = useState(initialContext.clauseId || 'pre-existing disease waiting period');
  const [searchPolicy, setSearchPolicy] = useState(initialContext.policyId || 'all');
  const [mode, setMode] = useState('hybrid');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);

  // Browse state
  const [browsePolicy, setBrowsePolicy] = useState(initialContext.policyId || 'niva_aspire');
  const [clauses, setClauses] = useState([]);
  const [expandedSections, setExpandedSections] = useState({});
  const highlightClause = initialContext.clauseId || null;

  // Compare state
  const [topic, setTopic] = useState(Object.keys(COMPARE_TOPICS)[0]);
  const [policyA, setPolicyA] = useState('niva_aspire');
  const [policyB, setPolicyB] = useState('hdfc_optima_secure_current');
  const [compResA, setCompResA] = useState(null);
  const [compResB, setCompResB] = useState(null);

  const runSearch = async (q = query, pol = searchPolicy, m = mode) => {
    if (!q.trim()) return;
    setSearching(true);
    try {
      const res = await api.searchPolicies(q, pol, m, 5);
      setResults(res);
    } finally {
      setSearching(false);
    }
  };

  useEffect(() => {
    if (subTab === 'search') {
      runSearch();
    }
  }, [subTab, mode, searchPolicy]);

  useEffect(() => {
    if (subTab === 'browse') {
      api.getPolicyClauses(browsePolicy).then((list) => {
        setClauses(list);
        if (highlightClause) {
          const match = list.find((c) => c.clause_id === highlightClause);
          if (match) {
            setExpandedSections((prev) => ({
              ...prev,
              [match.section || 'General Terms & Preamble']: true,
            }));
          }
        }
      });
    }
  }, [subTab, browsePolicy, highlightClause]);

  useEffect(() => {
    if (subTab === 'compare') {
      const q = COMPARE_TOPICS[topic];
      Promise.all([
        api.searchPolicies(q, policyA, 'hybrid', 1),
        api.searchPolicies(q, policyB, 'hybrid', 1),
      ]).then(([a, b]) => {
        setCompResA(a[0] || null);
        setCompResB(b[0] || null);
      });
    }
  }, [subTab, topic, policyA, policyB]);

  // Group clauses by section
  const grouped = clauses.reduce((acc, c) => {
    const sec = c.section || 'General Terms & Preamble';
    if (!acc[sec]) acc[sec] = [];
    acc[sec].push(c);
    return acc;
  }, {});

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Policy & Clause Explorer</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Test the multi-stage hybrid RAG retrieval layer, walk hierarchical clause trees, or compare insurer terms side by side.
        </p>
      </div>

      {/* Sub-tabs */}
      <div className="inline-flex p-1 bg-slate-200/70 rounded-xl gap-1">
        {[
          { id: 'search', label: 'Search Mode', icon: Search },
          { id: 'browse', label: 'Browse Clause Tree', icon: FolderTree },
          { id: 'compare', label: 'Compare Policies', icon: Scale },
        ].map((t) => {
          const Icon = t.icon;
          const active = subTab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setSubTab(t.id)}
              className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                active ? 'bg-white text-blue-700 shadow-2xs' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* SEARCH MODE */}
      {subTab === 'search' && (
        <div className="space-y-4">
          <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs flex flex-col md:flex-row gap-3">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && runSearch()}
              placeholder="Search clinical terms, waiting periods, room rent..."
              className="flex-1 text-xs border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <select
              value={searchPolicy}
              onChange={(e) => setSearchPolicy(e.target.value)}
              className="text-xs border border-slate-300 rounded-lg px-3 py-2 bg-slate-50"
            >
              <option value="all">All Policies</option>
              {Object.entries(POLICY_META).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label}
                </option>
              ))}
            </select>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              className="text-xs border border-slate-300 rounded-lg px-3 py-2 bg-slate-50"
            >
              <option value="hybrid">Hybrid (BM25 + Dense RRF)</option>
              <option value="dense">Dense (BGE-Small Embeddings)</option>
              <option value="bm25">BM25 (Lexical Search)</option>
            </select>
            <button
              type="button"
              onClick={() => runSearch()}
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold cursor-pointer"
            >
              {searching ? 'Searching...' : 'Search'}
            </button>
          </div>

          <div className="space-y-3">
            {results.map((r, i) => (
              <div
                key={`${r.policy_id}-${r.clause_id}-${i}`}
                className="bg-white border border-slate-200 border-l-4 border-l-blue-600 rounded-xl p-4 shadow-2xs"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-blue-700">
                      #{i + 1} · Clause {r.clause_id}
                    </span>
                    {r.section && <span className="text-xs text-slate-500">{r.section}</span>}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-blue-50 text-blue-700 border border-blue-200 tabular-nums">
                      Score: {Number(r.score).toFixed(4)}
                    </span>
                    <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700">
                      {getPolicyMeta(r.policy_id).label}
                    </span>
                  </div>
                </div>
                <p className="text-xs text-slate-700 leading-relaxed">"{r.text}"</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* BROWSE MODE */}
      {subTab === 'browse' && (
        <div className="space-y-4">
          <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-600">Select Policy:</span>
              <select
                value={browsePolicy}
                onChange={(e) => setBrowsePolicy(e.target.value)}
                className="text-xs border border-slate-300 rounded-lg px-3 py-1.5 bg-slate-50 font-medium"
              >
                {Object.entries(POLICY_META).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v.label}
                  </option>
                ))}
              </select>
            </div>
            <span className="text-xs text-slate-500">{clauses.length} indexed clauses</span>
          </div>

          <div className="space-y-2.5">
            {Object.entries(grouped).map(([sec, list]) => {
              const isOpen = !!expandedSections[sec];
              return (
                <div key={sec} className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
                  <button
                    type="button"
                    onClick={() => setExpandedSections((p) => ({ ...p, [sec]: !p[sec] }))}
                    className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-slate-50"
                  >
                    <span className="flex items-center gap-2 text-xs font-bold text-slate-800">
                      {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                      {sec}
                    </span>
                    <span className="text-[11px] text-slate-500">{list.length} clauses</span>
                  </button>
                  {isOpen && (
                    <div className="p-3 pt-0 space-y-2 border-t border-slate-100 bg-slate-50/40">
                      {list.map((c) => {
                        const active = c.clause_id === highlightClause;
                        return (
                          <div
                            key={c.clause_id}
                            className={`p-3 rounded-lg border-l-4 ${
                              active
                                ? 'bg-amber-50 border-amber-400 border border-l-4'
                                : 'bg-white border border-slate-200 border-l-blue-500'
                            }`}
                          >
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-xs font-bold text-blue-700">Clause {c.clause_id}</span>
                              {active && (
                                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-200 text-amber-900">
                                  Active Citation Target
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-slate-700 leading-relaxed">{c.text}</p>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* COMPARE MODE */}
      {subTab === 'compare' && (
        <div className="space-y-4">
          <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="text-[11px] font-semibold text-slate-500 uppercase">Adjudication Topic</label>
              <select
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                className="w-full mt-1 text-xs border border-slate-300 rounded-lg px-3 py-2 bg-slate-50 font-medium"
              >
                {Object.keys(COMPARE_TOPICS).map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-[11px] font-semibold text-slate-500 uppercase">Policy A</label>
              <select
                value={policyA}
                onChange={(e) => setPolicyA(e.target.value)}
                className="w-full mt-1 text-xs border border-slate-300 rounded-lg px-3 py-2 bg-slate-50 font-medium"
              >
                {Object.entries(POLICY_META).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-[11px] font-semibold text-slate-500 uppercase">Policy B</label>
              <select
                value={policyB}
                onChange={(e) => setPolicyB(e.target.value)}
                className="w-full mt-1 text-xs border border-slate-300 rounded-lg px-3 py-2 bg-slate-50 font-medium"
              >
                {Object.entries(POLICY_META).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[
              { label: getPolicyMeta(policyA).label, res: compResA },
              { label: getPolicyMeta(policyB).label, res: compResB },
            ].map((side, idx) => (
              <div key={idx} className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs space-y-2">
                <div className="text-sm font-bold text-slate-900 border-b border-slate-100 pb-2">{side.label}</div>
                {side.res ? (
                  <>
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold text-blue-700">Clause {side.res.clause_id}</span>
                      <span className="text-slate-500">{side.res.section}</span>
                    </div>
                    <p className="text-xs text-slate-700 leading-relaxed bg-slate-50 p-3 rounded-lg border border-slate-100">
                      "{side.res.text}"
                    </p>
                  </>
                ) : (
                  <p className="text-xs text-slate-500">No matching clause found.</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

