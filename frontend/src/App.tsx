import React, { useState, useRef, useEffect, ChangeEvent } from 'react'
import {
  Search,
  Loader2,
  XCircle,
  Zap,
  Network,
  FileText,
  Settings,
  Info,
  ExternalLink,
  Plus,
  MessageSquareText,
  CheckSquare,
  Landmark,
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

// Unified parser to render text content by converting <br> tags into <br /> elements
// and literal source references (e.g. 【Source X】 or [Source X]) into interactive badges.
const renderTextContent = (text: string, sources: Source[], setSelectedSource: (src: any) => void): React.ReactNode => {
  if (text.toLowerCase().includes('<br')) {
    const parts = text.split(/<br\s*\/?>/gi);
    return (
      <>
        {parts.map((part, index) => (
          <React.Fragment key={index}>
            {renderTextContent(part, sources, setSelectedSource)}
            {index < parts.length - 1 && <br />}
          </React.Fragment>
        ))}
      </>
    );
  }

  const citationRegex = /(?:【|\[)Source\s*(\d+)(?:】|\])/gi;
  if (citationRegex.test(text)) {
    citationRegex.lastIndex = 0;
    const elements: React.ReactNode[] = [];
    let match;
    let lastIndex = 0;

    while ((match = citationRegex.exec(text)) !== null) {
      const matchIndex = match.index;
      const citationText = match[0];
      const sourceNum = parseInt(match[1], 10);
      
      if (matchIndex > lastIndex) {
        elements.push(text.substring(lastIndex, matchIndex));
      }

      const sourceIndex = sourceNum - 1;
      const source = sources && sources[sourceIndex];
      if (source) {
        const baseName = source.filename.split(/[/\\]/).pop() || source.filename;
        const cleanName = baseName.replace(/\.pdf$/i, '');
        const displayName = cleanName.length > 20 ? cleanName.substring(0, 17) + '...' : cleanName;
        const sourceLabel = source.page ? `${displayName} (p. ${source.page})` : displayName;

        elements.push(
          <TooltipProvider key={`citation-${matchIndex}`}>
            <Tooltip>
              <TooltipTrigger asChild>
                <span
                  onClick={() => setSelectedSource(source)}
                  className="inline-flex items-center gap-1 bg-slate-100 text-slate-900 px-2 py-0.5 rounded-md font-bold text-[10px] cursor-pointer hover:bg-slate-900 hover:text-white transition-colors mx-0.5 align-middle font-sans"
                >
                  <FileText className="w-2.5 h-2.5 shrink-0 text-slate-500" />
                  {sourceLabel}
                </span>
              </TooltipTrigger>
              <TooltipContent className="bg-slate-900 text-white border-none p-3 rounded-xl shadow-2xl font-sans">
                <div className="space-y-1">
                  <p className="text-[10px] font-bold truncate max-w-[200px]">{source.filename}</p>
                  <p className="text-[9px] text-slate-400 font-medium uppercase tracking-tighter">Verified Grounding | Page {source.page || 'N/A'}</p>
                </div>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        );
      } else {
        elements.push(citationText);
      }

      lastIndex = citationRegex.lastIndex;
    }

    if (lastIndex < text.length) {
      elements.push(text.substring(lastIndex));
    }

    return <>{elements}</>;
  }

  return text;
};

const renderWithLineBreaksAndCitations = (content: any, sources: Source[], setSelectedSource: (src: any) => void): any => {
  if (typeof content === 'string') {
    return renderTextContent(content, sources, setSelectedSource);
  }
  if (Array.isArray(content)) {
    return content.map((child, index) => (
      <React.Fragment key={index}>
        {renderWithLineBreaksAndCitations(child, sources, setSelectedSource)}
      </React.Fragment>
    ));
  }
  if (React.isValidElement(content)) {
    const element = content as React.ReactElement<any>;
    if (element.props && element.props.children) {
      return React.cloneElement(element, {
        children: renderWithLineBreaksAndCitations(element.props.children, sources, setSelectedSource)
      } as any);
    }
  }
  return content;
};

interface SavedReport {
  id: string
  analysis_id: string
  filename: string
  format: string
  created_at: string
}

interface SchemeOption {
  id: string
  name: string
  citizen_count: number
  enrollment_count: number
}

interface GraphNode {
  id: string
  label: string
  type: string
  x?: number
  y?: number
  fx?: number
  fy?: number
  [key: string]: any
}

interface GraphLink {
  source: string | { id: string }
  target: string | { id: string }
  label: string
  description?: string
}

interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
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

const getLinkNodeId = (value: string | { id: string }) => (
  typeof value === 'string' ? value : value?.id
)

const applySchemeFocusedLayout = (
  nodes: GraphNode[],
  links: GraphLink[],
  activeSchemeId: string
): GraphNode[] => {
  if (!activeSchemeId) {
    // If no scheme selected, unfreeze all nodes to allow organic global layout
    nodes.forEach(node => {
      delete node.fx;
      delete node.fy;
    });
    return nodes;
  }

  const schemeNode = nodes.find((node) => node.id === activeSchemeId)
  if (!schemeNode) return nodes

  const citizenIds = new Set(
    links
      .filter((link) => link.label === 'ENROLLED_IN' && getLinkNodeId(link.target) === activeSchemeId)
      .map((link) => getLinkNodeId(link.source))
      .filter(Boolean) as string[]
  )

  const contextualIds = new Set<string>()
  links.forEach((link) => {
    const sourceId = getLinkNodeId(link.source)
    const targetId = getLinkNodeId(link.target)
    if (citizenIds.has(sourceId) && targetId !== activeSchemeId) contextualIds.add(targetId)
    if (citizenIds.has(targetId) && sourceId !== activeSchemeId) contextualIds.add(sourceId)
  })

  // Instead of a rigid ring, we spread them in an organic disk/spiral to give them breathing room
  const placeInSpiral = (
    groupNodes: GraphNode[],
    baseRadius: number,
  ) => {
    groupNodes.forEach((node, index) => {
      // Increase radius organically for large groups to prevent overlap
      const radius = baseRadius + (index * 0.4); 
      const angle = index * 2.4; // Golden ratio spread
      
      // Set initial positions but remove rigid fx/fy constraints 
      // so D3 force simulation can elegantly untangle them
      node.x = Math.cos(angle) * radius
      node.y = Math.sin(angle) * radius
      delete node.fx
      delete node.fy
    })
  }

  // Anchor the scheme tightly in the center
  schemeNode.fx = 0
  schemeNode.fy = 0
  schemeNode.x = 0
  schemeNode.y = 0

  const citizenNodes = nodes.filter((node) => citizenIds.has(node.id))
  const contextNodes = nodes.filter(
    (node) => node.id !== activeSchemeId && !citizenIds.has(node.id) && contextualIds.has(node.id)
  )
  const remainingNodes = nodes.filter(
    (node) => node.id !== activeSchemeId && !citizenIds.has(node.id) && !contextualIds.has(node.id)
  )

  placeInSpiral(citizenNodes, 120)
  placeInSpiral(contextNodes, 350)
  placeInSpiral(remainingNodes, 550)

  return nodes
}

export default function App() {
  const [, setDocuments] = useState<Document[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState<string>('')
  const [, setSavedAnalyses] = useState<QueryResult[]>([])
  const [, setReportHistory] = useState<SavedReport[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [query, setQuery] = useState('');
  const [activeTab, setActiveTab] = useState('research');
  const [querying, setQuerying] = useState(false);
  const [savingAnalysis, setSavingAnalysis] = useState(false)
  const [result, setResult] = useState<QueryResult | null>(null)
  const [selectedSource, setSelectedSource] = useState<Source | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [chatHistory, setChatHistory] = useState<{role: string, content: string}[]>([])

  // Graph States
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], links: [] })
  const [schemeGraphId, setSchemeGraphId] = useState('')
  const [schemeSearch, setSchemeSearch] = useState('')
  const [schemeOptions, setSchemeOptions] = useState<SchemeOption[]>([])
  const [loadingSchemes, setLoadingSchemes] = useState(false)
  const [loadingGraph, setLoadingGraph] = useState(false)
  const [projectsReady, setProjectsReady] = useState(false)

  const mapContainerRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<any>(null)
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

  const pollStatus = async (id: string) => {
    const interval = setInterval(async () => {
      try {
        const res = await axios.get(`${API}/documents/${id}`)
        const doc = res.data
        setDocuments(prev => prev.map(d => (d.id === id || (d as any).document_id === id) ? { ...d, ...doc } : d))
        if (doc.status === 'success' || doc.status === 'failed') clearInterval(interval)
      } catch {
        clearInterval(interval)
      }
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
        document_ids: selectedIds.size > 0 ? Array.from(selectedIds) : null,
        history: chatHistory.length > 0 ? chatHistory : null
      }
      const res = await axios.post(`${API}/query/`, payload)
      setResult({ ...res.data, project_id: selectedProjectId || null })
      setChatHistory(prev => [...prev, { role: 'user', content: query }, { role: 'assistant', content: res.data.answer }])
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Query failed.')
    } finally {
      setQuerying(false)
    }
  }

  const fetchGraph = async (schemeOverride?: string | null) => {
    if (graphRequestInFlightRef.current) return

    graphRequestInFlightRef.current = true
    setLoadingGraph(true)
    setError(null)
    try {
      const normalizedSchemeId = (schemeOverride ?? schemeGraphId).trim().toUpperCase()
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
      if (normalizedSchemeId) {
        params.set('scheme_id', normalizedSchemeId)
      }

      const queryString = params.toString()
      let res = await axios.get(`${API}/documents/graph/all${queryString ? `?${queryString}` : ''}`)

      // If project-scoped graph is empty, retry unscoped so USR/global graph still appears.
      if ((res.data?.nodes || []).length === 0 && selectedProjectId && selectedIds.size === 0) {
        const fallbackParams = new URLSearchParams()
        if (query.trim()) {
          fallbackParams.set('q', query.trim())
        }
        if (normalizedSchemeId) {
          fallbackParams.set('scheme_id', normalizedSchemeId)
        }
        const fallbackQuery = fallbackParams.toString()
        res = await axios.get(`${API}/documents/graph/all${fallbackQuery ? `?${fallbackQuery}` : ''}`)
      }

      const normalizedNodes = (res.data?.nodes || []).map((node: any) => ({
        ...node,
        type: resolveEntityCategory(node?.type || '', node?.label || node?.id || '')
      }))
      const laidOutNodes = applySchemeFocusedLayout(
        normalizedNodes,
        res.data?.links || [],
        normalizedSchemeId
      )
      setGraphData({
        nodes: laidOutNodes,
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

  const fetchSchemeOptions = async () => {
    setLoadingSchemes(true)
    try {
      const res = await axios.get(`${API}/documents/graph/schemes`)
      setSchemeOptions(res.data?.schemes || [])
    } catch (err) {
      console.error('Failed to load scheme catalog', err)
      setSchemeOptions([])
    } finally {
      setLoadingSchemes(false)
    }
  }

  const handleLoadSchemeGraph = async (schemeId: string) => {
    const normalizedSchemeId = schemeId.trim().toUpperCase()
    setSchemeGraphId(normalizedSchemeId)
    await fetchGraph(normalizedSchemeId)
  }

  const handleResetSchemeGraph = async () => {
    setSchemeGraphId('')
    await fetchGraph('')
  }


  useEffect(() => {
    if (activeTab !== 'map' || !projectsReady) return
    fetchGraph()
    fetchSchemeOptions()
  }, [activeTab, projectsReady, selectedProjectId])

  useEffect(() => {
    if (!graphRef.current || activeTab !== 'map') return

    const timer = window.setTimeout(() => {
      if (schemeGraphId) {
        graphRef.current.centerAt(0, 0, 800)
        graphRef.current.zoom(1.6, 800)
      } else {
        graphRef.current.zoomToFit(800, 80)
      }
    }, 150)

    return () => window.clearTimeout(timer)
  }, [graphData, schemeGraphId, activeTab])

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

  const filteredSchemeOptions = schemeOptions.filter((scheme) => {
    const search = schemeSearch.trim().toLowerCase()
    if (!search) return true
    return (
      scheme.id.toLowerCase().includes(search)
      || scheme.name.toLowerCase().includes(search)
    )
  })

  return (
    <div className="flex h-screen w-full bg-[#f8f9fa] text-slate-900 font-sans selection:bg-slate-900 selection:text-white overflow-hidden">
      <TooltipProvider>
        <Tabs
          value={activeTab}
          onValueChange={(val: string) => {
            setActiveTab(val);
            if (val === 'map') fetchGraph();
          }}
          className="flex h-screen w-full overflow-hidden flex-1"
        >
          {/* ── Left Sidebar: Navigation ── */}
          <nav className="w-48 flex flex-col py-6 border-r border-slate-200 bg-white shrink-0 z-30 px-5">
          <div className="mb-10 w-full flex justify-center">
            <img src="/kpmg_logo.png" alt="KPMG" className="w-20 h-auto object-contain" />
          </div>

          <div className="w-full mb-6">
            <div className="flex items-center justify-between mb-3 px-1">
              <h2 className="text-[10px] font-bold uppercase tracking-widest text-slate-400 font-mono">Workspace</h2>
              <button onClick={handleCreateProject} className="text-slate-400 hover:text-slate-900 transition-colors" title="New Project">
                <Plus className="w-3.5 h-3.5" />
              </button>
            </div>
            <select value={selectedProjectId} onChange={(e) => setSelectedProjectId(e.target.value)} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-[11px] font-semibold text-slate-700 outline-none hover:border-slate-300 transition-colors cursor-pointer focus:ring-2 focus:ring-slate-200 focus:border-transparent">
              <option value="" disabled>{projects.length > 0 ? "Select a project" : "Create project"}</option>
              {projects.map(project => (
                <option key={project.id} value={project.id}>{project.name}</option>
              ))}
            </select>
          </div>

          {/* Sidebar Navigation Tabs */}
          <div className="flex-1 w-full py-6 space-y-1">
            <div className="px-1 mb-3">
              <h2 className="text-[10px] font-bold uppercase tracking-widest text-slate-400 font-mono">Intelligence Hub</h2>
            </div>
            <TabsList className="flex flex-col bg-transparent p-0 rounded-none h-auto w-full gap-1.5 border-none">
              <TabsTrigger
                value="research"
                className="w-full justify-start rounded-xl px-4 py-3 text-[11px] font-bold uppercase tracking-widest text-slate-500 hover:bg-slate-50 hover:text-slate-900 data-[state=active]:bg-slate-900 data-[state=active]:text-white data-[state=active]:shadow-sm transition-all duration-200 flex items-center gap-2.5 border-none"
              >
                <MessageSquareText className="w-4 h-4 shrink-0" />
                Research Chat
              </TabsTrigger>
              <TabsTrigger
                value="map"
                className="w-full justify-start rounded-xl px-4 py-3 text-[11px] font-bold uppercase tracking-widest text-slate-500 hover:bg-slate-50 hover:text-slate-900 data-[state=active]:bg-slate-900 data-[state=active]:text-white data-[state=active]:shadow-sm transition-all duration-200 flex items-center gap-2.5 border-none"
              >
                <Network className="w-4 h-4 shrink-0" />
                Knowledge Map
              </TabsTrigger>
              <TabsTrigger
                value="eligibility"
                className="w-full justify-start rounded-xl px-4 py-3 text-[11px] font-bold uppercase tracking-widest text-slate-500 hover:bg-slate-50 hover:text-slate-900 data-[state=active]:bg-slate-900 data-[state=active]:text-white data-[state=active]:shadow-sm transition-all duration-200 flex items-center gap-2.5 border-none"
              >
                <CheckSquare className="w-4 h-4 shrink-0" />
                Eligibility
              </TabsTrigger>
              <TabsTrigger
                value="registry"
                className="w-full justify-start rounded-xl px-4 py-3 text-[11px] font-bold uppercase tracking-widest text-slate-500 hover:bg-slate-50 hover:text-slate-900 data-[state=active]:bg-slate-900 data-[state=active]:text-white data-[state=active]:shadow-sm transition-all duration-200 flex items-center gap-2.5 border-none"
              >
                <Landmark className="w-4 h-4 shrink-0" />
                Social Registry
              </TabsTrigger>
            </TabsList>
          </div>

          <div className="mt-auto w-full flex items-center justify-between px-2">
            <Tooltip>
              <TooltipTrigger asChild>
                <button className="text-slate-400 hover:text-slate-900 transition-colors p-2 hover:bg-slate-100 rounded-lg">
                  <Settings className="w-4 h-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="right"><p>Enterprise Settings</p></TooltipContent>
            </Tooltip>
            <Avatar className="w-8 h-8 ring-2 ring-slate-100">
              <AvatarImage src="https://github.com/shadcn.png" />
              <AvatarFallback>AD</AvatarFallback>
            </Avatar>
          </div>
        </nav>

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

            <div className="flex-1 flex flex-col overflow-hidden min-h-0">
              {/* ── Social Registry Dashboard Tab ── */}
              <TabsContent value="registry" className="flex-1 flex flex-col min-h-0 overflow-hidden m-0 p-0 border-none outline-none bg-[#fcfdfe] data-[state=inactive]:hidden data-[state=active]:flex" forceMount>
                <UsrDashboard API={API} />
              </TabsContent>

              <TabsContent value="eligibility" className="flex-1 flex flex-col min-h-0 overflow-hidden m-0 p-0 border-none outline-none data-[state=inactive]:hidden data-[state=active]:flex" forceMount>
                <EligibilityStudio API={API} />
              </TabsContent>

              <TabsContent value="research" className="flex-1 flex flex-col overflow-hidden min-h-0 mt-0 m-0 p-0 border-none outline-none data-[state=inactive]:hidden data-[state=active]:flex" forceMount>
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
                                      const baseName = source.filename.split(/[/\\]/).pop() || source.filename;
                                      const cleanName = baseName.replace(/\.pdf$/i, '');
                                      const displayName = cleanName.length > 20 ? cleanName.substring(0, 17) + '...' : cleanName;
                                      const sourceLabel = source.page ? `${displayName} (p. ${source.page})` : displayName;
                                      return (
                                        <TooltipProvider>
                                          <Tooltip>
                                            <TooltipTrigger asChild>
                                              <span
                                                onClick={() => setSelectedSource(source)}
                                                className="inline-flex items-center gap-1 bg-slate-100 text-slate-900 px-2 py-0.5 rounded-md font-bold text-[10px] cursor-pointer hover:bg-slate-900 hover:text-white transition-colors mx-0.5"
                                              >
                                                <FileText className="w-2.5 h-2.5 shrink-0 text-slate-500" />
                                                {sourceLabel}
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
                                },
                                p: ({ node, ...props }) => <p {...props}>{renderWithLineBreaksAndCitations(props.children, result?.sources || [], setSelectedSource)}</p>,
                                td: ({ node, ...props }) => <td {...props}>{renderWithLineBreaksAndCitations(props.children, result?.sources || [], setSelectedSource)}</td>,
                                th: ({ node, ...props }) => <th {...props}>{renderWithLineBreaksAndCitations(props.children, result?.sources || [], setSelectedSource)}</th>,
                                li: ({ node, ...props }) => <li {...props}>{renderWithLineBreaksAndCitations(props.children, result?.sources || [], setSelectedSource)}</li>
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

              <TabsContent value="map" className="flex-1 relative overflow-hidden min-h-0 mt-0 m-0 p-0 outline-none border-none bg-white h-full min-h-[700px] data-[state=inactive]:hidden data-[state=active]:block" forceMount>
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
                      ref={graphRef}
                      graphData={graphData}
                      width={Math.max(mapDimensions.width, 900)}
                      height={Math.max(mapDimensions.height, 620)}
                      nodeLabel={(node: any) => {
                        let label = `${node.type}: ${node.label}`;
                        if (node.fraud_reason) {
                          label += `<br/><span style="color: #ef4444; font-weight: bold; font-size: 10px;">⚠️ ${node.fraud_reason}</span>`;
                        }
                        return label;
                      }}
                      linkLabel={(link: any) => `${link.label}: ${link.description || ''}`}
                      nodeColor={(node: any) => resolveEntityColor(node.type || 'Default', node.label)}
                      nodeRelSize={8}
                      nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
                        const label = node.label;
                        const fontSize = 14 / globalScale;
                        const category = resolveEntityCategory(node.type || 'Default', label);
                        const color = ENTITY_COLORS[category] || ENTITY_COLORS.Default;
                        const isFraud = category === 'FraudFlag';
                        const isSchemeFocusNode = schemeGraphId && node.id === schemeGraphId;
                        const showLabel = schemeGraphId
                          ? (
                            isSchemeFocusNode
                            || category === 'Citizen'
                            || category === 'FraudFlag'
                            || globalScale > 1.4
                          )
                          : globalScale > 0.6

                        ctx.font = `bold ${fontSize}px Inter`;
                        ctx.textAlign = 'center';
                        ctx.textBaseline = 'middle';

                        // Immersive node glow - amplified for fraud
                        ctx.shadowColor = color;
                        ctx.shadowBlur = (isFraud ? 30 : 10) / globalScale;

                        ctx.fillStyle = color;
                        ctx.beginPath();
                        const radius = (isSchemeFocusNode ? 16 : isFraud ? 12 : 7) / globalScale;
                        ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
                        ctx.fill();

                        ctx.shadowBlur = 0; // Reset shadow

                        if (showLabel) {
                          ctx.fillStyle = '#1e293b';
                          const offset = (isSchemeFocusNode ? 28 : isFraud ? 22 : 16) / globalScale;
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
                    <div className="absolute top-8 left-8 flex flex-col gap-3 z-10">
                      <div className="w-80 rounded-[28px] border border-slate-200 bg-white/95 p-5 shadow-2xl backdrop-blur">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-[10px] font-bold uppercase tracking-[0.35em] text-slate-400">Scheme Browser</p>
                            <p className="mt-2 text-xs font-medium text-slate-500">
                              Pick a scheme to load its sampled citizen neighborhood.
                            </p>
                          </div>
                          <Button
                            variant="secondary"
                            size="sm"
                            className="h-8 rounded-xl px-3 text-[10px] font-bold uppercase tracking-wider"
                            onClick={() => fetchSchemeOptions()}
                            disabled={loadingSchemes}
                          >
                            {loadingSchemes ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Refresh'}
                          </Button>
                        </div>

                        <div className="mt-4 flex items-center gap-2">
                          <Input
                            placeholder="Search scheme"
                            value={schemeSearch}
                            onChange={(e: ChangeEvent<HTMLInputElement>) => setSchemeSearch(e.target.value)}
                            className="h-9 rounded-xl border-slate-200 bg-slate-50 text-xs font-semibold text-slate-700 shadow-none focus-visible:ring-slate-300"
                          />
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-9 rounded-xl px-3 text-[10px] font-bold uppercase tracking-wider text-slate-500"
                            onClick={() => handleResetSchemeGraph()}
                          >
                            Clear
                          </Button>
                        </div>

                        <div className="mt-4 rounded-2xl border border-slate-100 bg-slate-50/70 px-3 py-2">
                          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Active View</p>
                          <p className="mt-1 text-sm font-bold text-slate-900">
                            {schemeGraphId ? schemeGraphId : 'Overview'}
                          </p>
                        </div>

                        <ScrollArea className="mt-4 h-72 rounded-2xl border border-slate-100 bg-white">
                          <div className="space-y-2 p-3">
                            {filteredSchemeOptions.map((scheme) => {
                              const isActive = scheme.id === schemeGraphId
                              return (
                                <button
                                  key={scheme.id}
                                  type="button"
                                  onClick={() => handleLoadSchemeGraph(scheme.id)}
                                  className={`w-full rounded-2xl border px-4 py-3 text-left transition-all ${
                                    isActive
                                      ? 'border-slate-900 bg-slate-900 text-white shadow-lg'
                                      : 'border-slate-100 bg-slate-50 hover:border-slate-300 hover:bg-white'
                                  }`}
                                >
                                  <div className="flex items-center justify-between gap-3">
                                    <span className={`text-sm font-black tracking-tight ${isActive ? 'text-white' : 'text-slate-900'}`}>
                                      {scheme.id}
                                    </span>
                                    <span className={`text-[10px] font-bold uppercase tracking-[0.25em] ${isActive ? 'text-slate-300' : 'text-slate-400'}`}>
                                      {scheme.citizen_count} citizens
                                    </span>
                                  </div>
                                  <p className={`mt-1 text-xs font-medium ${isActive ? 'text-slate-200' : 'text-slate-500'}`}>
                                    {scheme.name}
                                  </p>
                                  <p className={`mt-2 text-[10px] font-bold uppercase tracking-widest ${isActive ? 'text-slate-300' : 'text-slate-400'}`}>
                                    {scheme.enrollment_count} enrollments
                                  </p>
                                </button>
                              )
                            })}
                            {!loadingSchemes && filteredSchemeOptions.length === 0 && (
                              <div className="rounded-2xl border border-dashed border-slate-200 px-4 py-8 text-center">
                                <p className="text-xs font-semibold text-slate-500">No schemes match this search yet.</p>
                              </div>
                            )}
                          </div>
                        </ScrollArea>
                      </div>
                      <Button variant="secondary" size="icon" className="bg-white/90 backdrop-blur shadow-2xl rounded-xl border-slate-100 h-10 w-10 hover:bg-white" onClick={() => fetchGraph()}>
                        <Network className="w-4 h-4 text-slate-900" />
                      </Button>
                    </div>

                    <div className="absolute bottom-10 right-10 bg-white/90 backdrop-blur border border-slate-100 rounded-[32px] p-8 shadow-[0px_30px_90px_rgba(0,0,0,0.12)] animate-in slide-in-from-bottom-8 duration-1000 z-10 w-72">
                      <h4 className="text-[10px] font-bold uppercase tracking-[0.4em] text-slate-400 mb-6 border-b border-slate-50 pb-4">Color Legend</h4>
                      <div className="grid grid-cols-2 gap-x-6 gap-y-5">
                        {DATABASE_ENTITY_LEGEND.map((type) => (
                          <div key={type} className="flex items-center gap-4">
                            <div className="w-4 h-4 rounded-full shadow-inner ring-4 ring-white" style={{ backgroundColor: ENTITY_COLORS[type] }} />
                            <span className="text-[10px] font-bold text-slate-600 uppercase tracking-tighter whitespace-nowrap">{type}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </TabsContent>


            </div>

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
        </Tabs>
      </TooltipProvider>
    </div>
  )
}















