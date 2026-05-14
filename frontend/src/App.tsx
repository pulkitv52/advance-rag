import React, { useState, useRef, useEffect, DragEvent, ChangeEvent } from 'react'
import {
  Search,
  Loader2,
  CheckCircle,
  XCircle,
  Zap,
  Network,
  LayoutDashboard,
  FileText,
  Settings,
  Database,
  Info,
  ExternalLink,
  Plus,
  Trash2
} from 'lucide-react'
import ForceGraph2D from 'react-force-graph-2d'
import axios from 'axios'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { toPng } from 'html-to-image'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer,
  LineChart, Line, PieChart, Pie, Cell, Legend
} from 'recharts'


// Visualization Components
const DynamicFlow = ({ config }: { config: any }) => {
  const { data, options = {} } = config

  if (!data || !Array.isArray(data)) return null

  return (
    <div data-viz-container className="my-10 w-full bg-white p-6 rounded-3xl border border-slate-100 shadow-sm animate-in fade-in duration-700">
      <h4 className="text-[10px] font-bold uppercase tracking-[0.3em] text-slate-300 mb-6 px-2">{options.title || 'Workflow'}</h4>
      <div className="space-y-3">
        {data.map((step: any, index: number) => (
          <div key={`${step.name}-${index}`} className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-2xl bg-slate-900 text-white text-xs font-bold flex items-center justify-center shrink-0">
              {step.value ?? index + 1}
            </div>
            <div className="flex-1 rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3 shadow-sm">
              <p className="text-sm font-semibold text-slate-900">{step.name}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

const DynamicChart = ({ config }: { config: any }) => {
  const { type, data, options = {} } = config
  const COLORS = ['#0f172a', '#334155', '#475569', '#64748b', '#94a3b8', '#cbd5e1']

  if (!data || !Array.isArray(data)) return null
  if (type === 'flow') return <DynamicFlow config={config} />

  return (
    <div data-viz-container className="my-10 h-[350px] w-full bg-white p-6 rounded-3xl border border-slate-100 shadow-sm transition-all hover:shadow-md animate-in fade-in duration-700">
      <h4 className="text-[10px] font-bold uppercase tracking-[0.3em] text-slate-300 mb-6 px-2">{options.title || 'Data Analytics'}</h4>
      <ResponsiveContainer width="100%" height={280} minWidth={0} minHeight={240}>
        {type === 'bar' ? (
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
            <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#94a3b8' }} dy={10} />
            <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#94a3b8' }} />
            <RechartsTooltip
              contentStyle={{ backgroundColor: '#0f172a', borderRadius: '12px', border: 'none', color: '#fff', fontSize: '10px' }}
              itemStyle={{ color: '#fff' }}
            />
            <Bar dataKey="value" fill="#0f172a" radius={[6, 6, 0, 0]} barSize={40} />
          </BarChart>
        ) : type === 'line' ? (
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
            <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#94a3b8' }} dy={10} />
            <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#94a3b8' }} />
            <RechartsTooltip contentStyle={{ backgroundColor: '#0f172a', borderRadius: '12px', border: 'none', color: '#fff', fontSize: '10px' }} />
            <Line type="monotone" dataKey="value" stroke="#0f172a" strokeWidth={3} dot={{ r: 4, fill: '#0f172a', strokeWidth: 2, stroke: '#fff' }} activeDot={{ r: 6 }} />
          </LineChart>
        ) : (
          <PieChart>
            <Pie data={data} innerRadius={60} outerRadius={80} paddingAngle={5} dataKey="value">
              {data.map((_: any, index: number) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <RechartsTooltip contentStyle={{ backgroundColor: '#0f172a', borderRadius: '12px', border: 'none', color: '#fff', fontSize: '10px' }} />
            <Legend verticalAlign="bottom" height={36} iconType="circle" wrapperStyle={{ fontSize: '10px', textTransform: 'uppercase', fontWeight: 'bold', letterSpacing: '0.1em' }} />
          </PieChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}

// Shadcn UI Components
import { Button } from "./components/ui/button"
import { Input } from "./components/ui/input"
import { Card } from "./components/ui/card"
import { ScrollArea } from "./components/ui/scroll-area"
import { Badge } from "./components/ui/badge"
import { Checkbox } from "./components/ui/checkbox"
import { Separator } from "./components/ui/separator"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./components/ui/tabs"
import { Avatar, AvatarFallback, AvatarImage } from "./components/ui/avatar"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./components/ui/tooltip"
import { EligibilityStudio } from "./components/EligibilityStudio"
import { UsrDashboard } from "./components/UsrDashboard"


const API = (import.meta as any).env.VITE_API_BASE_URL || 'http://localhost:8081'

type DocStatus = 'pending' | 'processing' | 'success' | 'failed'

interface Document {
  id: string
  filename: string
  status: DocStatus
  sub_status?: string
  progress_percent?: number
  chunks_indexed?: number
  elements_parsed?: number
}

interface Source {
  filename: string
  page?: number
  score: number
  snippet: string
}

interface QueryResult {
  analysis_id?: string
  project_id?: string | null
  query: string
  answer: string
  sources: Source[]
  latency_ms: number
  confidence_score?: number
  citation_coverage?: number
  graph_enrichment_used?: boolean
  weak_claims?: string[]
}

interface Project {
  id: string
  name: string
  description?: string | null
  created_at: string
}

interface SavedReport {
  id: string
  analysis_id: string
  filename: string
  format: string
  created_at: string
}

interface SaveFilePickerOptions {
  suggestedName?: string
  types?: Array<{
    description?: string
    accept: Record<string, string[]>
  }>
}

interface FileSystemWritableFileStream {
  write(data: Blob): Promise<void>
  close(): Promise<void>
}

interface FileSystemFileHandle {
  createWritable(): Promise<FileSystemWritableFileStream>
}

// Immersive Graph Color Map
const ENTITY_COLORS: Record<string, string> = {
  'District': '#6366f1',     // Indigo (Hierarchy Root)
  'Block': '#0ea5e9',        // Sky Blue (Sub-area)
  'GP': '#14b8a6',           // Teal (Local Governance)
  'Citizen': '#000000',      // Black (Beneficiary)
  'Scheme': '#a855f7',       // Purple (Benefit)
  'FraudFlag': '#ef4444',    // Red (Alert!)
  'Mobile': '#f97316',       // Orange (Identity Hub)
  'RationCard': '#fbbf24',   // Gold (Household Hub)
  'Operator': '#059669',     // Emerald (Audit Hub)
  'Address': '#64748b',      // Slate (Location Hub)
  'Person': '#0f172a',       // Deep Navy
  'Organization': '#3b82f6', // Bright Blue 
  'Document': '#334155',     // Dark Slate
  'Event': '#db2777',        // Rose
  'Concept': '#8b5cf6',      // Violet
  'Location': '#10b981',     // Emerald
  'Default': '#94a3b8'       // Slate
}

// Keep map legend focused on labels that exist in the current USR graph model.
const DATABASE_ENTITY_LEGEND: string[] = [
  'District',
  'Block',
  'GP',
  'Citizen',
  'Scheme',
  'FraudFlag',
  'Mobile',
  'RationCard',
  'Operator',
  'Address',
]

const ENTITY_TYPE_ALIASES: Record<string, string> = {
  'org': 'Organization', 'company': 'Organization', 'agency': 'Organization', 'institution': 'Organization', 'body': 'Organization', 'department': 'Organization', 'ministry': 'Organization',
  'place': 'Location', 'city': 'Location', 'country': 'Location', 'region': 'Location', 'state': 'Location', 'district': 'Location', 'office': 'Location',
  'officer': 'Person', 'individual': 'Person', 'user': 'Person', 'human': 'Person', 'member': 'Person', 'staff': 'Person', 'pensioner': 'Person',
  'date': 'Event', 'milestone': 'Event', 'deadline': 'Event', 'meeting': 'Event', 'scheme': 'Scheme',
  'file': 'Document', 'report': 'Document', 'paper': 'Document', 'source': 'Document', 'circular': 'Document', 'order': 'Document'
}

const resolveEntityCategory = (type: string = '', label: string = '') => {
  const t = type.toLowerCase().trim();
  const l = (label || '').toLowerCase().trim();

  const exactKey = Object.keys(ENTITY_COLORS).find(k => k.toLowerCase() === t);
  if (exactKey) return exactKey;

  if (t === 'gp' || t === 'gram_panchayat') return 'GP';
  if (t === 'fraudflag' || t === 'fraud') return 'FraudFlag';

  const aliasTarget = ENTITY_TYPE_ALIASES[t];
  if (aliasTarget) return aliasTarget;

  if (t === 'concept') {
    if (/(scheme|program|programme|policy|initiative|service)/.test(l)) return 'Scheme';
    return 'Concept';
  }

  if (/(person|officer|individual|pensioner|analyst|consultant|manager|doctor|engineer|employee|official)/.test(t)) return 'Person';
  if (/(citizen|beneficiary|applicant)/.test(t)) return 'Citizen';
  if (t.includes('district')) return 'District';
  if (t.includes('block')) return 'Block';
  if (/(gp|gram_panchayat)/.test(t)) return 'GP';
  if (/(scheme|program|programme|project|policy|initiative|service|framework|solution)/.test(t)) return 'Scheme';
  if (/(fraud|flag|anomaly|duplicate|overload|corruption)/.test(t)) return 'FraudFlag';
  if (t.includes('mobile') || t.includes('phone')) return 'Mobile';
  if (t.includes('operator') || t.includes('entry')) return 'Operator';
  if (t.includes('ration') || t.includes('household')) return 'RationCard';
  if (t.includes('address') || t.includes('lives_at')) return 'Address';
  if (/(org|organization|department|dept|ministry|agency|board|authority|corporation|company|committee|commission|university|institution|government)/.test(t)) return 'Organization';
  if (/(location|place|city|country|region|state|village|office|road|street|building|house|site)/.test(t)) return 'Location';

  if (/(officer|pensioner|person|individual|medical|doctor|analyst|consulting|manager|engineer|trader)/.test(l)) return 'Person';
  if (/(government|govt|dept|department|ministry|samiti|board|authority|org|asso|corp|corporation|university|public health)/.test(l)) return 'Organization';
  if (l.includes('district')) return 'District';
  if (l.includes('block')) return 'Block';
  if (/(scheme|program|programme|policy|initiative|service|framework|solution)/.test(l)) return 'Scheme';
  if (/(fraud|flag|anomaly|duplicate|overload|corruption)/.test(l)) return 'FraudFlag';
  if (/(gp|gram panchayat|gram_panchayat)/.test(l)) return 'GP';

  return 'Default';
}

const resolveEntityColor = (type: string, label: string = '') => {
  const category = resolveEntityCategory(type, label);
  return ENTITY_COLORS[category] || ENTITY_COLORS.Default;
}

export default function App() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState<string>('')
  const [savedAnalyses, setSavedAnalyses] = useState<QueryResult[]>([])
  const [reportHistory, setReportHistory] = useState<SavedReport[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [query, setQuery] = useState('');
  const [activeTab, setActiveTab] = useState('research');
  const [querying, setQuerying] = useState(false);
  const [savingAnalysis, setSavingAnalysis] = useState(false)
  const [result, setResult] = useState<QueryResult | null>(null)
  const [selectedSource, setSelectedSource] = useState<Source | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Graph States
  const [graphData, setGraphData] = useState({ nodes: [], links: [] })
  const [loadingGraph, setLoadingGraph] = useState(false)
  const [projectsReady, setProjectsReady] = useState(false)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const mapContainerRef = useRef<HTMLDivElement>(null)
  const graphRequestInFlightRef = useRef(false)

  const [mapDimensions, setMapDimensions] = useState({ width: 800, height: 600 })
  const activeProject = projects.find((project: Project) => project.id === selectedProjectId) || null

  useEffect(() => {
    const updateDimensions = () => {
      if (mapContainerRef.current) {
        setMapDimensions({
          width: mapContainerRef.current.clientWidth,
          height: mapContainerRef.current.clientHeight
        })
      }
    }

    window.addEventListener('resize', updateDimensions)
    // Small delay to ensure Tab transition is complete before measuring
    const timer = setTimeout(updateDimensions, 200)

    return () => {
      window.removeEventListener('resize', updateDimensions)
      clearTimeout(timer)
    }
  }, [loadingGraph])

  const fetchDocuments = async (projectId?: string) => {
    if (!projectId) {
      setDocuments([])
      setSelectedIds(new Set())
      return
    }

    try {
      const docsRes = await axios.get(`${API}/documents/?project_id=${projectId}`)
      const nextDocuments = docsRes.data.documents || []
      setDocuments(nextDocuments)
      setSelectedIds(prev => {
        const allowedIds = new Set(nextDocuments.map((doc: Document) => doc.id))
        return new Set(Array.from(prev).filter(id => allowedIds.has(id)))
      })
      nextDocuments.forEach((doc: any) => {
        if (doc.status === 'pending' || doc.status === 'processing') {
          pollStatus(doc.id || doc.document_id)
        }
      })
    } catch (err) {
      console.error('Failed to fetch documents', err)
    }
  }

  useEffect(() => {
    const bootstrap = async () => {
      try {
        const projectsRes = await axios.get(`${API}/projects/`)
        const nextProjects = projectsRes.data.projects || []
        setProjects(nextProjects)
        if (nextProjects.length > 0) {
          setSelectedProjectId(prev => prev || nextProjects[0].id)
        }
      } catch (err) {
        console.error("Failed to bootstrap app state", err)
      } finally {
        setProjectsReady(true)
      }
    }
    bootstrap()
  }, [])

  useEffect(() => {
    if (!projectsReady) return
    fetchDocuments(selectedProjectId)
  }, [projectsReady, selectedProjectId])

  useEffect(() => {
    if (!projectsReady) return

    if (projects.length === 0) {
      if (selectedProjectId) setSelectedProjectId('')
      return
    }

    const hasSelectedProject = projects.some((project: Project) => project.id === selectedProjectId)
    if (!hasSelectedProject) {
      setSelectedProjectId(projects[0].id)
    }
  }, [projectsReady, projects, selectedProjectId])

  useEffect(() => {
    const fetchSavedAnalyses = async () => {
      if (!selectedProjectId) {
        setSavedAnalyses([])
        return
      }
      try {
        const res = await axios.get(`${API}/analyses/?project_id=${selectedProjectId}`)
        setSavedAnalyses(res.data.analyses || [])
      } catch (err) {
        console.error("Failed to fetch saved analyses", err)
      }
    }
    fetchSavedAnalyses()
  }, [selectedProjectId])

  useEffect(() => {
    const fetchReportHistory = async () => {
      if (!result?.analysis_id) {
        setReportHistory([])
        return
      }
      try {
        const res = await axios.get(`${API}/analyses/${result.analysis_id}/reports`)
        setReportHistory(res.data.reports || [])
      } catch (err) {
        console.error("Failed to fetch report history", err)
      }
    }
    fetchReportHistory()
  }, [result?.analysis_id])

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    if (!selectedProjectId) {
      setError('Select a project before uploading documents.')
      return
    }
    setUploading(true)
    setError(null)
    const form = new FormData()
    Array.from(files).forEach(f => form.append('files', f))
    if (selectedProjectId) {
      form.append('project_id', selectedProjectId)
    }
    try {
      const res = await axios.post(`${API}/documents/upload`, form)
      const uploaded: any[] = res.data.documents
      const formatted = uploaded.map(d => ({ ...d, id: d.document_id }))
      setDocuments(prev => [...formatted, ...prev])
      uploaded.forEach(doc => pollStatus(doc.document_id))
      await fetchDocuments(selectedProjectId)
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Upload failed.')
    } finally {
      setUploading(false)
    }
  }

  const pollStatus = async (id: string) => {
    const interval = setInterval(async () => {
      try {
        const res = await axios.get(`${API}/documents/${id}`)
        const doc = res.data
        setDocuments(prev => prev.map(d => (d.id === id || (d as any).document_id === id) ? { ...d, ...doc } : d))
        if (doc.status === 'success' || doc.status === 'failed') clearInterval(interval)
      } catch { clearInterval(interval) }
    }, 2000)
  }

  const handleCreateProject = async () => {
    const name = window.prompt('Enter a project name')?.trim()
    if (!name) return

    try {
      const res = await axios.post(`${API}/projects/`, { name, description: '' })
      const project = res.data as Project
      setProjects(prev => [project, ...prev])
      setSelectedProjectId(project.id)
    } catch (err) {
      console.error('Failed to create project', err)
      setError('Failed to create project.')
    }
  }

  const handleLoadAnalysis = (analysis: QueryResult) => {
    setResult(analysis)
    setQuery(analysis.query)
    setSelectedSource(null)
    setError(null)
  }

  const saveCurrentAnalysis = async () => {
    if (!result) return null
    if (result.analysis_id) return result.analysis_id

    setSavingAnalysis(true)
    try {
      const res = await axios.post(`${API}/analyses/`, {
        project_id: selectedProjectId || null,
        query: result.query,
        answer: result.answer,
        confidence_score: result.confidence_score ?? null,
        citation_coverage: result.citation_coverage ?? null,
        graph_enrichment_used: result.graph_enrichment_used ?? false,
        sources: result.sources,
      })

      const nextAnalysisId = res.data.id as string
      const savedResult = { ...result, analysis_id: nextAnalysisId, project_id: selectedProjectId || null }
      setResult(savedResult)
      setSavedAnalyses(prev => [{ ...savedResult }, ...prev])
      return nextAnalysisId
    } catch (err) {
      console.error('Failed to save analysis', err)
      setError('Failed to save analysis.')
      return null
    } finally {
      setSavingAnalysis(false)
    }
  }

  const handleDownloadSavedReport = async (reportId: string) => {
    try {
      const response = await axios.get(`${API}/reports/${reportId}/download`, { responseType: 'blob' })
      const blob = response.data instanceof Blob ? response.data : new Blob([response.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      const disposition = response.headers['content-disposition'] || ''
      const filenameMatch = disposition.match(/filename\*?=(?:UTF-8''|\")?([^;\"\n]+)/i)
      const filename = filenameMatch ? decodeURIComponent(filenameMatch[1].replace(/\"/g, '').trim()) : `report-${reportId}.pdf`
      link.href = url
      link.download = filename
      link.style.display = 'none'
      document.body.appendChild(link)
      link.click()
      setTimeout(() => {
        window.URL.revokeObjectURL(url)
        link.remove()
      }, 60000)
    } catch (err) {
      console.error('Failed to download saved report', err)
      setError('Failed to download saved report.')
    }
  }

  const handleQuery = async () => {
    if (!query.trim()) return
    setQuerying(true)
    setResult(null)
    setError(null)
    setSelectedSource(null)
    try {
      const payload = {
        query,
        top_k: 10,
        document_ids: selectedIds.size > 0 ? Array.from(selectedIds) : null
      }
      const res = await axios.post(`${API}/query/`, payload)
      setResult({ ...res.data, project_id: selectedProjectId || null })
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Query failed.')
    } finally {
      setQuerying(false)
    }
  }

  const fetchGraph = async () => {
    if (graphRequestInFlightRef.current) return

    graphRequestInFlightRef.current = true
    setLoadingGraph(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (selectedIds.size > 0) {
        params.set('ids', Array.from(selectedIds).join(','))
      }
      if (selectedProjectId) {
        params.set('project_id', selectedProjectId)
      }
      if (query.trim()) {
        params.set('q', query.trim())
      }

      const queryString = params.toString()
      let res = await axios.get(`${API}/documents/graph/all${queryString ? `?${queryString}` : ''}`)

      // If project-scoped graph is empty, retry unscoped so USR/global graph still appears.
      if ((res.data?.nodes || []).length === 0 && selectedProjectId && selectedIds.size === 0) {
        const fallbackParams = new URLSearchParams()
        if (query.trim()) {
          fallbackParams.set('q', query.trim())
        }
        const fallbackQuery = fallbackParams.toString()
        res = await axios.get(`${API}/documents/graph/all${fallbackQuery ? `?${fallbackQuery}` : ''}`)
      }

      const normalizedNodes = (res.data?.nodes || []).map((node: any) => ({
        ...node,
        type: resolveEntityCategory(node?.type || '', node?.label || node?.id || '')
      }))
      setGraphData({
        nodes: normalizedNodes,
        links: res.data?.links || []
      })
    } catch (err: any) {
      const backendDetail = err?.response?.data?.detail
      setError(backendDetail || "Failed to load graph data. Ensure backend and Neo4j are running.")
    } finally {
      graphRequestInFlightRef.current = false
      setLoadingGraph(false)
    }
  }


  useEffect(() => {
    if (activeTab !== 'map' || !projectsReady) return
    fetchGraph()
  }, [activeTab, projectsReady, selectedProjectId])

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleDeleteDocument = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    if (!confirm("Are you sure you want to permanently delete this document from all databases?")) return

    try {
      await axios.delete(`${API}/documents/${id}`)
      setDocuments(prev => prev.filter(d => d.id !== id && (d as any).document_id !== id))
      setSelectedIds(prev => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    } catch (err) {
      setError("Failed to delete document.")
    }
  }

  const handleExportReport = async () => {
    if (!result) return
    try {
      const analysisId = await saveCurrentAnalysis()
      const vizElements = document.querySelectorAll('[data-viz-container]')
      const visualSnapshots: string[] = []

      for (const el of Array.from(vizElements)) {
        try {
          const dataUrl = await toPng(el as HTMLElement, {
            backgroundColor: '#ffffff',
            quality: 0.95,
            pixelRatio: 2
          })
          visualSnapshots.push(dataUrl)
        } catch (vizErr) {
          console.warn('Failed to capture visualization', vizErr)
        }
      }

      const res = await axios.post(`${API}/query/export`, {
        analysis_id: analysisId,
        query: result.query,
        answer: result.answer,
        sources: result.sources,
        visuals: visualSnapshots
      }, { responseType: 'blob' })

      const contentType = res.headers['content-type'] || 'application/pdf'
      const disposition = res.headers['content-disposition'] || ''
      const filenameMatch = disposition.match(/filename\*?=(?:UTF-8''|\")?([^;\"\n]+)/i)
      const filename = filenameMatch
        ? decodeURIComponent(filenameMatch[1].replace(/\"/g, '').trim())
        : `Research_Hub_Executive_Report_${Date.now()}.pdf`

      const pdfBlob = res.data instanceof Blob
        ? new Blob([res.data], { type: res.data.type || contentType })
        : new Blob([res.data], { type: contentType })

      if (pdfBlob.size === 0) {
        throw new Error('Received an empty PDF response.')
      }

      const resolvedFilename = filename.endsWith('.pdf') ? filename : `${filename}.pdf`
      const windowWithPicker = window as Window & {
        showSaveFilePicker?: (options?: SaveFilePickerOptions) => Promise<FileSystemFileHandle>
      }

      if (windowWithPicker.showSaveFilePicker) {
        const handle = await windowWithPicker.showSaveFilePicker({
          suggestedName: resolvedFilename,
          types: [
            {
              description: 'PDF Document',
              accept: { 'application/pdf': ['.pdf'] }
            }
          ]
        })
        const writable = await handle.createWritable()
        await writable.write(pdfBlob)
        await writable.close()
      } else {
        const url = window.URL.createObjectURL(pdfBlob)
        const link = document.createElement('a')
        link.href = url
        link.download = resolvedFilename
        link.style.display = 'none'
        document.body.appendChild(link)
        link.click()
        setTimeout(() => {
          window.URL.revokeObjectURL(url)
          link.remove()
        }, 60000)
      }

      if (analysisId) {
        const historyRes = await axios.get(`${API}/analyses/${analysisId}/reports`)
        setReportHistory(historyRes.data.reports || [])
      }
    } catch (err: any) {
      console.error('Export failed', err)
      setError('Failed to generate PDF report.')
    }
  }

  const getStatusIcon = (status: DocStatus) => {
    if (status === 'success') return <CheckCircle className="w-3 h-3 text-emerald-500" />
    if (status === 'failed') return <XCircle className="w-3 h-3 text-rose-500" />
    return <Loader2 className="w-3 h-3 text-blue-500 animate-spin" />
  }

  return (
    <div className="flex h-screen w-full bg-[#f8f9fa] text-slate-900 font-sans selection:bg-slate-900 selection:text-white overflow-hidden">
      <TooltipProvider>
        {/* ── Left Sidebar: Navigation ── */}
        <nav className="w-16 flex flex-col items-center py-6 border-r border-slate-200 bg-white shrink-0 z-30">
          <div className="mb-8 w-full flex justify-center px-1">
            <img src="/kpmg_logo.png" alt="KPMG" className="w-12 h-auto object-contain" />
          </div>

          <div className="flex flex-col gap-6 flex-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" className="w-10 h-10 rounded-xl hover:bg-slate-100">
                  <LayoutDashboard className="w-5 h-5 text-slate-500" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">Dashboard</TooltipContent>
            </Tooltip>

            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" className="w-10 h-10 rounded-xl hover:bg-slate-100">
                  <Database className="w-5 h-5 text-slate-500" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">Document Library</TooltipContent>
            </Tooltip>

            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" className="w-10 h-10 rounded-xl hover:bg-slate-100">
                  <Network className="w-5 h-5 text-slate-500" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">Knowledge Map</TooltipContent>
            </Tooltip>
          </div>

          <div className="mt-auto flex flex-col gap-6">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" className="w-10 h-10 rounded-xl hover:bg-slate-100">
                  <Settings className="w-5 h-5 text-slate-500" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right"><p>Enterprise Settings</p></TooltipContent>
            </Tooltip>
            <Avatar className="w-10 h-10 border-2 border-slate-100">
              <AvatarImage src="https://github.com/shadcn.png" />
              <AvatarFallback>AD</AvatarFallback>
            </Avatar>
          </div>
        </nav>

        {/* ── Secondary Sidebar: Documents ── */}
        <aside className={`w-72 flex flex-col border-r border-slate-200 bg-slate-50/50 shrink-0 z-20 ${activeTab === 'registry' ? 'hidden' : 'flex'}`}>
          <div className="p-6 shrink-0">
            <div className="space-y-4 mb-6">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400 font-mono">Projects</h2>
                <Button variant="ghost" size="sm" className="h-7 rounded-lg px-2 text-[10px] font-bold" onClick={handleCreateProject}>New</Button>
              </div>
              <select value={selectedProjectId} onChange={(e) => setSelectedProjectId(e.target.value)} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-[11px] font-semibold text-slate-700 outline-none">
                <option value="" disabled>{projects.length > 0 ? "Select a project" : "Create your first project"}</option>
                {projects.map(project => (
                  <option key={project.id} value={project.id}>{project.name}</option>
                ))}
              </select>
              <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Workspace Scope</p>
                <p className="mt-2 text-[11px] font-medium leading-relaxed text-slate-600">
                  {selectedProjectId ? 'Only documents linked to the active project are visible here. New uploads are attached to this project automatically.' : 'Select or create a project for scoped documents and research. Knowledge Map can still load globally.'}
                </p>
              </div>
            </div>
            <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-2 font-mono">Project Repository</h2>
            <p className="text-[10px] text-slate-400 mb-6 font-medium">{selectedProjectId ? 'This repository is scoped to the active project.' : 'Choose a project to view the repository for that workspace.'}</p>
            <div
              onDragOver={(e: DragEvent) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e: DragEvent) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files) }}
              onClick={() => fileInputRef.current?.click()}
              className={`group border-2 border-dashed rounded-2xl p-6 flex flex-col items-center gap-3 cursor-pointer transition-all bg-white hover:border-slate-300 hover:shadow-sm
                  ${dragOver ? 'border-slate-900 bg-slate-100' : 'border-slate-200'}`}
            >
              <div className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center group-hover:bg-slate-100 transition-colors">
                <Plus className="w-4 h-4 text-slate-600" />
              </div>
              <div className="text-center">
                <p className="text-[11px] font-bold text-slate-800">Add New Source</p>
              </div>
              {uploading && (
                <div className="absolute inset-0 bg-white/80 rounded-2xl flex items-center justify-center backdrop-blur-[2px]">
                  <Loader2 className="w-5 h-5 animate-spin text-slate-900" />
                </div>
              )}
            </div>
            <input ref={fileInputRef} type="file" multiple className="hidden" onChange={(e: ChangeEvent<HTMLInputElement>) => handleFiles(e.target.files)} />
          </div>

          <ScrollArea className="flex-1 px-4">
            <div className="space-y-4 pb-12">
              <div className="flex items-center justify-between px-2">
                <span className="text-[10px] font-bold text-slate-400 uppercase font-mono">Project Index</span>
                <Button variant="link" className="h-auto p-0 text-[10px] text-slate-400 hover:text-slate-900" onClick={() => setSelectedIds(new Set())}>Reset</Button>
              </div>
              <div className="space-y-1.5">
                {documents.map(doc => {
                  const isSelected = selectedIds.has(doc.id);
                  return (
                    <div
                      key={doc.id}
                      onClick={() => toggleSelect(doc.id)}
                      className={`group/item flex items-center gap-3 p-3 rounded-xl cursor-pointer transition-all flex-1
                          ${isSelected ? 'bg-white shadow-[0px_2px_8px_rgba(0,0,0,0.04)] border border-slate-200' : 'hover:bg-slate-100/50'}`}
                    >
                      <Checkbox checked={isSelected} className="rounded-md border-slate-300 data-[state=checked]:bg-slate-900" />
                      <div className="min-w-0 flex-1">
                        <p className={`text-[11px] font-semibold truncate ${isSelected ? 'text-slate-900' : 'text-slate-500'}`}>{doc.filename}</p>
                        <div className="flex items-center gap-2 mt-0.5">
                          {getStatusIcon(doc.status)}
                          <span className="text-[9px] font-bold text-slate-400 uppercase">{doc.status === 'processing' ? (doc.sub_status || 'analyzing') : `${doc.chunks_indexed || 0} chunks`}</span>
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="w-7 h-7 rounded-lg opacity-0 group-hover/item:opacity-100 hover:bg-rose-50 hover:text-rose-500 transition-all text-slate-400"
                        onClick={(e) => handleDeleteDocument(e, doc.id)}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  )
                })}
              </div>

              <div className="space-y-4 border-t border-slate-100 pt-4">
                <div>
                  <p className="px-2 text-[10px] font-bold uppercase text-slate-400 font-mono mb-2">Saved Analyses</p>
                  <div className="space-y-2">
                    {savedAnalyses.length === 0 ? (
                      <p className="px-2 text-[11px] text-slate-400">No saved analyses yet.</p>
                    ) : savedAnalyses.slice(0, 6).map((analysis, index) => (
                      <button key={analysis.analysis_id || `${analysis.query}-${index}`} onClick={() => handleLoadAnalysis(analysis)} className="w-full rounded-xl border border-slate-100 bg-white px-3 py-2 text-left hover:border-slate-200 hover:bg-slate-50 transition-colors">
                        <p className="text-[11px] font-bold text-slate-900 truncate">{analysis.query}</p>
                        <p className="text-[9px] font-semibold text-slate-500 mt-1">{analysis.confidence_score ? `${Math.round(analysis.confidence_score * 100)}% confidence` : 'Saved analysis'}</p>
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="px-2 text-[10px] font-bold uppercase text-slate-400 font-mono mb-2">Report History</p>
                  <div className="space-y-2">
                    {reportHistory.length === 0 ? (
                      <p className="px-2 text-[11px] text-slate-400">No saved reports yet.</p>
                    ) : reportHistory.slice(0, 6).map((report) => (
                      <button key={report.id} onClick={() => handleDownloadSavedReport(report.id)} className="w-full rounded-xl border border-slate-100 bg-white px-3 py-2 text-left hover:border-slate-200 hover:bg-slate-50 transition-colors">
                        <p className="text-[11px] font-bold text-slate-900 truncate">{report.filename}</p>
                        <p className="text-[9px] font-semibold text-slate-500 mt-1">{new Date(report.created_at).toLocaleString()}</p>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </ScrollArea>
        </aside>

        {/* ── Main Layout: Workspace & Intelligence ── */}
        <main className="flex-1 flex overflow-hidden">
          {/* Workspace Side */}
          <div className="flex-1 flex flex-col bg-white overflow-hidden relative">
            {/* Conditionally hide standard header for Registry for full-screen immersion */}
            <header className={`h-16 border-b border-slate-100 flex items-center justify-between px-10 shrink-0 ${activeTab === 'registry' ? 'hidden' : ''}`}>
              <div className="flex items-center gap-4">
                <Badge variant="outline" className="rounded-lg border-slate-200 text-slate-500 font-mono text-[9px] tracking-widest px-2 py-0.5">V2.4.0 STABLE</Badge>
                <Separator orientation="vertical" className="h-4 bg-slate-200" />
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Context: <span className="text-slate-900">{selectedIds.size > 0 ? `${selectedIds.size} Selective` : 'Full Knowledge Base'}</span></p>
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Project: <span className="text-slate-900">{activeProject?.name || 'Select Project'}</span></p>
              </div>
              <div className="flex items-center gap-3">
                <Button variant="ghost" size="sm" onClick={saveCurrentAnalysis} disabled={!result || savingAnalysis} className="text-[10px] font-bold uppercase text-slate-400 hover:text-slate-900 transition-colors disabled:opacity-50">
                  {savingAnalysis ? 'Saving...' : 'Save Analysis'}
                </Button>
                <Button
                  variant="default"
                  size="sm"
                  disabled={!result}
                  onClick={handleExportReport}
                  className="bg-slate-900 text-white rounded-lg px-4 h-8 text-[11px] font-bold shadow-lg shadow-slate-200 disabled:opacity-50"
                >
                  Export Report
                </Button>
              </div>
            </header>

            <Tabs
              value={activeTab}
              onValueChange={(val: string) => {
                setActiveTab(val);
                if (val === 'map') fetchGraph();
              }}
              className="flex-1 flex flex-col overflow-hidden min-h-0"
            >
              {/* Global Tab List (Hidden when Registry is Active to avoid double nav) */}
              <div className={`absolute top-4 left-10 z-20 shrink-0 ${activeTab === 'registry' ? 'hidden' : ''}`}>
                <TabsList className="bg-white/80 backdrop-blur-md border border-slate-200 p-1 rounded-xl h-10 w-fit shadow-sm">
                  <TabsTrigger value="research" className="rounded-lg px-6 text-[11px] font-bold uppercase tracking-widest data-[state=active]:bg-white data-[state=active]:shadow-sm">Research Chat</TabsTrigger>
                  <TabsTrigger value="map" className="rounded-lg px-6 text-[11px] font-bold uppercase tracking-widest data-[state=active]:bg-white data-[state=active]:shadow-sm">Knowledge Map</TabsTrigger>
                  <TabsTrigger value="eligibility" className="rounded-lg px-6 text-[11px] font-bold uppercase tracking-widest data-[state=active]:bg-white data-[state=active]:shadow-sm">Eligibility</TabsTrigger>
                  <TabsTrigger value="registry" className="rounded-lg px-6 text-[11px] font-bold uppercase tracking-widest data-[state=active]:bg-white data-[state=active]:shadow-sm">🏛 Social Registry</TabsTrigger>
                </TabsList>
              </div>
              {/* ── Social Registry Dashboard Tab ── */}
              <TabsContent value="registry" className="flex-1 flex flex-col min-h-0 overflow-hidden m-0 p-0 border-none outline-none bg-[#fcfdfe] data-[state=inactive]:hidden data-[state=active]:flex">
                {activeTab === 'registry' && (
                  <UsrDashboard
                    API={API}
                    navArea={
                      <TabsList className="bg-slate-100/50 border border-slate-200 p-1 rounded-xl h-10 w-fit">
                        <TabsTrigger value="research" className="rounded-lg px-6 text-[11px] font-bold uppercase tracking-widest data-[state=active]:bg-white data-[state=active]:shadow-sm">Research Chat</TabsTrigger>
                        <TabsTrigger value="map" className="rounded-lg px-6 text-[11px] font-bold uppercase tracking-widest data-[state=active]:bg-white data-[state=active]:shadow-sm">Knowledge Map</TabsTrigger>
                        <TabsTrigger value="eligibility" className="rounded-lg px-6 text-[11px] font-bold uppercase tracking-widest data-[state=active]:bg-white data-[state=active]:shadow-sm">Eligibility</TabsTrigger>
                        <TabsTrigger value="registry" className="rounded-lg px-6 text-[11px] font-bold uppercase tracking-widest data-[state=active]:bg-white data-[state=active]:shadow-sm">Social Registry</TabsTrigger>
                      </TabsList>
                    }
                  />
                )}
              </TabsContent>

              <TabsContent value="eligibility" className="flex-1 flex flex-col min-h-0 overflow-hidden m-0 p-0 border-none outline-none data-[state=inactive]:hidden data-[state=active]:flex">
                <EligibilityStudio API={API} />
              </TabsContent>

              <TabsContent value="research" className="flex-1 flex flex-col overflow-hidden min-h-0 mt-0 m-0 p-0 border-none outline-none data-[state=inactive]:hidden data-[state=active]:flex">
                <ScrollArea className="flex-1 h-full">
                  <div className="max-w-4xl mx-auto px-10 pt-14 pb-32 space-y-12">
                    {/* Hero Area */}
                    {!result && !querying && (
                      <div className="py-20 flex flex-col items-center justify-center opacity-30">
                        <div className="w-16 h-16 rounded-3xl bg-slate-50 border border-slate-100 flex items-center justify-center mb-6">
                          <Zap className="w-8 h-8 text-slate-400 fill-slate-400" />
                        </div>
                        <h1 className="text-xl font-bold text-slate-900 mb-2">Internal Research Engine</h1>
                        <p className="text-sm text-slate-500 text-center max-w-sm">Select documents in the sidebar and initiate a semantic inquiry below to begin deep synthesis.</p>
                      </div>
                    )}

                    {error && (
                      <Card className="border-rose-100 bg-rose-50/50 rounded-2xl p-6 flex gap-4 animate-in fade-in slide-in-from-top-2">
                        <XCircle className="w-5 h-5 text-rose-500 shrink-0" />
                        <div className="space-y-1">
                          <p className="text-sm font-bold text-rose-900">Analysis Error</p>
                          <p className="text-xs text-rose-700 leading-relaxed font-medium">{error}</p>
                        </div>
                      </Card>
                    )}

                    {result && (
                      <div className="space-y-12 animate-in fade-in duration-700">
                        <div className="space-y-6">
                          <div className="flex flex-wrap gap-3">
                            <Card className="rounded-2xl border-slate-100 px-4 py-3 bg-slate-50/70">
                              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Confidence</p>
                              <p className="text-lg font-bold text-slate-900">{result.confidence_score ? `${Math.round(result.confidence_score * 100)}%` : 'N/A'}</p>
                            </Card>
                            <Card className="rounded-2xl border-slate-100 px-4 py-3 bg-slate-50/70">
                              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Citation Coverage</p>
                              <p className="text-lg font-bold text-slate-900">{result.citation_coverage ? `${Math.round(result.citation_coverage * 100)}%` : 'N/A'}</p>
                            </Card>
                            <Card className="rounded-2xl border-slate-100 px-4 py-3 bg-slate-50/70">
                              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Graph</p>
                              <p className="text-lg font-bold text-slate-900">{result.graph_enrichment_used ? 'Enabled' : 'Not Used'}</p>
                            </Card>
                          </div>
                          {result.weak_claims && result.weak_claims.length > 0 && (
                            <Card className="rounded-2xl border-amber-100 bg-amber-50/80 p-4">
                              <p className="text-[10px] font-bold uppercase tracking-widest text-amber-700 mb-2">Evidence Warnings</p>
                              <div className="space-y-1">
                                {result.weak_claims.map((claim, index) => (
                                  <p key={`${claim}-${index}`} className="text-sm font-medium text-amber-900">{claim}</p>
                                ))}
                              </div>
                            </Card>
                          )}
                          <p className="text-[10px] font-bold uppercase tracking-[0.4em] text-slate-300">Analysis Output</p>
                          <div className="prose prose-slate max-w-none text-[15px] leading-[1.8] text-slate-800 font-medium border-l-4 border-slate-900 pl-8 transition-all hover:bg-slate-50/50 py-2 rounded-r-2xl
                             prose-headings:text-slate-900 prose-headings:font-bold prose-h1:text-xl prose-h2:text-lg prose-h3:text-base
                             prose-p:mb-4 prose-ul:list-disc prose-ul:pl-6 prose-li:mb-1
                             prose-table:border prose-table:border-slate-200 prose-th:bg-slate-50 prose-th:p-2 prose-td:p-2 prose-td:border-t">
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              components={{
                                a: ({ node, ...props }) => {
                                  const isSource = props.href?.startsWith('#source-');
                                  if (isSource && result) {
                                    const index = parseInt(props.href!.split('-')[1]) - 1;
                                    const source = result.sources[index];
                                    if (source) {
                                      return (
                                        <TooltipProvider>
                                          <Tooltip>
                                            <TooltipTrigger asChild>
                                              <span
                                                onClick={() => setSelectedSource(source)}
                                                className="inline-flex items-center justify-center bg-slate-100 text-slate-900 px-1.5 py-0 rounded font-bold text-[10px] cursor-pointer hover:bg-slate-900 hover:text-white transition-colors mx-0.5"
                                              >
                                                {props.children}
                                              </span>
                                            </TooltipTrigger>
                                            <TooltipContent className="bg-slate-900 text-white border-none p-3 rounded-xl shadow-2xl">
                                              <div className="space-y-1">
                                                <p className="text-[10px] font-bold truncate max-w-[200px]">{source.filename}</p>
                                                <p className="text-[9px] text-slate-400 font-medium uppercase tracking-tighter">Verified Grounding | Page {source.page || 'N/A'}</p>
                                              </div>
                                            </TooltipContent>
                                          </Tooltip>
                                        </TooltipProvider>
                                      );
                                    }
                                  }
                                  return <a {...props} className="text-slate-900 underline decoration-slate-200 underline-offset-4 hover:decoration-slate-900 transition-all font-bold" />;
                                },
                                code: ({ node, className, children, ...props }) => {
                                  const match = /language-(\w+)/.exec(className || '');
                                  const lang = match ? match[1] : '';

                                  if (lang === 'json') {
                                    try {
                                      const raw = String(children).trim();
                                      const cleanJson = raw.replace(':chart', '').trim();
                                      const config = JSON.parse(cleanJson);

                                      if (config && typeof config === 'object' && config.type && Array.isArray(config.data)) {
                                        return <DynamicChart config={config} />;
                                      }
                                    } catch (e) {
                                      return <code className={className} {...props}>{children}</code>;
                                    }
                                  }

                                  return <code className={className} {...props}>{children}</code>;
                                }
                              }}
                            >
                              {result.answer}
                            </ReactMarkdown>
                          </div>
                        </div>

                        <div className="space-y-6">
                          <p className="text-[10px] font-bold uppercase tracking-[0.4em] text-slate-300">Cited Evidence Fragments</p>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {result.sources.map((src: Source, i: number) => (
                              <Card
                                key={i}
                                onClick={() => setSelectedSource(src)}
                                className={`p-5 rounded-2xl cursor-pointer transition-all border shadow-none hover:shadow-md
                                    ${selectedSource === src ? 'border-slate-900 bg-white ring-1 ring-slate-900 translate-y-[-2px]' : 'border-slate-100 bg-slate-50/10 hover:border-slate-300 hover:bg-white'}`}
                              >
                                <div className="flex items-center justify-between mb-3">
                                  <Badge variant="secondary" className="bg-slate-100 text-slate-500 rounded-lg px-2 h-5 text-[9px] hover:bg-slate-200 border-none">{`#${i + 1}`}</Badge>
                                  <span className="text-[9px] font-bold text-slate-400">{(src.score * 100).toFixed(0)}% Match</span>
                                </div>
                                <p className="text-[11px] font-bold text-slate-900 truncate mb-2">{src.filename}</p>
                                <div className="flex items-center gap-1.5 opacity-40">
                                  <FileText className="w-3 h-3" />
                                  <span className="text-[9px] font-bold uppercase tracking-tighter">Page {src.page || 'N/A'}</span>
                                </div>
                              </Card>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </ScrollArea>

                {/* Fixed Query Bar Area */}
                <div className="absolute bottom-10 left-10 right-10 z-20">
                  <div className="max-w-4xl mx-auto relative cursor-text group" onClick={() => document.getElementById('query-input')?.focus()}>
                    <div className="absolute inset-x-0 bottom-[-8px] h-full bg-slate-900/5 blur-2xl rounded-3xl" />
                    <div className="relative bg-white border border-slate-200 rounded-3xl p-1.5 flex gap-0 shadow-[0px_20px_50px_rgba(0,0,0,0.06)] group-hover:border-slate-400 transition-colors">
                      <Input
                        id="query-input"
                        placeholder="Synthesize information about..."
                        value={query}
                        autoComplete="off"
                        onChange={(e: ChangeEvent<HTMLInputElement>) => setQuery(e.target.value)}
                        onKeyDown={(e: React.KeyboardEvent<HTMLInputElement>) => { if (e.key === 'Enter') handleQuery() }}
                        className="flex-1 bg-transparent border-none shadow-none text-base p-6 h-14 placeholder:text-slate-300 text-slate-800 font-medium focus-visible:ring-0"
                      />
                      <Button
                        onClick={handleQuery}
                        disabled={querying || !query.trim()}
                        className="bg-slate-900 hover:bg-slate-800 text-white w-14 h-14 rounded-2xl flex items-center justify-center p-0 shrink-0 transition-transform active:scale-95"
                      >
                        {querying ? <Loader2 className="w-6 h-6 animate-spin" /> : <Search className="w-6 h-6" />}
                      </Button>
                    </div>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="map" className="flex-1 relative overflow-hidden min-h-0 mt-0 m-0 p-0 outline-none border-none bg-white h-full min-h-[700px] data-[state=inactive]:hidden data-[state=active]:block">
                {loadingGraph ? (
                  <div className="flex flex-col items-center justify-center h-full gap-6">
                    <div className="relative">
                      <Loader2 className="w-16 h-16 text-slate-900 animate-spin" />
                      <Network className="absolute inset-0 m-auto w-6 h-6 text-slate-900" />
                    </div>
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.4em] animate-pulse">Mapping Relational Intelligence...</p>
                  </div>
                ) : (
                  <div ref={mapContainerRef} className="absolute inset-0 w-full h-full cursor-grab active:cursor-grabbing">
                    <ForceGraph2D
                      graphData={graphData}
                      width={Math.max(mapDimensions.width, 900)}
                      height={Math.max(mapDimensions.height, 620)}
                      nodeLabel={(node: any) => `${node.type}: ${node.label}`}
                      linkLabel={(link: any) => `${link.label}: ${link.description || ''}`}
                      nodeColor={(node: any) => resolveEntityColor(node.type || 'Default', node.label)}
                      nodeRelSize={8}
                      nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
                        const label = node.label;
                        const fontSize = 14 / globalScale;
                        const category = resolveEntityCategory(node.type || 'Default', label);
                        const color = ENTITY_COLORS[category] || ENTITY_COLORS.Default;
                        const isFraud = category === 'FraudFlag';

                        ctx.font = `bold ${fontSize}px Inter`;
                        ctx.textAlign = 'center';
                        ctx.textBaseline = 'middle';

                        // Immersive node glow - amplified for fraud
                        ctx.shadowColor = color;
                        ctx.shadowBlur = (isFraud ? 30 : 10) / globalScale;

                        ctx.fillStyle = color;
                        ctx.beginPath();
                        const radius = (isFraud ? 12 : 7) / globalScale;
                        ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
                        ctx.fill();

                        ctx.shadowBlur = 0; // Reset shadow

                        if (globalScale > 0.6) {
                          ctx.fillStyle = '#1e293b';
                          const offset = (isFraud ? 22 : 16) / globalScale;
                          ctx.fillText(label, (node.x as number), (node.y as number) + offset);
                        }
                      }}
                      linkDirectionalParticles={2}
                      linkDirectionalParticleSpeed={0.005}
                      linkColor={() => '#cbd5e1'}
                      linkWidth={1.5}
                      backgroundColor="#ffffff"
                      cooldownTicks={100}
                    />

                    {graphData.nodes.length === 0 && (
                      <div className="absolute inset-0 z-20 flex items-center justify-center pointer-events-none">
                        <div className="pointer-events-auto max-w-lg rounded-3xl border border-slate-200 bg-white/95 p-8 shadow-2xl text-center">
                          <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Knowledge Map</p>
                          <h3 className="mt-2 text-lg font-bold text-slate-900">No graph nodes available yet</h3>
                          <p className="mt-2 text-sm text-slate-600">
                            This usually means the selected project has no linked documents or graph sync has not populated Neo4j yet.
                          </p>
                          <div className="mt-5 flex justify-center gap-2">
                            <Button variant="secondary" size="sm" className="rounded-xl" onClick={() => fetchGraph()}>
                              Retry Load
                            </Button>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Immersive Map Controls Overlay */}
                    <div className="absolute top-8 right-8 flex flex-col gap-2 z-10">
                      <Button variant="secondary" size="icon" className="bg-white/90 backdrop-blur shadow-2xl rounded-xl border-slate-100 h-10 w-10 hover:bg-white" onClick={() => fetchGraph()}>
                        <Network className="w-4 h-4 text-slate-900" />
                      </Button>
                    </div>

                    <div className="absolute bottom-10 right-10 bg-white/90 backdrop-blur border border-slate-100 rounded-[32px] p-10 shadow-[0px_30px_90px_rgba(0,0,0,0.12)] space-y-4 animate-in slide-in-from-bottom-8 duration-1000 z-10 w-80">
                      <h4 className="text-[10px] font-bold uppercase tracking-[0.4em] text-slate-400 mb-8 border-b border-slate-50 pb-4">Intelligence Legend</h4>
                      <div className="grid grid-cols-2 gap-x-6 gap-y-5">
                        {DATABASE_ENTITY_LEGEND.map((type) => (
                          <div key={type} className="flex items-center gap-4">
                            <div className="w-4 h-4 rounded-full shadow-inner ring-4 ring-white" style={{ backgroundColor: ENTITY_COLORS[type] }} />
                            <span className="text-[10px] font-bold text-slate-600 uppercase tracking-tighter whitespace-nowrap">{type}</span>
                          </div>
                        ))}
                      </div>

                      <div className="mt-8 pt-6 border-t border-slate-100 space-y-4">
                        <h5 className="text-[10px] font-bold uppercase tracking-widest text-slate-800">Fraud Typology Guide</h5>
                        <div className="flex flex-col gap-4 text-[11px] text-slate-500">
                          <div className="flex gap-3 items-start">
                            <span className="font-black text-rose-500 shrink-0 w-14 uppercase tracking-tighter">Fraud 1</span>
                            <span className="leading-snug"><strong className="text-slate-800">Ghost Flags:</strong> Invalid or suspicious beneficiary profiles flagged from citizen attributes.</span>
                          </div>
                          <div className="flex gap-3 items-start">
                            <span className="font-black text-amber-500 shrink-0 w-14 uppercase tracking-tighter">Fraud 2</span>
                            <span className="leading-snug"><strong className="text-slate-800">Identity Duplicates:</strong> Same person linked via duplicate identity patterns (B/I rules).</span>
                          </div>
                          <div className="flex gap-3 items-start">
                            <span className="font-black text-violet-500 shrink-0 w-14 uppercase tracking-tighter">Fraud 3</span>
                            <span className="leading-snug"><strong className="text-slate-800">Systemic Anomalies:</strong> Operator/household/scheme-level risk clusters requiring field audit.</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </TabsContent>


            </Tabs>

          </div>

          {/* Intelligence Side Pane (Conditional) */}
          <aside className={`w-80 border-l border-slate-200 bg-white transition-all transform duration-500 flex flex-col overflow-hidden shrink-0
            ${activeTab === 'registry' ? 'hidden' : (selectedSource ? 'translate-x-0' : 'translate-x-full absolute right-0 h-full')}`}>
            <header className="h-16 border-b border-slate-100 flex items-center justify-between px-6 shrink-0">
              <h3 className="text-[10px] font-bold uppercase tracking-widest text-slate-900">Intelligence Pane</h3>
              <Button variant="ghost" size="icon" className="w-8 h-8 rounded-lg" onClick={() => setSelectedSource(null)}>
                <XCircle className="w-4 h-4 text-slate-400" />
              </Button>
            </header>

            {selectedSource && (
              <ScrollArea className="flex-1">
                <div className="p-8 space-y-10 animate-in fade-in slide-in-from-right-4 duration-500">
                  <div className="sticky top-0 z-10 bg-white pb-6 pt-0 space-y-4 border-b border-slate-50">
                    <Badge variant="outline" className="text-slate-400 uppercase tracking-widest text-[8px] font-bold px-1.5 py-0 border-slate-200">Metadata Analysis</Badge>
                    <h2 className="text-base font-bold text-slate-900 leading-tight">{selectedSource.filename}</h2>
                    <div className="flex items-center gap-6">
                      <div className="flex flex-col">
                        <span className="text-[9px] font-bold text-slate-300 uppercase underline decoration-slate-100 underline-offset-4 mb-2">Confidence</span>
                        <span className="text-sm font-bold text-slate-900">{(selectedSource.score * 100).toFixed(1)}%</span>
                      </div>
                      <div className="flex flex-col">
                        <span className="text-[9px] font-bold text-slate-300 uppercase underline decoration-slate-100 underline-offset-4 mb-2">Reference</span>
                        <span className="text-sm font-bold text-slate-900">Page {selectedSource.page || 'N/A'}</span>
                      </div>
                    </div>
                  </div>

                  <Separator className="bg-slate-100" />

                  <div className="space-y-4">
                    <div className="flex items-center gap-2">
                      <Info className="w-3.5 h-3.5 text-slate-400" />
                      <span className="text-[10px] font-bold text-slate-300 uppercase tracking-wider">Semantic Grounding</span>
                    </div>
                    <blockquote className="text-[13px] leading-[1.8] text-slate-500 italic font-medium bg-slate-50/50 p-6 rounded-2xl border-l border-slate-200">
                      "{selectedSource.snippet}"
                    </blockquote>
                    <Button variant="secondary" className="w-full h-10 bg-slate-50 text-slate-900 border border-slate-200 hover:bg-slate-100 rounded-xl text-xs font-bold gap-2">
                      <ExternalLink className="w-3.5 h-3.5" />
                      Full Original Document
                    </Button>
                  </div>
                </div>
              </ScrollArea>
            )}
          </aside>
        </main>
      </TooltipProvider>
    </div>
  )
}



























