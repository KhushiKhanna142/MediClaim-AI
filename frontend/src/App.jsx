import { useEffect, useState } from 'react';
import {
  ShieldPlus,
  FilePlus2,
  PlayCircle,
  CheckSquare,
  ListChecks,
  FileSearch,
  BookOpen,
  BarChart2,
  Info,
  AlertTriangle,
  Sun,
} from 'lucide-react';
import { api } from './api';
import { SubmitPage } from './pages/SubmitPage';
import { ProcessingPage } from './pages/ProcessingPage';
import { DecisionPage } from './pages/DecisionPage';
import { ReviewQueuePage } from './pages/ReviewQueuePage';
import { ReviewDetailPage } from './pages/ReviewDetailPage';
import { PolicyExplorerPage } from './pages/PolicyExplorerPage';
import { EvaluationPage } from './pages/EvaluationPage';
import { AboutPage } from './pages/AboutPage';

const TABS = [
  { id: 'Submit', label: 'Submit a Claim', icon: FilePlus2, roles: ['Claimant', 'All Tabs'] },
  { id: 'Processing', label: 'Processing', icon: PlayCircle, roles: ['Claimant', 'All Tabs'] },
  { id: 'Decision', label: 'Decision', icon: CheckSquare, roles: ['Claimant', 'Reviewer', 'Demo Viewer', 'All Tabs'] },
  { id: 'Review Queue', label: 'Review Queue', icon: ListChecks, roles: ['Reviewer', 'All Tabs'] },
  { id: 'Review Detail', label: 'Review Detail', icon: FileSearch, roles: ['Reviewer', 'All Tabs'] },
  { id: 'Policy Explorer', label: 'Policy Explorer', icon: BookOpen, roles: ['Reviewer', 'Demo Viewer', 'All Tabs'] },
  { id: 'Evaluation', label: 'Evaluation', icon: BarChart2, roles: ['Demo Viewer', 'All Tabs'] },
  { id: 'About', label: 'About', icon: Info, roles: ['Demo Viewer', 'All Tabs'] },
];

