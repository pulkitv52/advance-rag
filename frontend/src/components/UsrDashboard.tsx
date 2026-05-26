import React, { useEffect, useRef, useState } from 'react'
import { 
  Users, 
  AlertTriangle, 
  TrendingUp, 
  Map, 
  Ghost, 
  Copy, 
  Settings, 
  ShieldCheck, 
  Loader2, 
  ArrowRight,
  UserCheck2,
  Download
} from 'lucide-react'
import axios from 'axios'
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer,
} from 'recharts'
import { Card } from "./ui/card"
import { Button } from "./ui/button"
import { Badge } from "./ui/badge"
import { ScrollArea } from "./ui/scroll-area"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "./ui/dialog"

interface UsrDashboardProps {
  API: string
}

interface UsrStats {
  total_citizens: number;
  avg_vulnerability: number;
  critical_count: number;
  high_risk_count: number;
  last_updated: string | null;
  registry_total?: number;
  coverage_pct?: number;
  female_count: number
  critical_tier_count: number
}

interface UsrCitizen {
  name: string
  gender: string
  dob: string
  score: number
  tier: string
  district: string
  block: string
  gp: string
  schemes: string[]
  age?: number
}

interface UsrFraudFlag {
  name?: string
  name1?: string
  name2?: string
  uid?: string
  uid1?: string
  uid2?: string
  dob?: string
  confidence: number
  rule: string
  scheme?: string
  shared_gp?: string
  name_similarity?: number
  gp_name?: string
  concentration_ratio?: number
  label?: string
  type?: string
  description?: string
}

interface UsrDataQuality {
  total_issues: number
  total_citizens?: number
  integrity_index?: number
  health: string
  checks: Record<string, number>
}

interface UsrDistrict {
  district: string
  citizen_count: number
  avg_risk_score: number
  high_risk_count: number
}

interface UsrAuditCase {
  name: string
  uid: string
  dob: string
  gender: string
  score: number
  district: string
  block: string
  gp: string
  flags: number
  flag_notes: string[]
}

interface UsrRulesEF {
  rule_e: any[]
  rule_f: any[]
}