export default function App() {
  const [role, setRole] = useState('All Tabs');
  const [activeTab, setActiveTab] = useState('Decision');
  const [claims, setClaims] = useState([]);
  const [selectedClaimId, setSelectedClaimId] = useState('C005_niva_partial_room');
  const [reviewerName, setReviewerName] = useState('Dr. Sarah Chen, Senior Adjudicator');
  const [demoMode, setDemoMode] = useState(true);
  const [explorerContext, setExplorerContext] = useState({});

  const refreshClaims = () => {
    api
      .listClaims()
      .then((list) => {
        setClaims(list);
        if (list.length > 0 && !list.some((c) => c.id === selectedClaimId)) {
          setSelectedClaimId(list[0].id);
        }
      })
      .catch(() => {});
  };

  useEffect(() => {
    refreshClaims();
  }, [activeTab]);

  const handleRoleChange = (newRole) => {
    setRole(newRole);
    if (newRole === 'Claimant') setActiveTab('Submit');
    else if (newRole === 'Reviewer') setActiveTab('Review Queue');
    else if (newRole === 'Demo Viewer') setActiveTab('Decision');
  };

  const handleNavigate = (tab, ctx = {}) => {
    if (tab === 'Policy Explorer' && (ctx.clauseId || ctx.policyId)) {
      setExplorerContext(ctx);
    }
    if (!TABS.find((t) => t.id === tab)?.roles.includes(role)) {
      setRole('All Tabs');
    }
    setActiveTab(tab);
  };

  const visibleTabs = TABS.filter((t) => t.roles.includes(role));
  const reviewCount = claims.filter((c) => c.status === 'needs_review').length;

  return (
    <div className="min-h-screen flex flex-col bg-slate-100 text-slate-900">
      {/* Top Header Bar */}
      <header className="h-14 bg-white border-b border-slate-200 px-4 flex items-center justify-between gap-4 sticky top-0 z-30">
        {/* Brand */}
        <div className="flex items-center gap-2.5 shrink-0">
          <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white shadow-xs">
            <ShieldPlus className="w-5 h-5" />
          </div>
          <div>
            <div className="text-sm font-extrabold text-slate-900 leading-tight">MediClaim-AI</div>
            <div className="text-[11px] text-slate-500 hidden sm:block">
              AI-powered Health Insurance Claim Adjudication
            </div>
          </div>
        </div>

        {/* Synthetic Data Warning Pill */}
        <div className="hidden md:flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-amber-50 border border-amber-200 text-xs font-medium text-amber-900">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
          <span>Demo System — Uses synthetic data only. Decisions are not real and not for actual claims.</span>
        </div>

        {/* Role Selector */}
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs font-medium text-slate-500 hidden sm:inline">Role:</span>
          <select
            value={role}
            onChange={(e) => handleRoleChange(e.target.value)}
            className="text-xs font-semibold bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="All Tabs">All Tabs (Full View)</option>
            <option value="Demo Viewer">Demo Viewer</option>
            <option value="Reviewer">Reviewer</option>
            <option value="Claimant">Claimant</option>
          </select>
        </div>
      </header>

      {/* Body: Sidebar + Main Canvas */}
      <div className="flex-1 flex flex-col md:flex-row">
        {/* Left Light-Theme Sidebar */}
        <aside className="w-full md:w-56 bg-white border-b md:border-b-0 md:border-r border-slate-200 flex flex-col justify-between shrink-0">
          <nav className="p-3 space-y-1 flex md:flex-col overflow-x-auto md:overflow-x-visible">
            {visibleTabs.map((t) => {
              const Icon = t.icon;
              const active = activeTab === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setActiveTab(t.id)}
                  className={`flex items-center justify-between gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition-colors whitespace-nowrap cursor-pointer ${
                    active
                      ? 'bg-blue-600 text-white shadow-xs'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`}
                >
                  <span className="flex items-center gap-2.5">
                    <Icon className={`w-4 h-4 ${active ? 'text-white' : 'text-slate-400'}`} />
                    {t.label}
                  </span>
                  {t.id === 'Review Queue' && reviewCount > 0 && (
                    <span
                      className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold tabular-nums ${
                        active ? 'bg-white/20 text-white' : 'bg-amber-100 text-amber-800'
                      }`}
                    >
                      {reviewCount}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>

          {/* Sidebar Footer */}
          <div className="hidden md:block p-3 border-t border-slate-100 space-y-2">
            <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5">
              <div className="text-[10px] font-semibold uppercase text-slate-400">Signed in as</div>
              <div className="text-xs font-bold text-slate-800 truncate">{reviewerName}</div>
            </div>
            <div className="flex items-center justify-between text-[11px] text-slate-400 px-1">
              <span>v1.0.0</span>
              <span className="inline-flex items-center gap-1 text-slate-500 font-medium">
                <Sun className="w-3 h-3 text-amber-500" />
                Light Theme
              </span>
            </div>
          </div>
        </aside>

        {/* Main Workspace */}
        <main className="flex-1 p-4 sm:p-6 overflow-y-auto flex flex-col justify-between">
          <div>
            {activeTab === 'Submit' && (
              <SubmitPage
                onSubmitted={(newId) => {
                  setSelectedClaimId(newId);
                  refreshClaims();
                  setActiveTab('Processing');
                }}
              />
            )}
            {activeTab === 'Processing' && (
              <ProcessingPage claimId={selectedClaimId} onNavigate={handleNavigate} />
            )}
            {activeTab === 'Decision' && (
              <DecisionPage
                claimId={selectedClaimId}
                claims={claims}
                onSelectClaim={setSelectedClaimId}
                onNavigate={handleNavigate}
              />
            )}
            {activeTab === 'Review Queue' && (
              <ReviewQueuePage
                reviewerName={reviewerName}
                onSelectClaim={setSelectedClaimId}
                onNavigate={handleNavigate}
              />
            )}
            {activeTab === 'Review Detail' && (
              <ReviewDetailPage
                claimId={selectedClaimId}
                claims={claims}
                reviewerName={reviewerName}
                onSelectClaim={setSelectedClaimId}
                onNavigate={handleNavigate}
              />
            )}
            {activeTab === 'Policy Explorer' && (
              <PolicyExplorerPage initialContext={explorerContext} />
            )}
            {activeTab === 'Evaluation' && (
              <EvaluationPage
                onSelectClaim={setSelectedClaimId}
                onNavigate={handleNavigate}
              />
            )}
            {activeTab === 'About' && (
              <AboutPage
                reviewerName={reviewerName}
                onChangeReviewer={setReviewerName}
                demoMode={demoMode}
                onToggleDemoMode={setDemoMode}
              />
            )}
          </div>

          {/* Mandatory Synthetic Data Footer on Every Page */}
          <footer className="mt-8 pt-4 border-t border-slate-200 text-center text-[11px] text-slate-500">
            <strong>Synthetic Data Notice:</strong> All claims, patient identities, hospital bills, and policy schedules in this application are synthetically generated for benchmark evaluation. No real Protected Health Information (PHI) is contained.
          </footer>
        </main>
      </div>
    </div>
  );
}