export const UsrDashboard: React.FC<UsrDashboardProps> = ({ API }) => {
  const INTEL_PAGE_SIZE = 500
  const [usrStats, setUsrStats] = useState<UsrStats | null>(null)
  const [usrTopRisk, setUsrTopRisk] = useState<Record<string, UsrCitizen[]>>({
    all: [],
    elderly: [],
    children: [],
    workers: []
  })
  const [usrHeatmap, setUsrHeatmap] = useState<UsrDistrict[]>([])
  const [usrLoading, setUsrLoading] = useState(false)
  const [usrGhosts, setUsrGhosts] = useState<UsrFraudFlag[]>([])
  const [usrDuplicates, setUsrDuplicates] = useState<UsrFraudFlag[]>([])
  const [usrIntelligenceFeed, setUsrIntelligenceFeed] = useState<any[]>([])
  const [usrIntelligenceTotal, setUsrIntelligenceTotal] = useState(0)
  const [usrLoadingMoreIntel, setUsrLoadingMoreIntel] = useState(false)
  const [usrAnomalies, setUsrAnomalies] = useState<UsrFraudFlag[]>([])
  const [usrDataQuality, setUsrDataQuality] = useState<UsrDataQuality | null>(null)
  const [usrAuditQueue, setUsrAuditQueue] = useState<UsrAuditCase[]>([])
  const [usrRulesEF, setUsrRulesEF] = useState<UsrRulesEF>({ rule_e: [], rule_f: [] })
  
  // New Functional States for Field Portal
  const [isQueueModalOpen, setIsQueueModalOpen] = useState(false)
  const [selectedAuditCitizen, setSelectedAuditCitizen] = useState<UsrAuditCase | null>(null)
  const [isForensicModalOpen, setIsForensicModalOpen] = useState(false)
  const [selectedOperator, setSelectedOperator] = useState<any | null>(null)
  const [operatorAuditData, setOperatorAuditData] = useState<any[]>([])
  const [auditLoading, setAuditLoading] = useState(false)
  const [showAuditModal, setShowAuditModal] = useState(false)
  const [showOperatorAudit, setShowOperatorAudit] = useState(false)
  const [segmentFilter, setSegmentFilter] = useState('all')
  const [showAllCitizens, setShowAllCitizens] = useState(false)
  const usrRequestInFlightRef = useRef(false)
  const usrHasLoadedRef = useRef(false)
  const heatmapContainerRef = useRef<HTMLDivElement | null>(null)
  const [heatmapReady, setHeatmapReady] = useState(false)

  const recategorizeFeed = (feed: any[]) => {
    setUsrGhosts(
      feed.filter((f: any) => {
        const t = String(f?.type || '').toUpperCase()
        return t.includes('GHOST')
      })
    )
    setUsrDuplicates(
      feed.filter((f: any) => {
        const t = String(f?.type || '').toUpperCase()
        const r = String(f?.rule || '').toUpperCase()
        return t.includes('DUPLICATE') || t.includes('CLONE') || r.startsWith('B') || r.startsWith('I')
      })
    )
    setUsrAnomalies(
      feed.filter((f: any) => {
        const t = String(f?.type || '').toUpperCase()
        const r = String(f?.rule || '').toUpperCase()
        return t.includes('ANOMALY') || t.includes('INTERNAL') || r.startsWith('C') || r.startsWith('F') || r.startsWith('H')
      })
    )
  }

  const fetchUsrDashboard = async (force = false) => {
    if (usrRequestInFlightRef.current) return
    if (usrHasLoadedRef.current && !force) return

    usrRequestInFlightRef.current = true
    setUsrLoading(true)

    try {
      const [statsRes, topRiskAll, topRiskElderly, topRiskChildren, topRiskWorkers, heatmapRes] = await Promise.all([
        axios.get(`${API}/api/usr/stats`),
        axios.get(`${API}/api/usr/top-risk?limit=50`),
        axios.get(`${API}/api/usr/top-risk?limit=50&segment=elderly`),
        axios.get(`${API}/api/usr/top-risk?limit=50&segment=children`),
        axios.get(`${API}/api/usr/top-risk?limit=50&segment=workers`),
        axios.get(`${API}/api/usr/heatmap`),
      ])

      setUsrStats(statsRes.data)
      setUsrTopRisk({
        all: topRiskAll.data.citizens || [],
        elderly: topRiskElderly.data.citizens || [],
        children: topRiskChildren.data.citizens || [],
        workers: topRiskWorkers.data.citizens || []
      })
      setUsrHeatmap(heatmapRes.data.districts || [])
      usrHasLoadedRef.current = true
    } catch (err) {
      console.error('USR Dashboard core load failed', err)
      return
    } finally {
      usrRequestInFlightRef.current = false
      setUsrLoading(false)
    }

    const [intelRes, qualityRes, auditRes, rulesEFRes] = await Promise.allSettled([
      axios.get(`${API}/api/usr/intelligence/feed?limit=${INTEL_PAGE_SIZE}&offset=0`),
      axios.get(`${API}/api/usr/data-quality`),
      axios.get(`${API}/api/usr/audit-queue`),
      axios.get(`${API}/api/usr/analytics/rules-ef`),
    ])

    if (intelRes.status === 'fulfilled') {
      const feed = intelRes.value.data.feed || []
      setUsrIntelligenceTotal(intelRes.value.data.total || feed.length)
      setUsrIntelligenceFeed(feed)
      recategorizeFeed(feed)
    }

    if (qualityRes.status === 'fulfilled') {
      setUsrDataQuality(qualityRes.value.data)
    }

    if (auditRes.status === 'fulfilled') {
      setUsrAuditQueue(auditRes.value.data.queue || [])
    }

    if (rulesEFRes.status === 'fulfilled') {
      setUsrRulesEF(rulesEFRes.value.data)
    }
  }
  useEffect(() => {
    fetchUsrDashboard()
  }, [])

  const handleLoadMoreIntelligence = async () => {
    if (usrLoadingMoreIntel) return
    if (usrIntelligenceFeed.length >= usrIntelligenceTotal) return
    setUsrLoadingMoreIntel(true)
    try {
      const res = await axios.get(
        `${API}/api/usr/intelligence/feed?limit=${INTEL_PAGE_SIZE}&offset=${usrIntelligenceFeed.length}`
      )
      const more = res.data.feed || []
      const total = res.data.total || usrIntelligenceTotal
      const merged = [...usrIntelligenceFeed, ...more]
      setUsrIntelligenceTotal(total)
      setUsrIntelligenceFeed(merged)
      recategorizeFeed(merged)
    } catch (err) {
      console.error('Failed to load more intelligence alerts', err)
    } finally {
      setUsrLoadingMoreIntel(false)
    }
  }

  useEffect(() => {
    const node = heatmapContainerRef.current
    if (!node) return

    const updateReady = () => {
      setHeatmapReady(node.clientWidth > 0 && node.clientHeight > 0)
    }

    updateReady()

    if (typeof ResizeObserver === 'undefined') {
      window.setTimeout(updateReady, 150)
      return
    }

    const observer = new ResizeObserver(() => updateReady())
    observer.observe(node)
    return () => observer.disconnect()
  }, [usrLoading])

  const fetchOperatorAudit = async (opId: string) => {
    setAuditLoading(true)
    setShowOperatorAudit(true)
    try {
      const res = await axios.get(`${API}/api/usr/operator/${opId}/audit`)
      setOperatorAuditData(res.data.audit_trail || [])
      setSelectedOperator(opId)
    } catch (err) {
      console.error('Audit load failed', err)
    } finally {
      setAuditLoading(false)
    }
  }

  const runUsrBatch = async (type: 'batch' | 'sync') => {
    try {
      const url = type === 'sync'
        ? `${API}/api/usr/run-sync?limit=50000`
        : `${API}/api/usr/run-batch`
      await axios.post(url)
    } catch {
      // Error handling
    }
  }

  // --- Helper Functions ---
  const getRiskColor = (score: number) => {
    if (score >= 61) return '#ef4444'
    if (score >= 41) return '#f97316'
    if (score >= 21) return '#f59e0b'
    return '#10b981'
  }

  const getRiskTierBadge = (tier: string) => {
    const map: Record<string, { color: string, bg: string }> = {
      'CRITICAL': { color: '#ef4444', bg: 'rgba(239,68,68,0.1)' },
      'HIGH':     { color: '#f97316', bg: 'rgba(249,115,22,0.1)' },
      'MODERATE': { color: '#f59e0b', bg: 'rgba(245,158,11,0.1)' },
      'LOW':      { color: '#10b981', bg: 'rgba(16,185,129,0.1)' },
    }
    return map[tier] || map['LOW']
  }

  const getWhyExplanation = (flag: UsrFraudFlag) => {
    if (flag.rule === 'A1') return "Identified as a 'Ghost' because the age provided (105+) is physically unlikely for the region."
    if (flag.rule === 'B1') return "Potential Duplicate: This person shares an identical Name and Date of Birth with another record, suggesting a double-enrollment."
    if (flag.rule === 'C1') return "Scheme Concentration Anomaly: This GP shows an impossible volume of beneficiaries for this specific scheme."
    if (flag.rule === 'E1') return "Household Overload: Too many citizens are linked to a single Ration Card hub (Synthetic Household)."
    return (flag as any).label || flag.rule || "Pattern anomaly detected by the Intelligence Engine."
  }

  const calculateAge = (dob: string) => {
    if (!dob) return 0
    try {
      const birth = new Date(dob)
      const now = new Date()
      return now.getFullYear() - birth.getFullYear()
    } catch { return 0 }
  }

  const filteredCitizens = usrTopRisk[segmentFilter] || []

  const visibleCitizens = showAllCitizens ? filteredCitizens : filteredCitizens.slice(0, 10)
  const intelligenceFeedCount = usrIntelligenceFeed.length + usrRulesEF.rule_e.length + usrRulesEF.rule_f.length

  const handleAuditAll = () => {
    setIsQueueModalOpen(true)
  }

  const handleDownloadPdf = () => {
    window.open(`${API}/api/usr/audit-queue/export-pdf`, '_blank')
  }

  const handleDrillDown = (citizen: UsrAuditCase) => {
    setSelectedAuditCitizen(citizen)
    setIsForensicModalOpen(true)
  }
  const handleExportAuditCSV = () => {
    const allFlags = [...usrDuplicates, ...usrGhosts, ...usrAnomalies]
    if (allFlags.length === 0) {
      alert('No fraud flags to export. Run a batch analysis first.')
      return
    }
    const rows = [
      ['ID', 'Name', 'Category', 'Risk Explanation', 'Confidence', 'Shared GP', 'DOB'],
      ...allFlags.map(f => [
        f.rule,
        f.name1 || f.name || 'Unknown',
        f.label || f.type,
        getWhyExplanation(f),
        `${f.confidence}%`,
        f.shared_gp || f.gp_name || '',
        f.dob || ''
      ])
    ]
    const csv = rows.map(r => r.map(v => `"${String(v).replace(/"/g,'""')}"`).join(',')).join('\n')
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `audit_flags_${new Date().toISOString().slice(0, 10)}.csv`
    a.style.display = 'none'
    document.body.appendChild(a)
    a.click()
    setTimeout(() => {
      URL.revokeObjectURL(url)
      document.body.removeChild(a)
    }, 60000)
    setShowAuditModal(false)
  }

  return (
    <TooltipProvider>
      {/* Audit All Modal */}
      {showAuditModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm animate-in fade-in duration-300">
          <div className="bg-white rounded-3xl shadow-2xl p-8 w-full max-w-md mx-4 space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-black text-slate-900">Audit Export</h2>
                <p className="text-xs text-slate-500 mt-1">{usrDuplicates.length + usrGhosts.length + usrAnomalies.length} total flagged cases</p>
              </div>
              <button onClick={() => setShowAuditModal(false)} className="w-9 h-9 rounded-xl bg-slate-100 flex items-center justify-center hover:bg-slate-200 transition-colors text-slate-500 font-bold text-sm">✕</button>
            </div>
            <div className="space-y-3">
              <div className="flex justify-between text-xs font-bold text-slate-700 bg-slate-50 rounded-xl p-4">
                <span>Ghost Beneficiaries (Rule A)</span>
                <span className="text-rose-600">{usrGhosts.length} cases</span>
              </div>
              <div className="flex justify-between text-xs font-bold text-slate-700 bg-slate-50 rounded-xl p-4">
                <span>Duplicate Identities (Rule B)</span>
                <span className="text-orange-600">{usrDuplicates.length} cases</span>
              </div>
              <div className="flex justify-between text-xs font-bold text-slate-700 bg-slate-50 rounded-xl p-4">
                <span>Scheme Anomalies (Rule C)</span>
                <span className="text-amber-600">{usrAnomalies.length} cases</span>
              </div>
            </div>
            <div className="flex gap-3">
              <button onClick={() => setShowAuditModal(false)} className="flex-1 h-11 rounded-2xl border border-slate-200 text-sm font-bold text-slate-600 hover:bg-slate-50 transition-colors">Cancel</button>
              <button onClick={handleExportAuditCSV} className="flex-1 h-11 rounded-2xl bg-slate-900 text-white text-sm font-bold hover:bg-slate-800 transition-colors flex items-center justify-center gap-2">
                <Download className="w-4 h-4" /> Export CSV
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Forensic Operator Audit Modal */}
      {showOperatorAudit && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-md animate-in fade-in zoom-in-95 duration-300 p-4">
          <div className="bg-white rounded-[2rem] shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col overflow-hidden border border-slate-100">
            <header className="p-8 border-b border-slate-100 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-2xl bg-rose-50 flex items-center justify-center">
                  <AlertTriangle className="w-6 h-6 text-rose-600" />
                </div>
                <div>
                  <h2 className="text-xl font-black text-slate-900">Operator Forensic Audit</h2>
                  <p className="text-xs font-bold text-rose-500 uppercase tracking-widest mt-0.5">ID: {selectedOperator || '...'}</p>
                </div>
              </div>
              <button 
                onClick={() => setShowOperatorAudit(false)} 
                className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center hover:bg-slate-200 transition-colors text-slate-500"
              >✕</button>
            </header>

            <div className="flex-1 overflow-auto p-8 pt-0">
              <div className="grid grid-cols-3 gap-6 my-8 sticky top-0 z-10 bg-white pb-4">
                <div className="bg-slate-50 p-6 rounded-2xl border border-slate-100">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Total Registrations</p>
                  <p className="text-2xl font-black text-slate-900">{operatorAuditData.length}</p>
                </div>
                <div className="bg-rose-50 p-6 rounded-2xl border border-rose-100">
                  <p className="text-[10px] font-bold text-rose-400 uppercase tracking-widest mb-1">Flagged Anomalies</p>
                  <p className="text-2xl font-black text-rose-600">{operatorAuditData.filter((c: any) => c.flags.length > 0).length}</p>
                </div>
                <div className="bg-blue-50 p-6 rounded-2xl border border-blue-100">
                  <p className="text-[10px] font-bold text-blue-400 uppercase tracking-widest mb-1">Anomaly Rate</p>
                  <p className="text-2xl font-black text-blue-600">
                    {operatorAuditData.length > 0 ? Math.round((operatorAuditData.filter((c: any) => c.flags.length > 0).length / operatorAuditData.length) * 100) : 0}%
                  </p>
                </div>
              </div>

              {auditLoading ? (
                <div className="h-64 flex flex-col items-center justify-center text-slate-300 gap-4">
                  <Loader2 className="w-8 h-8 animate-spin" />
                  <p className="text-sm font-bold animate-pulse">Running full-node forensic trace...</p>
                </div>
              ) : (
                <table className="w-full text-left">
                  <thead className="sticky top-[136px] bg-white z-10">
                    <tr className="border-b border-slate-100">
                      {['Citizen', 'DOB & Gender', 'Vulnerability', 'Intelligence Flags', 'Action'].map(h => (
                        <th key={h} className="py-4 px-2 text-[9px] font-bold text-slate-400 uppercase tracking-widest">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {operatorAuditData.map((citizen: any, i: number) => (
                      <tr key={i} className={`hover:bg-slate-50/50 transition-colors ${citizen.flags.length > 0 ? 'bg-rose-50/10' : ''}`}>
                        <td className="py-6 px-2">
                          <div className="flex items-center gap-3">
                            <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-[10px] font-bold ${citizen.flags.length > 0 ? 'bg-rose-200 text-rose-700' : 'bg-slate-100 text-slate-400'}`}>
                              {citizen.name[0]}
                            </div>
                            <div>
                              <p className="text-sm font-black text-slate-900">{citizen.name}</p>
                              <p className="text-[10px] font-mono text-slate-400 uppercase">{citizen.uid}</p>
                            </div>
                          </div>
                        </td>
                        <td className="py-6 px-2">
                           <p className="text-xs font-bold text-slate-700">{citizen.dob}</p>
                           <p className="text-[10px] font-bold text-slate-400 uppercase">{citizen.gender}</p>
                        </td>
                        <td className="py-6 px-2">
                           <div className="flex items-center gap-2">
                              <span className="text-xs font-black text-slate-900">{citizen.risk_score}%</span>
                              <Badge className="text-[8px] px-1.5" variant="outline">{citizen.tier}</Badge>
                           </div>
                        </td>
                        <td className="py-6 px-2">
                          <div className="flex flex-wrap gap-1">
                            {citizen.flags.length > 0 ? citizen.flags.map((f: any, idx: number) => (
                              <Badge key={idx} className="bg-rose-100 text-rose-700 hover:bg-rose-100 border-none text-[8px] font-black uppercase px-2 py-0.5" variant="secondary">
                                {f.rule}: {f.type}
                              </Badge>
                            )) : (
                              <Badge variant="outline" className="text-slate-300 border-slate-100 text-[8px] font-bold uppercase">CLEAN RECORD</Badge>
                            )}
                          </div>
                        </td>
                        <td className="py-6 px-2">
                          <Button variant="ghost" size="sm" className="h-8 rounded-lg text-[9px] font-black uppercase tracking-widest text-blue-600 hover:bg-blue-50">
                            Deep Audit
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <footer className="p-8 bg-slate-50 border-t border-slate-100 flex justify-between items-center shrink-0">
               <p className="text-xs text-slate-400 font-medium italic">Showing all records found in the Knowledge Graph for this entry agent.</p>
               <Button onClick={() => setShowOperatorAudit(false)} className="bg-slate-900 text-white rounded-xl px-8 h-10 font-bold text-sm">Close Audit Workspace</Button>
            </footer>
          </div>
        </div>
      )}
      <div className="bg-[#fcfdfe] animate-in fade-in duration-1000 min-h-screen w-full m-0 p-0 flex flex-col">
        <ScrollArea className="flex-1 w-full m-0 p-0">
          <div className="w-full m-0 p-0">
            
            {/* --- Unified Command Header --- */}
            <header className="flex items-center justify-between p-6 md:p-8 bg-white border-b border-slate-100 sticky top-0 z-30 shadow-sm shadow-slate-900/5">
              <div className="flex items-center gap-6">
                <h1 className="text-3xl font-black tracking-tight text-slate-900 m-0">
                  Social Registry Intelligence Hub
                </h1>
                <Badge className="border-blue-200 bg-blue-50 text-blue-700 text-[10px] font-bold uppercase tracking-[0.2em] px-3 py-1">v4.0 Phase 4</Badge>
              </div>
              
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => fetchUsrDashboard(true)} disabled={usrLoading} className="rounded-xl font-bold text-xs h-9 border-slate-200">
                  {usrLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-2" /> : <TrendingUp className="w-3.5 h-3.5 mr-2" />}
                  Refresh Intel
                </Button>
                <Button onClick={() => runUsrBatch('sync')} size="sm" className="bg-slate-900 rounded-xl font-bold text-xs h-9 text-white hover:bg-slate-800">
                  <ShieldCheck className="w-3.5 h-3.5 mr-2" />
                  Field Audit Sync
                </Button>
              </div>
            </header>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 p-6 md:p-8">
               {[
                 { 
                   label: 'Integrity Index', 
                   value: typeof usrDataQuality?.integrity_index === 'number' ? `${usrDataQuality.integrity_index}%` : '—', 
                   sub: usrDataQuality ? `${usrDataQuality.total_issues.toLocaleString()} issue signals` : 'Overall Trust Score',
                   icon: <ShieldCheck className="w-5 h-5 text-blue-600" />, 
                   bg: 'bg-blue-50/50',
                   color: 'text-blue-600',
                   why: 'Measures how many records are unique and free of demographic factory patterns.'
                 },
                 { 
                   label: 'Critical Leakage', 
                   value: (usrStats?.critical_count || 0).toLocaleString(), 
                   sub: 'Immediate Interventions',
                   icon: <AlertTriangle className="w-5 h-5 text-rose-600" />, 
                   bg: 'bg-rose-50/50',
                   color: 'text-rose-600',
                   why: 'Identities with >90% probability of being synthetic or fraudulent.'
                 },
                 { 
                   label: 'Forensic Coverage', 
                   value: typeof usrStats?.coverage_pct === 'number' ? `${usrStats.coverage_pct}%` : '—',
                   sub: usrStats
                     ? `${(usrStats.total_citizens ?? 0).toLocaleString()} / ${(usrStats.registry_total ?? 2234522).toLocaleString()}`
                     : 'Sync pending',
                   icon: <Ghost className="w-5 h-5 text-amber-600" />, 
                   bg: 'bg-amber-50/50',
                   color: 'text-amber-600',
                   why: 'The percentage of the total Social Registry currently synced and analyzed in the Knowledge Graph.'
                 },
                 { 
                   label: 'Avg Vulnerability', 
                   value: usrStats?.avg_vulnerability ? usrStats.avg_vulnerability.toFixed(1) : '—', 
                   sub: 'Regional Hardship',
                   icon: <Users className="w-5 h-5 text-indigo-600" />, 
                   bg: 'bg-indigo-50/50',
                   color: 'text-indigo-600',
                   why: 'Weighted score of socio-economic vulnerability based on lifecycle stage.'
                 }
               ].map((kpi, i) => (
                 <Tooltip key={i}>
                   <TooltipTrigger asChild>
                     <Card className="glass-card p-6 border-none ring-1 ring-slate-100 intel-card-hover cursor-pointer group">
                       <div className="flex items-start justify-between">
                         <div className={`p-2.5 rounded-2xl ${kpi.bg} transition-colors group-hover:scale-110 duration-500`}>
                           {kpi.icon}
                         </div>
                       </div>
                       <div className="mt-4 space-y-1">
                         <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400">{kpi.label}</p>
                         <h2 className={`text-3xl font-black ${kpi.color}`}>{kpi.value}</h2>
                         <p className="text-[10px] font-semibold text-slate-500">{kpi.sub}</p>
                       </div>
                     </Card>
                   </TooltipTrigger>
                   <TooltipContent className="bg-slate-900 text-white rounded-xl border-none p-3 max-w-[200px]">
                     <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1">Intelligence Insight</p>
                     <p className="text-[11px] leading-relaxed">{kpi.why}</p>
                   </TooltipContent>
                 </Tooltip>
               ))}
            </div>

            {/* --- Main Dashboard Content --- */}
            <div className="grid grid-cols-12 gap-8 px-6 md:px-8 pb-12">
              
              {/* Left Column: Analytics & Mapping */}
              <div className="col-span-12 lg:col-span-8 space-y-8">
                
                {/* District Risk Heatmap */}
                <Card className="glass-panel p-8 border-none ring-1 ring-slate-100 overflow-hidden">
                   <div className="flex items-center justify-between mb-8 text-neutral-600">
                     <div>
                       <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                         Geo-Spatial Risk Deployment
                         <Map className="w-4 h-4 text-slate-400" />
                       </h3>
                       <p className="text-xs text-slate-500 font-medium mt-1">Which Districts are seeing the highest "Systemic Leakage"?</p>
                     </div>
                     <Badge className="bg-slate-100 text-slate-500 text-[9px] font-bold h-6 px-3">UPDATED REAL-TIME</Badge>
                   </div>
                   
                    <div ref={heatmapContainerRef} className="h-[300px] w-full min-w-0 relative overflow-hidden" style={{ minHeight: '300px' }}>
                      {heatmapReady && usrHeatmap.length > 0 ? (
                      <ResponsiveContainer width="100%" height={300} minWidth={0} minHeight={260}>
                        <BarChart data={usrHeatmap.slice(0, 10)} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                          <defs>
                            <linearGradient id="riskGrad" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#ef4444" stopOpacity={0.8}/>
                              <stop offset="95%" stopColor="#ef4444" stopOpacity={0.1}/>
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                          <XAxis 
                            dataKey="district" 
                            axisLine={false} 
                            tickLine={false} 
                            tick={{ fontSize: 9, fontWeight: 700, fill: '#64748b' }} 
                            interval={0}
                            angle={-15}
                            textAnchor="end"
                            dy={10} 
                          />
                          <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 9, fill: '#94a3b8' }} />
                          <RechartsTooltip cursor={{fill: '#f8fafc'}} contentStyle={{ backgroundColor: '#0f172a', borderRadius: '16px', border: 'none', color: '#fff', padding: '12px' }} />
                          <Bar dataKey="avg_risk_score" name="Risk Index" fill="url(#riskGrad)" radius={[8, 8, 0, 0]} barSize={32} />
                        </BarChart>
                      </ResponsiveContainer>
                      ) : (
                      <div className="flex h-full items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50/50 text-[11px] font-medium text-slate-400">
                        {usrLoading ? "Scanning the Knowledge Graph..." : "No regional risk data available. Run Field Audit Sync."}
                      </div>
                      )}
                    </div>
                   
                   <div className="mt-8 pt-6 border-t border-slate-50 flex items-center justify-between">
                      <div className="flex gap-6">
                        <div className="flex items-center gap-2">
                           <div className="w-2.5 h-2.5 rounded-full bg-rose-500" />
                           <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Critical Zones</span>
                        </div>
                        <div className="flex items-center gap-2">
                           <div className="w-2.5 h-2.5 rounded-full bg-orange-400" />
                           <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">High Volatility</span>
                        </div>
                      </div>
                      <Button variant="ghost" size="sm" className="text-[10px] font-bold uppercase tracking-widest gap-2 text-blue-600 hover:text-blue-700">
                        View GIS Report <ArrowRight className="w-3 h-3" />
                      </Button>
                   </div>
                </Card>

                {/* Lifecycle Segmentation Table */}
                <Card className="glass-panel p-0 border-none ring-1 ring-slate-100 overflow-hidden">
                   <div className="p-8 pb-4">
                     <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                       Lifecycle Vulnerability & Targeted Interventions
                       <UserCheck2 className="w-4 h-4 text-slate-400" />
                     </h3>
                     <p className="text-xs text-slate-500 font-medium mt-1 mb-6">Categorizing beneficiaries based on their current stage for scheme optimization.</p>
                     
                     <div className="flex gap-2 mb-6">
                       {['all', 'elderly', 'children', 'workers'].map((seg) => (
                         <Button 
                           key={seg}
                           onClick={() => setSegmentFilter(seg)}
                           variant={segmentFilter === seg ? 'default' : 'outline'}
                           className={`h-8 px-4 text-[10px] font-bold uppercase tracking-widest rounded-lg ${segmentFilter === seg ? 'bg-slate-900' : 'border-slate-100 bg-slate-50'}`}
                         >
                           {seg === 'workers' ? 'working age' : seg}
                         </Button>
                       ))}
                     </div>
                   </div>

                   <table className="w-full text-left">
                     <thead className="bg-slate-50/50 border-y border-slate-100">
                       <tr>
                         {['Citizen Name', 'Region (District)', 'Age Profile', 'Calculated Risk', 'Status'].map(h => (
                           <th key={h} className="py-3 px-8 text-[9px] font-bold uppercase tracking-[0.2em] text-slate-400">{h}</th>
                         ))}
                       </tr>
                     </thead>
                     <tbody className="divide-y divide-slate-50">
                       {filteredCitizens.length === 0 && (
                        <tr>
                          <td colSpan={5} className="py-12 px-8 text-center">
                            <p className="text-sm font-bold text-slate-400">No citizens match this filter.</p>
                            <p className="text-xs text-slate-300 mt-1">Try selecting a different segment or syncing data first.</p>
                          </td>
                        </tr>
                      )}
                      {visibleCitizens.map((citizen: UsrCitizen, i: number) => {
                         const color = getRiskColor(citizen.score)
                         const tier = getRiskTierBadge(citizen.tier || 'LOW')
                         const age = calculateAge(citizen.dob)
                         return (
                           <tr key={i} className="hover:bg-slate-50/30 transition-colors group">
                             <td className="py-4 px-8">
                               <div className="flex items-center gap-3">
                                 <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-[10px] font-bold text-slate-500">
                                   {citizen.name.split(' ').map(n => n[0]).join('')}
                                 </div>
                                 <p className="text-xs font-bold text-slate-900">{citizen.name}</p>
                               </div>
                             </td>
                             <td className="py-4 px-8 text-xs font-medium text-slate-500">{citizen.district} <span className="text-[10px] text-slate-300 ml-1">({citizen.gp})</span></td>
                             <td className="py-4 px-8">
                               <div className="flex flex-col gap-1">
                                 <span className="text-xs font-bold text-slate-700">{age} yrs</span>
                                 <span className={`text-[8px] font-bold uppercase tracking-widest ${age >= 60 ? 'text-blue-500' : age <= 18 ? 'text-indigo-500' : 'text-slate-400'}`}>
                                   {age >= 60 ? 'ELDERLY / PENSION' : age <= 18 ? 'SCHOOL AGE / NUTRITION' : 'WORKER / NREGA'}
                                 </span>
                               </div>
                             </td>
                             <td className="py-4 px-8">
                               <div className="flex items-center gap-2">
                                 <div className="flex-1 h-1.5 w-16 bg-slate-100 rounded-full overflow-hidden">
                                   <div className="h-full rounded-full transition-all duration-1000" style={{ width: `${citizen.score}%`, backgroundColor: color }} />
                                 </div>
                                 <span className="text-xs font-black text-slate-900">{citizen.score}%</span>
                               </div>
                             </td>
                             <td className="py-4 px-8">
                               <Badge className="text-[8px] font-black uppercase tracking-widest px-2" style={{ backgroundColor: tier.bg, color: tier.color }}>
                                 {citizen.tier || 'MODERATE'}
                               </Badge>
                             </td>
                           </tr>
                         )
                       })}
                     </tbody>
                   </table>
                    {filteredCitizens.length > 10 && (
                      <div className="p-6 bg-slate-50/30 border-t border-slate-100 text-center">
                        <Button
                          variant="link"
                          onClick={() => setShowAllCitizens((v: boolean) => !v)}
                          className="text-xs font-bold text-slate-500 hover:text-slate-900"
                        >
                          {showAllCitizens
                            ? 'Show Less'
                            : `View All ${filteredCitizens.length} ${segmentFilter === 'all' ? 'High-Volume' : segmentFilter.charAt(0).toUpperCase() + segmentFilter.slice(1)} Cases`
                          }
                        </Button>
                      </div>
                    )}
                    {filteredCitizens.length <= 10 && filteredCitizens.length > 0 && (
                      <div className="p-4 bg-slate-50/30 border-t border-slate-100 text-center">
                        <span className="text-[10px] font-bold text-slate-300 uppercase tracking-widest">Showing all {filteredCitizens.length} cases in this segment</span>
                      </div>
                    )}
                </Card>
              </div>

              {/* Right Column: Intelligence Feed & Data Quality */}
              <div className="col-span-12 lg:col-span-4 space-y-8">
                
                {/* Rules & Explainability Feed */}
                <Card className="glass-panel p-0 border-none ring-1 ring-slate-100 overflow-hidden bg-slate-900">
                   <div className="p-8">
                     <h3 className="text-base font-bold white flex items-center gap-2">
                       Intelligence Feed
                       <Settings className="w-4 h-4 text-slate-500 animate-spin-slow" />
                     </h3>
                     <p className="text-[11px] text-slate-400 font-medium mt-1">Real-time Anomaly Detections derived from the Identity Hub.</p>
                   </div>

                    <ScrollArea className="h-[435px] border-t border-slate-800">
                      <div className="p-6 space-y-4">
                        {/* Unified Knowledge Graph Intelligence Feed (A-I) */}
                        {usrIntelligenceFeed.map((flag: any, i: number) => (
                           <div key={`intel-${i}`} className="p-4 rounded-2xl bg-slate-800/50 border border-slate-700/50 hover:bg-slate-800 transition-colors group">
                               <div className="flex items-start justify-between mb-3">
                                  <div className="flex items-center gap-2">
                                     {flag.type === 'GHOST' ? <Ghost className="w-3.5 h-3.5 text-rose-500" /> : <Copy className="w-3.5 h-3.5 text-orange-400" />}
                                     <span className="text-[10px] font-black uppercase tracking-[0.2em]" style={{ color: flag.type === 'GHOST' ? '#ef4444' : '#fb923c' }}>
                                        {flag.label || `Rule ${flag.rule}`}
                                     </span>
                                  </div>
                                  <Badge className="bg-slate-900 border-slate-700 text-slate-400 text-[8px] font-bold">{flag.confidence}% CONF</Badge>
                               </div>
                               <p className="text-xs font-bold text-white mb-2 leading-snug">{flag.name || 'Unknown Identity'}</p>
                               <p className="text-[10px] text-slate-500 leading-relaxed font-medium">
                                 Detected in <span className="text-slate-300">{flag.gp_name}</span>. {flag.description}
                               </p>
                           </div>
                        ))}

                        {/* Household Overload Rules (E) */}
                        {usrRulesEF.rule_e.slice(0, 5).map((caseData: any, i: number) => (
                          <div key={`e-${i}`} className="p-4 rounded-2xl bg-indigo-900/30 border border-indigo-500/30 hover:bg-indigo-900/40 transition-colors group">
                            <div className="flex items-start justify-between mb-3">
                               <div className="flex items-center gap-2">
                                  <Users className="w-3.5 h-3.5 text-indigo-400" />
                                  <span className="text-[10px] font-black uppercase tracking-[0.2em] text-indigo-400">Rule E1</span>
                               </div>
                               <Badge className="bg-indigo-950 text-indigo-300 text-[8px] font-bold">95% CONF</Badge>
                            </div>
                            <p className="text-xs font-bold text-white mb-1">RC: {caseData.ration_card}</p>
                            <p className="text-[10px] text-indigo-200/60 font-medium">Synthetic Household: {caseData.member_count} members linked to one card.</p>
                          </div>
                        ))}

                        {/* Operator Corruption Rules (F) */}
                        {usrRulesEF.rule_f.slice(0, 10).map((caseData: any, i: number) => (
                          <div 
                            key={`f-${i}`} 
                            onClick={() => fetchOperatorAudit(caseData.operator_id)}
                            className="p-4 rounded-2xl bg-rose-900/30 border border-rose-500/30 hover:bg-rose-900/40 transition-all cursor-pointer group active:scale-95"
                          >
                            <div className="flex items-start justify-between mb-3">
                               <div className="flex items-center gap-2">
                                  <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
                                  <span className="text-[10px] font-black uppercase tracking-[0.2em] text-rose-400">Rule F1</span>
                               </div>
                               <Badge className="bg-rose-950 text-rose-300 text-[8px] font-bold">90% CONF</Badge>
                            </div>
                            <p className="text-xs font-bold text-white mb-1">Operator: {caseData.operator_id}</p>
                            <div className="flex items-center justify-between">
                              <p className="text-[10px] text-rose-200/60 font-medium">{Math.round(caseData.fraud_rate * 100)}% Forensic Fraud Rate.</p>
                              <span className="text-[9px] font-black text-rose-400 uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-opacity">Drill Down →</span>
                            </div>
                          </div>
                        ))}

                        {intelligenceFeedCount === 0 && (
                          <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-800/40 px-4 py-8 text-center">
                            <p className="text-[11px] font-semibold text-slate-200">No intelligence alerts available yet.</p>
                            <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
                              The feed fills after fraud-analysis endpoints return alerts from the graph. If you just opened the hub, give the heavier scans a few seconds to finish.
                            </p>
                          </div>
                        )}
                      </div>
                    </ScrollArea>
                   
                   <div className="p-6 bg-slate-800 text-white flex items-center justify-between">
                     <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                       Showing {usrIntelligenceFeed.length.toLocaleString()} of {usrIntelligenceTotal.toLocaleString()} alerts
                     </span>
                     <div className="flex items-center gap-2">
                       {usrIntelligenceFeed.length < usrIntelligenceTotal && (
                         <Button
                           size="sm"
                           onClick={handleLoadMoreIntelligence}
                           disabled={usrLoadingMoreIntel}
                           className="h-8 bg-slate-700 hover:bg-slate-600 text-white text-[10px] font-black uppercase px-4 rounded-xl"
                         >
                           {usrLoadingMoreIntel ? 'Loading...' : 'Load More'}
                         </Button>
                       )}
                       <Button size="sm" onClick={handleAuditAll} className="h-8 bg-blue-600 hover:bg-blue-500 text-white text-[10px] font-black uppercase px-4 rounded-xl">
                         Audit All
                       </Button>
                     </div>
                   </div>
                </Card>

                {/* Audit Queue / Export Card */}
                <Card className="glass-panel p-8 border-none ring-1 ring-slate-100 bg-gradient-to-br from-indigo-600 to-blue-700 text-white relative overflow-hidden">
                   <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 blur-3xl rounded-full translate-x-1/2 -translate-y-1/2" />
                   <h3 className="text-base font-bold mb-2 flex items-center gap-2">
                     Field Audit Portal
                     <Download className="w-4 h-4 text-white/60" />
                   </h3>
                   <div className="space-y-4 mb-6">
                      <p className="text-[11px] text-indigo-100 font-medium leading-relaxed">
                        Top {usrAuditQueue.length} cases pre-selected for physical verification based on concurrent fraud signals.
                      </p>
                      <div className="space-y-2">
                         {usrAuditQueue.slice(0, 3).map((caseItem: UsrAuditCase, idx: number) => (
                           <div key={idx} className="flex items-center justify-between bg-white/10 p-2.5 rounded-xl border border-white/10">
                              <div className="flex flex-col">
                                <span className="text-[10px] font-black">{caseItem.name}</span>
                                <span className="text-[8px] text-indigo-200 uppercase">{caseItem.gp} | {caseItem.flags} Signals</span>
                              </div>
                              <Button 
                                variant="ghost" 
                                size="icon" 
                                className="h-6 w-6 text-white hover:bg-white/20"
                                onClick={() => handleDrillDown(caseItem)}
                              >
                                <ArrowRight className="w-3 h-3" />
                              </Button>
                           </div>
                         ))}
                      </div>
                   </div>
                    <Button 
                      onClick={handleDownloadPdf}
                      className="w-full bg-white text-indigo-700 font-black text-xs h-12 rounded-2xl hover:bg-indigo-50 shadow-lg"
                    >
                      Export Priority List (.PDF)
                    </Button>
                </Card>

              </div>
            </div>
          </div>
        </ScrollArea>
      </div>

      {/* MODAL: Full Priority Queue */}
      <Dialog open={isQueueModalOpen} onOpenChange={setIsQueueModalOpen}>
        <DialogContent className="max-w-4xl max-h-[80vh] min-h-0 overflow-hidden flex flex-col p-8">
          <DialogHeader>
            <DialogTitle className="text-2xl font-black text-slate-800 uppercase tracking-tight">Priority Audit Queue</DialogTitle>
            <DialogDescription className="text-slate-500 font-medium">
              Segment Analysis: Top 50 citizens flagged for immediate field verification.
            </DialogDescription>
          </DialogHeader>
          
          <div className="flex-1 min-h-0 mt-6 pr-2 overflow-y-auto">
            <div className="space-y-3 pr-2">
              {usrAuditQueue.map((item: UsrAuditCase, idx: number) => (
                <div key={idx} className="flex items-center justify-between p-4 bg-slate-50 rounded-2xl border border-slate-100 hover:border-blue-200 transition-all group">
                  <div className="flex gap-4 items-center">
                    <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-bold text-xs ring-2 ring-white">
                      {item.flags}
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-slate-800">{item.name}</h4>
                      <p className="text-[10px] text-slate-500 font-medium">{item.gp} | {item.district}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <Badge variant="outline" className="text-[9px] border-slate-200 text-slate-500">{item.uid}</Badge>
                    <Button 
                      size="sm" 
                      variant="ghost" 
                      className="h-8 w-8 rounded-full text-blue-600 hover:bg-blue-50"
                      onClick={() => {
                        setIsQueueModalOpen(false)
                        handleDrillDown(item)
                      }}
                    >
                      <ArrowRight className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-8 flex justify-end gap-3 pt-6 border-t border-slate-100">
             <Button variant="outline" onClick={() => setIsQueueModalOpen(false)} className="rounded-xl border-slate-200 text-slate-600 font-bold text-[10px] uppercase">Close</Button>
             <Button onClick={handleDownloadPdf} className="bg-blue-600 hover:bg-blue-500 text-white font-bold text-[10px] uppercase rounded-xl px-6">
                Download PDF Brief (.pdf)
             </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* MODAL: Forensic Profile Detail */}
      <Dialog open={isForensicModalOpen} onOpenChange={setIsForensicModalOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-hidden flex flex-col p-8 rounded-3xl">
          {selectedAuditCitizen && (
            <>
              <DialogHeader className="mb-6">
                <div className="flex items-center gap-4 mb-2">
                   <div className="h-12 w-12 rounded-2xl bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center text-white shadow-lg">
                      <UserCheck2 className="w-6 h-6" />
                   </div>
                   <div>
                     <DialogTitle className="text-2xl font-black text-slate-900 leading-none mb-1">{selectedAuditCitizen.name}</DialogTitle>
                     <DialogDescription className="text-slate-500 font-bold text-xs uppercase tracking-widest">{selectedAuditCitizen.uid}</DialogDescription>
                   </div>
                </div>
              </DialogHeader>

              <ScrollArea className="flex-1 pr-4">
                <div className="space-y-6">
                  {/* Demographics Grid */}
                  <div className="grid grid-cols-2 gap-4">
                    <div className="p-4 bg-slate-50 rounded-2xl border border-slate-100">
                      <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1">Gender / DOB</p>
                      <p className="text-xs font-black text-slate-700">{selectedAuditCitizen.gender} | {selectedAuditCitizen.dob}</p>
                    </div>
                    <div className="p-4 bg-slate-50 rounded-2xl border border-slate-100">
                      <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1">Intelligence Region</p>
                      <p className="text-xs font-black text-slate-700">{selectedAuditCitizen.gp} ({selectedAuditCitizen.block})</p>
                    </div>
                  </div>

                  {/* Flag Evidence List */}
                  <div className="space-y-3">
                    <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest flex items-center gap-2">
                       <AlertTriangle className="w-3 h-3 text-rose-500" />
                       Intelligence Evidence Trail ({selectedAuditCitizen.flags})
                    </h5>
                    {selectedAuditCitizen.flag_notes.map((note: string, i: number) => (
                      <div key={i} className="p-4 bg-rose-50 border border-rose-100 rounded-2xl text-rose-800 text-xs font-medium leading-relaxed">
                        {note}
                      </div>
                    ))}
                  </div>

                  {/* Action Recommendations */}
                  <div className="p-6 bg-blue-50 border border-blue-100 rounded-3xl">
                     <h5 className="text-[10px] font-black text-blue-900 uppercase tracking-widest mb-3">Field Action Protocol</h5>
                     <ul className="space-y-2">
                        <li className="flex items-start gap-3 text-[11px] text-blue-800 font-medium">
                           <div className="w-4 h-4 rounded-full bg-blue-200 flex-shrink-0 flex items-center justify-center text-[10px]">1</div>
                           Verify physical existence at the registered GP address.
                        </li>
                        <li className="flex items-start gap-3 text-[11px] text-blue-800 font-medium">
                           <div className="w-4 h-4 rounded-full bg-blue-200 flex-shrink-0 flex items-center justify-center text-[10px]">2</div>
                           Check Ration Card / Aadhaar linkage for duplicate hubs.
                        </li>
                        <li className="flex items-start gap-3 text-[11px] text-blue-800 font-medium">
                           <div className="w-4 h-4 rounded-full bg-blue-200 flex-shrink-0 flex items-center justify-center text-[10px]">3</div>
                           Collect photographic evidence of the household.
                        </li>
                     </ul>
                  </div>
                </div>
              </ScrollArea>

              <div className="mt-8 pt-6 border-t border-slate-100">
                <Button 
                  onClick={() => setIsForensicModalOpen(false)}
                  className="w-full bg-slate-900 hover:bg-slate-800 text-white font-black text-[10px] uppercase h-12 rounded-2xl tracking-widest"
                >
                  Confirm Awareness & Close
                </Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </TooltipProvider>
  )
}



