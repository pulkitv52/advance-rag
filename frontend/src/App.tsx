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
  Mic,
  Square,
  Volume2,
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
import { convertAudioBlobToWav, requestSTTTranscript } from "./lib/voice"


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

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  result?: QueryResult
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
const GovWestBengalEmblem = () => (
  <img 
    src="/wb_logo.png" 
    alt="Govt. of West Bengal Logo" 
    className="h-24 w-24 object-contain shrink-0 drop-shadow-[0_8px_18px_rgba(15,23,42,0.14)] transition-transform duration-300 hover:scale-105" 
  />
)



const SUGGESTIONS = [
  {
    category: "Key Schemes",
    items: [
      {
        title: "Lokkhir Bhandar",
        description: "Verify eligibility age and income thresholds for direct financial support.",
        query: "What are the eligibility criteria and monthly benefit amounts for the Lokkhir Bhandar scheme?",
        icon: "💳"
      },
      {
        title: "Swasthya Sathi",
        description: "Explore group health protection benefits and universal health coverage scope.",
        query: "What is the coverage scope and who is eligible under the Swasthya Sathi health scheme?",
        icon: "🏥"
      },
      {
        title: "Banglar Bari (Gramin)",
        description: "Check financial assistance rules and exclusions for rural housing construction.",
        query: "Explain the eligibility criteria and exclusion rules for the Banglar Bari (Gramin) housing scheme.",
        icon: "🏠"
      },
      {
        title: "Chaa Sundari Extension",
        description: "Review homestead land allocations and building funds for tea garden workers.",
        query: "What are the key features and eligibility rules for the Chaa Sundari Extension housing scheme?",
        icon: "🏡"
      }
    ]
  },
  {
    category: "Treasury & Finance Policy",
    items: [
      {
        title: "Mission Vatsalya",
        description: "Audit guidelines for child protection services, funding, and CWCs.",
        query: "Explain the institutional framework and funding rules under the Mission Vatsalya child welfare guidelines.",
        icon: "🧸"
      },
      {
        title: "Amar Fasal Amar Gola",
        description: "Check storage structure subsidies and marketing guidelines for onion preservation.",
        query: "What are the subsidies and implementation rules for Onion Storage Structures under Amar Fasal Amar Gola?",
        icon: "🧅"
      },
      {
        title: "Post-Matric Scholarship",
        description: "Verify freeship card rules, eligibility, and scholarship groups for OBC/EBC students.",
        query: "What are the eligibility rules and scholarship groups under the Post-Matric Scholarship for OBC/EBC students?",
        icon: "🎓"
      }
    ]
  }
];

const RAGLoader = () => {
  const steps = [
    "Parsing semantic query & extracting policy intent...",
    "Querying vector database for matching circulars & notifications...",
    "Scanning Neo4j Knowledge Graph for relational scheme anomalies...",
    "Running cross-validation on treasury budget rules & metadata...",
    "Synthesizing audit-ready response with grounded citations..."
  ];
  const [currentStep, setCurrentStep] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentStep((prev) => (prev < steps.length - 1 ? prev + 1 : prev));
    }, 1800);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="w-full bg-gradient-to-r from-slate-50 to-white border border-slate-100 rounded-3xl p-8 shadow-sm flex flex-col md:flex-row items-center gap-6 animate-in fade-in duration-300 relative overflow-hidden">
      {/* Decorative background grid/pulse */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_30%,rgba(11,76,140,0.02),transparent_35%)] pointer-events-none" />
      
      {/* Big Aesthetic Spinning/Pulsing Visual */}
      <div className="relative flex items-center justify-center shrink-0 w-16 h-16 rounded-2xl bg-blue-50/50 border border-blue-100/50 shadow-inner">
        {/* Pulsing glow ring */}
        <span className="absolute inset-0 rounded-2xl bg-blue-500/10 animate-pulse" />
        
        {/* Animated RAG Oracle logo or network particles */}
        <div className="relative w-8 h-8 flex items-center justify-center">
          <Network className="w-6 h-6 text-[#0B4C8C] animate-pulse" />
          <div className="absolute inset-0 rounded-full border-2 border-t-[#FF9933] border-r-transparent border-b-[#138808] border-l-transparent animate-spin" style={{ animationDuration: '1200ms' }} />
        </div>
      </div>

      {/* Progress & Text */}
      <div className="flex-1 w-full space-y-4">
        <div className="space-y-1">
          <div className="flex items-center justify-between text-[10px] font-black uppercase tracking-[0.2em] text-[#0B4C8C]">
            <span>Deep Synthesis Engine</span>
            <span className="text-[#FF9933] animate-pulse">Running</span>
          </div>
          <p className="text-sm font-semibold text-slate-800 transition-all duration-300 animate-pulse">
            {steps[currentStep]}
          </p>
        </div>

        {/* Custom Progress Bar */}
        <div className="relative w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
          <div 
            className="absolute top-0 left-0 h-full bg-gradient-to-r from-[#FF9933] via-[#0B4C8C] to-[#138808] rounded-full transition-all duration-500 ease-out"
            style={{ width: `${((currentStep + 1) / steps.length) * 100}%` }}
          />
        </div>

        {/* Sub-details (skeletons) */}
        <div className="space-y-2.5 opacity-40">
          <div className="h-2 bg-slate-200 rounded-full w-4/5 animate-pulse" />
          <div className="h-2 bg-slate-200 rounded-full w-2/3 animate-pulse" />
        </div>
      </div>
    </div>
  );
};

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
  const [, setSavingAnalysis] = useState(false)
  const [result, setResult] = useState<QueryResult | null>(null)
  const [selectedSource, setSelectedSource] = useState<Source | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([])
  const chatEndRef = useRef<HTMLDivElement>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const speechRecognitionRef = useRef<any>(null)
  const speechBaseQueryRef = useRef<string>("")
  const isRecordingRef = useRef<boolean>(false)
  const [isRecording, setIsRecording] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [speakingMessageIndex, setSpeakingMessageIndex] = useState<number | null>(null)
  const [voiceLanguage, setVoiceLanguage] = useState<'en-IN' | 'hi-IN'>('en-IN')
  const sttMode: 'live' | 'accurate' = 'live'

  useEffect(() => {
    if (chatHistory.length > 0 || querying) {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [chatHistory, querying])

  useEffect(() => {
    isRecordingRef.current = isRecording
  }, [isRecording])

  const handleStartRecording = async () => {
    if (sttMode === 'live') {
      const SpeechRecognitionApi =
        (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
      if (!SpeechRecognitionApi) {
        setError("Live STT is not supported in this browser. Switch to Accurate mode.")
        return
      }
      setError(null)
      const recognition = new SpeechRecognitionApi()
      speechRecognitionRef.current = recognition
      speechBaseQueryRef.current = query.trim()
      recognition.lang = voiceLanguage
      recognition.continuous = true
      recognition.interimResults = true

      recognition.onresult = (event: any) => {
        let finalTranscript = ""
        let interimTranscript = ""
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const transcript = String(event.results[i][0]?.transcript || "").trim()
          if (!transcript) continue
          if (event.results[i].isFinal) finalTranscript += `${transcript} `
          else interimTranscript += `${transcript} `
        }
        const combined = `${finalTranscript}${interimTranscript}`.trim()
        const base = speechBaseQueryRef.current
        setQuery(combined ? `${base}${base ? " " : ""}${combined}` : base)
      }

      recognition.onend = () => {
        if (isRecordingRef.current) {
          try {
            recognition.start()
          } catch {
            // Ignore recognition restart races.
          }
        }
      }

      recognition.onerror = (event: any) => {
        if (event?.error === "not-allowed") setError("Microphone permission denied.")
      }

      try {
        recognition.start()
        setIsRecording(true)
      } catch (speechError: any) {
        setError(speechError?.message || "Unable to start live speech recognition.")
      }
      return
    }

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setError("Your browser does not support microphone recording.")
      return
    }

    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      audioChunksRef.current = []
      mediaRecorderRef.current = recorder

      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      recorder.onstop = async () => {
        const tracks = stream.getTracks()
        tracks.forEach((track) => track.stop())
        setIsRecording(false)

        if (audioChunksRef.current.length === 0) return

        setIsTranscribing(true)
        try {
          const rawAudioBlob = new Blob(audioChunksRef.current, { type: recorder.mimeType || 'audio/webm' })
          const audioBlob = await convertAudioBlobToWav(rawAudioBlob)
          const { transcript } = await requestSTTTranscript(API, {
            file: audioBlob,
            filename: "query.wav",
            language_code: voiceLanguage,
          })
          if (transcript) {
            setQuery((prev) => `${prev}${prev.trim() ? " " : ""}${transcript}`.trim())
          } else {
            setError("Speech recognized, but no transcript was returned.")
          }
        } catch (sttError: any) {
          setError(sttError?.response?.data?.detail || "Voice transcription failed.")
        } finally {
          setIsTranscribing(false)
        }
      }

      recorder.start()
      setIsRecording(true)
    } catch (recordError: any) {
      setError(recordError?.message || "Unable to access microphone.")
      setIsRecording(false)
    }
  }

  const handleStopRecording = () => {
    const recognition = speechRecognitionRef.current
    if (recognition) {
      setIsRecording(false)
      try {
        recognition.stop()
      } catch {
        // ignore
      }
      speechRecognitionRef.current = null
      return
    }

    const recorder = mediaRecorderRef.current
    if (!recorder || recorder.state === 'inactive') return
    recorder.stop()
  }

  const handleSpeakAnswer = async (messageIndex: number, text: string) => {
    if (!text?.trim()) return
    setError(null)
    setSpeakingMessageIndex(messageIndex)
    try {
      const toSpeechText = (raw: string): string => {
        let cleaned = String(raw || "")
        // Remove fenced code blocks and inline code
        cleaned = cleaned.replace(/```[\s\S]*?```/g, " ")
        cleaned = cleaned.replace(/`([^`]+)`/g, "$1")
        // Convert markdown links [text](url) -> text
        cleaned = cleaned.replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1")
        // Strip markdown emphasis/heading markers
        cleaned = cleaned.replace(/[*_~#>-]+/g, " ")
        // Remove table separators and pipes
        cleaned = cleaned.replace(/\|/g, " ")
        cleaned = cleaned.replace(/-{3,}/g, " ")
        // Remove source/citation tokens like [Source 1], 【Source 2】
        cleaned = cleaned.replace(/(?:\[|【)\s*Source\s*\d+\s*(?:\]|】)/gi, " ")
        // Normalize whitespace
        cleaned = cleaned.replace(/\s+/g, " ").trim()
        return cleaned
      }

      const synth = window.speechSynthesis
      if (!synth) {
        setSpeakingMessageIndex(null)
        setError("Speech playback is not supported in this browser.")
        return
      }

      const pickBestIndianVoice = (langCode: 'en-IN' | 'hi-IN'): SpeechSynthesisVoice | null => {
        const voices = synth.getVoices() || []
        if (!voices.length) return null
        const targetPrefix = langCode.toLowerCase().startsWith("hi") ? "hi" : "en"
        const strongMatch = voices.find((v) => String(v.lang || "").toLowerCase() === langCode.toLowerCase())
        if (strongMatch) return strongMatch

        const indianHints = ["india", "indian", "aditi", "hindi", "bharat"]
        const hinted = voices.find((v) => {
          const name = String(v.name || "").toLowerCase()
          const lang = String(v.lang || "").toLowerCase()
          const hasHint = indianHints.some((h) => name.includes(h))
          return lang.startsWith(`${targetPrefix}-`) && hasHint
        })
        if (hinted) return hinted

        const familyMatch = voices.find((v) => String(v.lang || "").toLowerCase().startsWith(`${targetPrefix}-`))
        return familyMatch || null
      }

      const normalized = toSpeechText(text)
      if (!normalized) {
        setSpeakingMessageIndex(null)
        setError("No readable text found for speech.")
        return
      }
      const chunks: string[] = []
      const maxChunk = 220
      let cursor = 0
      while (cursor < normalized.length) {
        let end = Math.min(cursor + maxChunk, normalized.length)
        if (end < normalized.length) {
          const split = Math.max(
            normalized.lastIndexOf(". ", end),
            normalized.lastIndexOf(", ", end),
            normalized.lastIndexOf(" ", end),
          )
          if (split > cursor + 60) {
            end = split + 1
          }
        }
        const part = normalized.slice(cursor, end).trim()
        if (part) chunks.push(part)
        cursor = end
      }

      synth.cancel()
      const selectedVoice = pickBestIndianVoice(voiceLanguage)

      const speakChunk = (index: number) => {
        if (index >= chunks.length) {
          setSpeakingMessageIndex((current) => (current === messageIndex ? null : current))
          return
        }
        const utterance = new SpeechSynthesisUtterance(chunks[index])
        utterance.lang = voiceLanguage
        if (selectedVoice) utterance.voice = selectedVoice
        utterance.rate = 0.95
        utterance.pitch = 1.0
        utterance.onend = () => speakChunk(index + 1)
        utterance.onerror = () => {
          setSpeakingMessageIndex((current) => (current === messageIndex ? null : current))
          setError("Unable to play speech.")
        }
        synth.speak(utterance)
      }

      speakChunk(0)
    } catch (speechError: any) {
      setSpeakingMessageIndex((current) => (current === messageIndex ? null : current))
      setError(speechError?.message || "Text-to-speech failed.")
    }
  }

  const handleStopSpeaking = () => {
    const synth = window.speechSynthesis
    if (!synth) return
    synth.cancel()
    setSpeakingMessageIndex(null)
  }

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

  const handleQuery = async (queryOverride?: string) => {
    if (isRecording) {
      handleStopRecording()
    }
    const currentQuery = (queryOverride ?? query).trim()
    if (!currentQuery) return
    setQuerying(true)
    setQuery('')
    setError(null)
    setSelectedSource(null)
    try {
      const payload = {
        query: currentQuery,
        top_k: 10,
        document_ids: selectedIds.size > 0 ? Array.from(selectedIds) : null,
        history: chatHistory.length > 0 ? chatHistory.map(h => ({ role: h.role, content: h.content })) : null
      }
      setChatHistory(prev => [...prev, { role: 'user', content: currentQuery }])
      
      const res = await axios.post(`${API}/query/`, payload)
      const resData = { ...res.data, project_id: selectedProjectId || null }
      
      setResult(resData)
      setChatHistory(prev => [
        ...prev,
        { role: 'assistant', content: res.data.answer, result: resData }
      ])
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
  const isResearchWelcomeState = chatHistory.length === 0 && !querying
  const renderCivicBackdrop = () => (
    <>
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_left_center,rgba(217,119,6,0.12),transparent_24%),radial-gradient(circle_at_top_right,rgba(11,76,140,0.10),transparent_20%),radial-gradient(circle_at_bottom_left,rgba(11,76,140,0.06),transparent_26%)]" />
      <div
        className="pointer-events-none absolute -top-28 -left-10 h-[360px] w-[360px] opacity-22"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 400'%3E%3Cg fill='none' stroke='rgba(90,111,138,0.34)' stroke-width='10'%3E%3Ccircle cx='200' cy='200' r='150'/%3E%3C/g%3E%3Cg stroke='rgba(90,111,138,0.26)' stroke-width='3'%3E%3Cline x1='200' y1='200' x2='200' y2='50'/%3E%3Cline x1='200' y1='200' x2='238.82' y2='55.11'/%3E%3Cline x1='200' y1='200' x2='275' y2='70.1'/%3E%3Cline x1='200' y1='200' x2='306.07' y2='93.93'/%3E%3Cline x1='200' y1='200' x2='329.9' y2='125'/%3E%3Cline x1='200' y1='200' x2='344.89' y2='161.18'/%3E%3Cline x1='200' y1='200' x2='350' y2='200'/%3E%3Cline x1='200' y1='200' x2='344.89' y2='238.82'/%3E%3Cline x1='200' y1='200' x2='329.9' y2='275'/%3E%3Cline x1='200' y1='200' x2='306.07' y2='306.07'/%3E%3Cline x1='200' y1='200' x2='275' y2='329.9'/%3E%3Cline x1='200' y1='200' x2='238.82' y2='344.89'/%3E%3Cline x1='200' y1='200' x2='200' y2='350'/%3E%3Cline x1='200' y1='200' x2='161.18' y2='344.89'/%3E%3Cline x1='200' y1='200' x2='125' y2='329.9'/%3E%3Cline x1='200' y1='200' x2='93.93' y2='306.07'/%3E%3Cline x1='200' y1='200' x2='70.1' y2='275'/%3E%3Cline x1='200' y1='200' x2='55.11' y2='238.82'/%3E%3Cline x1='200' y1='200' x2='50' y2='200'/%3E%3Cline x1='200' y1='200' x2='55.11' y2='161.18'/%3E%3Cline x1='200' y1='200' x2='70.1' y2='125'/%3E%3Cline x1='200' y1='200' x2='93.93' y2='93.93'/%3E%3Cline x1='200' y1='200' x2='125' y2='70.1'/%3E%3Cline x1='200' y1='200' x2='161.18' y2='55.11'/%3E%3C/g%3E%3C/svg%3E\")",
          backgroundSize: 'contain',
          backgroundRepeat: 'no-repeat',
        }}
      />
      <div
        className="pointer-events-none absolute top-8 right-28 h-[190px] w-[190px] opacity-24"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 260 260'%3E%3Cg fill='none' stroke='rgba(90,111,138,0.34)' stroke-width='8'%3E%3Ccircle cx='130' cy='130' r='92'/%3E%3C/g%3E%3Cg stroke='rgba(90,111,138,0.24)' stroke-width='2.6'%3E%3Cline x1='130' y1='130' x2='130' y2='38'/%3E%3Cline x1='130' y1='130' x2='153.81' y2='41.19'/%3E%3Cline x1='130' y1='130' x2='176' y2='50.33'/%3E%3Cline x1='130' y1='130' x2='195.05' y2='64.95'/%3E%3Cline x1='130' y1='130' x2='209.67' y2='84'/%3E%3Cline x1='130' y1='130' x2='218.81' y2='106.19'/%3E%3Cline x1='130' y1='130' x2='222' y2='130'/%3E%3Cline x1='130' y1='130' x2='218.81' y2='153.81'/%3E%3Cline x1='130' y1='130' x2='209.67' y2='176'/%3E%3Cline x1='130' y1='130' x2='195.05' y2='195.05'/%3E%3Cline x1='130' y1='130' x2='176' y2='209.67'/%3E%3Cline x1='130' y1='130' x2='153.81' y2='218.81'/%3E%3Cline x1='130' y1='130' x2='130' y2='222'/%3E%3Cline x1='130' y1='130' x2='106.19' y2='218.81'/%3E%3Cline x1='130' y1='130' x2='84' y2='209.67'/%3E%3Cline x1='130' y1='130' x2='64.95' y2='195.05'/%3E%3Cline x1='130' y1='130' x2='50.33' y2='176'/%3E%3Cline x1='130' y1='130' x2='41.19' y2='153.81'/%3E%3Cline x1='130' y1='130' x2='38' y2='130'/%3E%3Cline x1='130' y1='130' x2='41.19' y2='106.19'/%3E%3Cline x1='130' y1='130' x2='50.33' y2='84'/%3E%3Cline x1='130' y1='130' x2='64.95' y2='64.95'/%3E%3Cline x1='130' y1='130' x2='84' y2='50.33'/%3E%3Cline x1='130' y1='130' x2='106.19' y2='41.19'/%3E%3C/g%3E%3Ccircle cx='130' cy='130' r='14' fill='rgba(90,111,138,0.28)'/%3E%3C/svg%3E\")",
          backgroundSize: 'contain',
          backgroundRepeat: 'no-repeat',
        }}
      />
      <div
        className="pointer-events-none absolute inset-0 opacity-55"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 800'%3E%3Cg fill='none' stroke='rgba(135,149,168,0.22)' stroke-width='1.5'%3E%3Cpath d='M84 584 246 396 418 560 582 302 770 442 938 250'/%3E%3Cpath d='M902 172 1034 246 1122 136' stroke-dasharray='4 8'/%3E%3Cpath d='M176 664 336 590 496 690' stroke-dasharray='5 7'/%3E%3C/g%3E%3Cg fill='rgba(135,149,168,0.42)'%3E%3Ccircle cx='84' cy='584' r='6'/%3E%3Ccircle cx='246' cy='396' r='7'/%3E%3Ccircle cx='418' cy='560' r='6'/%3E%3Ccircle cx='582' cy='302' r='7'/%3E%3Ccircle cx='770' cy='442' r='6'/%3E%3Ccircle cx='938' cy='250' r='7'/%3E%3Ccircle cx='1034' cy='246' r='5'/%3E%3Ccircle cx='1122' cy='136' r='5'/%3E%3Ccircle cx='176' cy='664' r='5'/%3E%3Ccircle cx='496' cy='690' r='5'/%3E%3Ccircle cx='336' cy='590' r='5'/%3E%3C/g%3E%3Cg fill='rgba(255,153,51,0.30)'%3E%3Ccircle cx='128' cy='524' r='5'/%3E%3Ccircle cx='964' cy='214' r='5'/%3E%3C/g%3E%3Cg fill='rgba(11,76,140,0.08)'%3E%3Ccircle cx='1048' cy='520' r='82'/%3E%3Cpath d='M1012 492h72v56h-72z'/%3E%3Cpath d='M1028 492v-16c0-18 14-32 32-32s32 14 32 32v16' stroke='rgba(11,76,140,0.15)' stroke-width='8' fill='none'/%3E%3C/g%3E%3Cg fill='rgba(11,76,140,0.08)'%3E%3Ccircle cx='858' cy='620' r='58'/%3E%3Cpath d='M836 618h44M836 634h44M836 650h30' stroke='rgba(11,76,140,0.18)' stroke-width='6' stroke-linecap='round'/%3E%3C/g%3E%3C/svg%3E\")",
          backgroundSize: 'cover',
          backgroundRepeat: 'no-repeat',
          backgroundPosition: 'center',
        }}
      />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-20 bg-[linear-gradient(to_bottom,rgba(11,76,140,0.10),transparent)]" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-32 bg-[linear-gradient(to_top,rgba(181,101,29,0.16),rgba(181,101,29,0.06),transparent)]" />
    </>
  )

  const renderQueryBar = (isCentered: boolean) => {
    return (
      <div className={`w-full ${isCentered ? 'max-w-[850px]' : 'max-w-[1300px]'} mx-auto relative cursor-text group`} onClick={() => {
        const inputId = isCentered ? 'query-input-centered' : 'query-input';
        document.getElementById(inputId)?.focus();
      }}>
        <div className="absolute inset-x-0 bottom-[-8px] h-full bg-slate-900/5 blur-2xl rounded-3xl" />
        <div className={`relative bg-white border border-slate-200/90 rounded-3xl p-1.5 flex gap-0 shadow-[0px_20px_50px_rgba(0,0,0,0.06)] group-hover:border-slate-400 focus-within:border-slate-500 focus-within:ring-4 focus-within:ring-slate-100 transition-all duration-300 ${isCentered ? 'scale-105' : ''}`}>
          <Input
            id={isCentered ? 'query-input-centered' : 'query-input'}
            placeholder="Synthesize information about schemes, budgets, circulars..."
            value={query}
            autoComplete="off"
            onChange={(e: ChangeEvent<HTMLInputElement>) => setQuery(e.target.value)}
            onKeyDown={(e: React.KeyboardEvent<HTMLInputElement>) => { if (e.key === 'Enter') handleQuery() }}
            className="flex-1 bg-transparent border-none shadow-none text-base px-6 py-4 h-14 placeholder:text-slate-400 text-slate-800 font-medium focus-visible:ring-0"
          />
          <Button
            onClick={() => handleQuery()}
            disabled={querying || isTranscribing || !query.trim()}
            className="bg-[#0B4C8C] hover:bg-[#093d70] text-white w-14 h-14 rounded-2xl flex items-center justify-center p-0 shrink-0 transition-all duration-200 active:scale-95 shadow-md shadow-blue-200/50 disabled:opacity-50 disabled:shadow-none"
          >
            {querying || isTranscribing ? <Loader2 className="w-6 h-6 animate-spin" /> : <Search className="w-6 h-6" />}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-full bg-[#f4f7fb] text-slate-900 font-sans selection:bg-slate-900 selection:text-white overflow-hidden border-t-4 border-[#FF9933]">
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
          <nav className="w-48 flex flex-col py-6 border-r border-slate-200 bg-white shrink-0 z-30 px-4">
          <div className="mb-6 w-full flex flex-col items-center text-center gap-2 border-b border-slate-100 pb-5">
            <GovWestBengalEmblem />
            <div className="space-y-0.5 mt-1">
              <p className="text-[10px] font-black text-slate-900 tracking-tight leading-none uppercase">Govt. of West Bengal</p>
              <p className="text-[9px] font-bold text-slate-500 uppercase tracking-tight leading-none">Finance Department</p>
            </div>
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
          <div className="flex-1 w-full py-2 space-y-1">
            <div className="px-1 mb-3">
              <h2 className="text-[10px] font-bold uppercase tracking-widest text-slate-400 font-mono">Intelligence Hub</h2>
            </div>
            <TabsList className="flex flex-col bg-transparent p-0 rounded-none h-auto w-full gap-1.5 border-none">
              <TabsTrigger
                value="research"
                className="w-full justify-start rounded-xl px-4 py-3 text-[11px] font-bold uppercase tracking-widest text-slate-500 hover:bg-slate-50 hover:text-slate-900 data-[state=active]:bg-[#0B4C8C] data-[state=active]:text-white data-[state=active]:shadow-sm transition-all duration-200 flex items-center gap-2.5 border-none"
              >
                <MessageSquareText className="w-4 h-4 shrink-0" />
                Policy Research
              </TabsTrigger>
              <TabsTrigger
                value="map"
                className="w-full justify-start rounded-xl px-4 py-3 text-[11px] font-bold uppercase tracking-widest text-slate-500 hover:bg-slate-50 hover:text-slate-900 data-[state=active]:bg-[#0B4C8C] data-[state=active]:text-white data-[state=active]:shadow-sm transition-all duration-200 flex items-center gap-2.5 border-none"
              >
                <Network className="w-4 h-4 shrink-0" />
                Registry Graph
              </TabsTrigger>
              <TabsTrigger
                value="eligibility"
                className="w-full justify-start rounded-xl px-4 py-3 text-[11px] font-bold uppercase tracking-widest text-slate-500 hover:bg-slate-50 hover:text-slate-900 data-[state=active]:bg-[#0B4C8C] data-[state=active]:text-white data-[state=active]:shadow-sm transition-all duration-200 flex items-center gap-2.5 border-none"
              >
                <CheckSquare className="w-4 h-4 shrink-0" />
                Eligibility Studio
              </TabsTrigger>
              <TabsTrigger
                value="registry"
                className="w-full justify-start rounded-xl px-4 py-3 text-[11px] font-bold uppercase tracking-widest text-slate-500 hover:bg-slate-50 hover:text-slate-900 data-[state=active]:bg-[#0B4C8C] data-[state=active]:text-white data-[state=active]:shadow-sm transition-all duration-200 flex items-center gap-2.5 border-none"
              >
                <Landmark className="w-4 h-4 shrink-0" />
                Social Registry
              </TabsTrigger>
            </TabsList>
          </div>

          <div className="mt-auto w-full pt-4 border-t border-slate-100 space-y-4">
            <div className="flex flex-col items-center gap-1 py-2 bg-slate-50 rounded-xl border border-slate-100">
              <span className="text-[8px] font-extrabold uppercase tracking-widest text-slate-400">Technical Partner</span>
              <img src="/kpmg_logo.png" alt="KPMG" className="h-4 w-auto object-contain opacity-70 hover:opacity-100 transition-opacity" />
            </div>
            
            <div className="flex items-center justify-between px-1">
              <Tooltip>
                <TooltipTrigger asChild>
                  <button className="text-slate-400 hover:text-slate-900 transition-colors p-2 hover:bg-slate-100 rounded-lg">
                    <Settings className="w-4 h-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="right"><p>Enterprise Settings</p></TooltipContent>
              </Tooltip>
              <Avatar className="w-7 h-7 ring-2 ring-slate-100">
                <AvatarImage src="https://github.com/shadcn.png" />
                <AvatarFallback>AD</AvatarFallback>
              </Avatar>
            </div>
          </div>
        </nav>

        {/* ── Main Layout: Workspace & Intelligence ── */}
        <main className="flex-1 flex overflow-hidden">
          {/* Workspace Side */}
          <div className="flex-1 flex flex-col bg-white overflow-hidden relative">
            {/* Conditionally hide standard header for Registry for full-screen immersion */}
            {activeTab !== 'registry' && (
              <div className="w-full bg-[#FF9933] text-white text-[10px] md:text-[11px] font-extrabold py-1.5 overflow-hidden relative flex items-center select-none shrink-0 border-b border-amber-500/20">
                <div className="inline-block animate-marquee hover:[animation-play-state:paused] cursor-pointer pl-[100%] whitespace-nowrap">
                  Search verified policy circulars, verify citizen benefit scheme criteria, check state budget structures, and inspect official treasury directives with audit-ready accuracy.
                </div>
              </div>
            )}
            <header className={`h-20 border-b border-slate-100 flex flex-col justify-center px-10 shrink-0 bg-white ${activeTab === 'registry' ? 'hidden' : ''}`}>
              <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-widest text-slate-500 border-b border-slate-100 pb-2">
                <p>Government Service Intelligence Portal</p>
                <p className="text-slate-400">Citizen-first | Secure | Explainable</p>
              </div>
              <div className="h-0.5 w-full bg-gradient-to-r from-[#FF9933] via-white to-[#138808]" />
              <div className="flex items-center justify-between pt-2">
              <div className="flex items-center gap-4">
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Project: <span className="text-slate-900">{activeProject?.name || 'Select Project'}</span></p>
              </div>
              <div className="flex items-center gap-3">
                {activeTab === 'research' && chatHistory.length > 0 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setChatHistory([])
                      setResult(null)
                      setError(null)
                      setSelectedSource(null)
                    }}
                    className="text-[10px] font-bold uppercase text-rose-500 hover:text-rose-700 hover:bg-rose-50/50 transition-colors rounded-xl px-3 h-8"
                  >
                    Reset Session
                  </Button>
                )}
                {activeTab === 'research' && (
                  <Button
                    variant="default"
                    size="sm"
                    disabled={!result}
                    onClick={handleExportReport}
                    className="bg-slate-900 text-white rounded-lg px-4 h-8 text-[11px] font-bold shadow-lg shadow-slate-200 disabled:opacity-50"
                  >
                    Export Report
                  </Button>
                )}
              </div>
              </div>
            </header>

            <div className="flex-1 flex flex-col overflow-hidden min-h-0">
              {/* ── Social Registry Dashboard Tab ── */}
              <TabsContent value="registry" className="relative flex-1 flex flex-col min-h-0 overflow-y-auto overflow-x-hidden m-0 p-0 border-none outline-none bg-[#fcfdfe] data-[state=inactive]:hidden data-[state=active]:flex" forceMount>
                <div className="pointer-events-none absolute inset-x-0 top-0 h-72 overflow-hidden">
                  <div className="absolute inset-0 bg-[linear-gradient(140deg,#fffdf8_0%,#f7f2e9_36%,#edf4ff_72%,#f8fbff_100%)]" />
                  {renderCivicBackdrop()}
                </div>
                <div className="relative z-10 flex-1 min-h-0 h-full">
                  <UsrDashboard API={API} />
                </div>
              </TabsContent>

              <TabsContent value="eligibility" className="relative flex-1 flex flex-col min-h-0 overflow-hidden m-0 p-0 border-none outline-none bg-[linear-gradient(140deg,#fffdf8_0%,#f7f2e9_36%,#edf4ff_72%,#f8fbff_100%)] data-[state=inactive]:hidden data-[state=active]:flex" forceMount>
                {renderCivicBackdrop()}
                <div className="relative z-10 flex-1 min-h-0">
                  <EligibilityStudio API={API} />
                </div>
              </TabsContent>

              <TabsContent
                value="research"
                className={`relative flex-1 flex flex-col overflow-hidden min-h-0 mt-0 m-0 p-0 border-none outline-none data-[state=inactive]:hidden data-[state=active]:flex ${
                  isResearchWelcomeState
                    ? 'bg-[linear-gradient(140deg,#fffdf8_0%,#f7f2e9_36%,#edf4ff_72%,#f8fbff_100%)]'
                    : 'bg-white'
                }`}
                forceMount
              >
                {isResearchWelcomeState && renderCivicBackdrop()}
                <ScrollArea className="flex-1 h-full">
                  <div className={`relative z-10 w-full max-w-[1300px] mx-auto px-6 lg:px-10 pt-10 pb-32 ${isResearchWelcomeState ? 'space-y-6' : 'space-y-10'}`}>
                    {/* Hero Welcome Area */}
                    {isResearchWelcomeState && (
                      <div className="w-full flex flex-col items-center justify-center pt-8 pb-4 animate-in fade-in duration-700 relative z-10">
                        {/* Emblem and Official Badge */}
                        <div className="flex flex-col items-center gap-3 mb-6">
                          <div className="inline-flex items-center gap-2 rounded-full bg-amber-50 px-4 py-1.5 border border-amber-200/50 shadow-sm">
                            <Zap className="w-3.5 h-3.5 text-[#FF9933]" />
                            <span className="text-[10px] font-bold uppercase tracking-widest text-[#0B4C8C]">Official Policy & Scheme Assistant</span>
                          </div>
                        </div>

                        {/* Title and Subtitle */}
                        <h1 className="text-4xl md:text-5xl font-black tracking-tight text-center leading-tight text-slate-900 max-w-3xl">
                          West Bengal <span className="text-gradient-navy-gold">Finance Department</span>
                        </h1>

                        {/* Premium Large Centered Voice Hub */}
                        <div className="mt-8 flex flex-col items-center gap-5 animate-in fade-in slide-in-from-bottom-3 duration-500">
                          {/* Centered Large Circular Mic Button */}
                          <div className="relative group">
                            {/* Outer animated rings when recording */}
                            {isRecording && (
                              <>
                                <span 
                                  className="absolute -inset-4 rounded-full bg-rose-500/10 animate-ping" 
                                  style={{ animationDuration: '1500ms' }}
                                />
                                <span 
                                  className="absolute -inset-8 rounded-full bg-rose-500/5 animate-pulse" 
                                  style={{ animationDuration: '2000ms' }}
                                />
                              </>
                            )}
                            {/* Hover glow effect */}
                            <span className="absolute -inset-2 rounded-full bg-gradient-to-tr from-[#0B4C8C] to-[#1e5d9f] opacity-20 blur-md group-hover:opacity-35 transition duration-300" />
                            
                            <Button
                              onClick={isRecording ? handleStopRecording : handleStartRecording}
                              disabled={querying || isTranscribing}
                              className={`relative w-24 h-24 rounded-full p-0 flex items-center justify-center transition-all duration-300 shadow-lg border-4
                                ${isRecording 
                                  ? 'bg-rose-500/10 hover:bg-rose-500/20 border-rose-400 text-rose-500 shadow-rose-200/50' 
                                  : 'bg-[#0B4C8C]/10 hover:bg-[#0B4C8C]/20 border-[#0B4C8C]/30 text-[#0B4C8C] hover:scale-105 active:scale-95 shadow-blue-100/50'
                                }`}
                              title={isRecording ? "Stop recording" : "Start voice input"}
                            >
                              {isRecording ? (
                                <Square className="w-10 h-10 fill-current animate-pulse" />
                              ) : (
                                <Mic className="w-12 h-12" />
                              )}
                            </Button>
                          </div>

                          {/* Subtle Language Selector Below Mic */}
                          <div className="flex items-center gap-2 mt-1 bg-white border border-slate-200/70 px-4 py-2 rounded-full shadow-sm">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Language:</span>
                            <select
                              value={voiceLanguage}
                              onChange={(e) => setVoiceLanguage((e.target.value as 'en-IN' | 'hi-IN'))}
                              className="bg-transparent text-[11px] font-bold text-slate-700 outline-none cursor-pointer hover:text-slate-900 transition-colors"
                              aria-label="Voice language"
                            >
                              <option value="en-IN">English (EN)</option>
                              <option value="hi-IN">Hindi (HI)</option>
                            </select>
                          </div>

                          {isRecording && (
                            <p className="text-[10px] font-bold text-rose-500 uppercase tracking-widest animate-pulse mt-1">
                              Listening... Speak now
                            </p>
                          )}
                        </div>


                        {/* Centered Search Bar */}
                        <div className="mt-10 w-full flex justify-center animate-fade-in-up">
                          {renderQueryBar(true)}
                        </div>

                        {/* Suggestions Grid */}
                        <div className="mt-14 w-full max-w-[950px] space-y-10 animate-fade-in-up">
                          <div>
                            <div className="flex items-center justify-center gap-3 mb-5">
                              <div className="h-[2px] w-8 bg-gradient-to-r from-transparent to-[#FF9933]" />
                              <h2 className="text-[11px] font-extrabold uppercase tracking-[0.2em] text-slate-400">Key Welfare Schemes</h2>
                              <div className="h-[2px] w-8 bg-gradient-to-l from-transparent to-[#138808]" />
                            </div>
                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                              {SUGGESTIONS[0].items.map((item, idx) => (
                                <div 
                                  key={idx}
                                  onClick={() => {
                                    setQuery(item.query);
                                    handleQuery(item.query);
                                  }}
                                  className="glass-card hover:border-[#D4AF37]/50 border-slate-200/60 p-5 rounded-2xl cursor-pointer hover:shadow-md transition-all duration-300 flex flex-col justify-between h-full group card-premium-shadow bg-white/70 hover:bg-white"
                                >
                                  <div>
                                    <div className="text-2xl mb-3 group-hover:scale-110 transition-transform duration-300 w-fit">{item.icon}</div>
                                    <h3 className="font-bold text-slate-800 text-sm mb-1 group-hover:text-[#0B4C8C] transition-colors">{item.title}</h3>
                                    <p className="text-[11px] text-slate-500 leading-relaxed font-medium">{item.description}</p>
                                  </div>
                                  <div className="mt-4 flex items-center text-[10px] font-bold text-[#0B4C8C] group-hover:translate-x-1 transition-transform">
                                    Query Scheme →
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>

                          <div>
                            <div className="flex items-center justify-center gap-3 mb-5">
                              <div className="h-[2px] w-8 bg-gradient-to-r from-transparent to-[#D4AF37]" />
                              <h2 className="text-[11px] font-extrabold uppercase tracking-[0.2em] text-slate-400">Treasury & Finance Policy</h2>
                              <div className="h-[2px] w-8 bg-gradient-to-l from-transparent to-[#D4AF37]" />
                            </div>
                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                              {SUGGESTIONS[1].items.map((item, idx) => (
                                <div 
                                  key={idx}
                                  onClick={() => {
                                    setQuery(item.query);
                                    handleQuery(item.query);
                                  }}
                                  className="glass-card hover:border-[#D4AF37]/50 border-slate-200/60 p-5 rounded-2xl cursor-pointer hover:shadow-md transition-all duration-300 flex flex-row items-center gap-4 h-full group card-premium-shadow bg-white/70 hover:bg-white"
                                >
                                  <div className="text-3xl p-3 bg-slate-50 rounded-xl group-hover:scale-115 transition-transform duration-300 shrink-0">{item.icon}</div>
                                  <div className="flex-1 min-w-0">
                                    <h3 className="font-bold text-slate-800 text-sm mb-0.5 group-hover:text-[#0B4C8C] transition-colors">{item.title}</h3>
                                    <p className="text-[11px] text-slate-500 leading-relaxed font-medium">{item.description}</p>
                                  </div>
                                  <div className="text-[#0B4C8C] font-bold text-sm shrink-0 group-hover:translate-x-1 transition-transform pr-2">→</div>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Chat Conversational History Stream */}
                    {chatHistory.length > 0 && (
                      <div className="space-y-8 flex flex-col">
                        {chatHistory.map((message, messageIndex) => {
                          if (message.role === 'user') {
                            return (
                              <div key={`user-${messageIndex}`} className="flex justify-end animate-in slide-in-from-bottom-2 duration-300">
                                <div className="bg-slate-900 text-white rounded-3xl rounded-tr-none px-6 py-4 max-w-[92%] lg:max-w-[85%] shadow-sm hover:shadow-md transition-shadow">
                                  <p className="text-sm font-semibold tracking-wide leading-relaxed">{message.content}</p>
                                </div>
                              </div>
                            )
                          }

                          // Assistant Turn Card
                          const resData = message.result
                          if (!resData) return null

                          return (
                            <div key={`assistant-${messageIndex}`} className="flex justify-start animate-in fade-in duration-500">
                              <Card className="w-full bg-white border border-slate-100 p-6 rounded-3xl shadow-sm space-y-6">
                                {resData.weak_claims && resData.weak_claims.length > 0 && (
                                  <Card className="rounded-2xl border-amber-100 bg-amber-50/80 p-4">
                                    <p className="text-[10px] font-bold uppercase tracking-widest text-amber-700 mb-2">Evidence Warnings</p>
                                    <div className="space-y-1">
                                      {resData.weak_claims.map((claim, index) => (
                                        <p key={`${claim}-${index}`} className="text-sm font-medium text-amber-900">{claim}</p>
                                      ))}
                                    </div>
                                  </Card>
                                )}

                                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
                                  <div className="space-y-1">
                                    <p className="text-[10px] font-bold uppercase tracking-[0.4em] text-slate-300">Analysis Output</p>
                                    <p className="text-[10px] text-slate-400 font-medium">Verified RAG Synthesis</p>
                                  </div>
                                  <div className="flex flex-wrap items-center gap-2">
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      onClick={() => handleSpeakAnswer(messageIndex, resData.answer)}
                                      disabled={speakingMessageIndex === messageIndex}
                                      className="h-7 rounded-full px-3 text-[10px] font-bold uppercase tracking-wide"
                                    >
                                      {speakingMessageIndex === messageIndex ? (
                                        <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                                      ) : (
                                        <Volume2 className="w-3 h-3 mr-1" />
                                      )}
                                      Speak
                                    </Button>
                                    {speakingMessageIndex === messageIndex && (
                                      <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={handleStopSpeaking}
                                        className="h-7 rounded-full px-3 text-[10px] font-bold uppercase tracking-wide"
                                      >
                                        <Square className="w-3 h-3 mr-1" />
                                        Stop
                                      </Button>
                                    )}

                                    <TooltipProvider>
                                      <Tooltip>
                                        <TooltipTrigger asChild>
                                          <div className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-bold border shadow-sm cursor-help transition-colors
                                            ${resData.graph_enrichment_used 
                                              ? 'bg-blue-50 text-blue-700 border-blue-100/60 hover:bg-blue-100/50' 
                                              : 'bg-slate-50 text-slate-500 border-slate-100 hover:bg-slate-100/50'}`}
                                          >
                                            <Network className={`w-3.5 h-3.5 ${resData.graph_enrichment_used ? 'text-blue-500' : 'text-slate-400'}`} />
                                            <span>{resData.graph_enrichment_used ? 'Graph Active' : 'Vector Only'}</span>
                                          </div>
                                        </TooltipTrigger>
                                        <TooltipContent className="bg-slate-950 text-white border-none p-3 rounded-xl shadow-2xl max-w-xs">
                                          <p className="font-bold text-xs mb-1">Knowledge Graph Integration</p>
                                          <p className="text-[10px] text-slate-400 font-medium">
                                            {resData.graph_enrichment_used 
                                              ? 'Relational graph query was automatically triggered to enrich this answer with multi-hop connections.'
                                              : 'Answer synthesizes vectorized document chunks only.'}
                                          </p>
                                        </TooltipContent>
                                      </Tooltip>
                                    </TooltipProvider>
                                  </div>
                                </div>

                                <div className="prose prose-slate max-w-none text-[15px] leading-[1.8] text-slate-800 font-medium border-l-4 border-slate-900 pl-8 transition-all hover:bg-slate-50/50 py-2 rounded-r-2xl
                                   prose-headings:text-slate-900 prose-headings:font-bold prose-h1:text-xl prose-h2:text-lg prose-h3:text-base
                                   prose-p:mb-4 prose-ul:list-disc prose-ul:pl-6 prose-li:mb-1">
                                  <ReactMarkdown
                                    remarkPlugins={[remarkGfm]}
                                    components={{
                                      a: ({ node, ...props }) => {
                                        const isSource = props.href?.startsWith('#source-');
                                        if (isSource && resData) {
                                          const index = parseInt(props.href!.split('-')[1]) - 1;
                                          const source = resData.sources[index];
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
                                      table: ({ node, ...props }) => (
                                        <div className="my-6 overflow-hidden rounded-2xl border border-slate-200/60 shadow-md bg-white max-w-full overflow-x-auto relative">
                                          <div className="h-[3px] w-full bg-gradient-to-r from-[#FF9933] via-[#0B4C8C] to-[#138808]" />
                                          <table {...props} className="w-full border-collapse text-left text-xs" />
                                        </div>
                                      ),
                                      thead: ({ node, ...props }) => (
                                        <thead {...props} className="bg-gradient-to-r from-[#0B4C8C] to-[#12589d] text-white text-[10px] font-extrabold uppercase tracking-wider border-b border-[#0B4C8C]/20" />
                                      ),
                                      tr: ({ node, ...props }) => (
                                        <tr {...props} className="border-b border-slate-100/80 last:border-0 hover:bg-[#0B4C8C]/5 transition-colors duration-150 odd:bg-white even:bg-slate-50/40" />
                                      ),
                                      th: ({ node, ...props }) => (
                                        <th {...props} className="p-3.5 font-extrabold text-white align-middle border-r border-white/10 last:border-r-0">
                                          {renderWithLineBreaksAndCitations(props.children, resData.sources || [], setSelectedSource)}
                                        </th>
                                      ),
                                      td: ({ node, ...props }) => (
                                        <td {...props} className="p-3.5 text-slate-700 font-semibold align-middle leading-normal border-r border-slate-100/60 last:border-r-0">
                                          {renderWithLineBreaksAndCitations(props.children, resData.sources || [], setSelectedSource)}
                                        </td>
                                      ),
                                      p: ({ node, ...props }) => <p {...props}>{renderWithLineBreaksAndCitations(props.children, resData.sources || [], setSelectedSource)}</p>,
                                      li: ({ node, ...props }) => <li {...props}>{renderWithLineBreaksAndCitations(props.children, resData.sources || [], setSelectedSource)}</li>
                                    }}
                                  >
                                    {resData.answer}
                                  </ReactMarkdown>
                                </div>

                              </Card>
                            </div>
                          )
                        })}
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

                    {/* Pulse Loading Indicator */}
                    {querying && <RAGLoader />}

                    {/* Auto-scroll target */}
                    <div ref={chatEndRef} />
                  </div>
                </ScrollArea>

                {/* Fixed Query Bar Area */}
                {(chatHistory.length > 0 || querying) && (
                  <div className="absolute bottom-10 left-10 right-10 z-20">
                    {renderQueryBar(false)}
                  </div>
                )}
              </TabsContent>

              <TabsContent value="map" className="flex-1 relative overflow-hidden min-h-0 mt-0 m-0 p-0 outline-none border-none bg-[linear-gradient(140deg,#fffdf8_0%,#f7f2e9_36%,#edf4ff_72%,#f8fbff_100%)] h-full min-h-[700px] data-[state=inactive]:hidden data-[state=active]:block">
                {renderCivicBackdrop()}
                {loadingGraph ? (
                  <div className="relative z-10 flex flex-col items-center justify-center h-full gap-6">
                    <div className="relative">
                      <Loader2 className="w-16 h-16 text-slate-900 animate-spin" />
                      <Network className="absolute inset-0 m-auto w-6 h-6 text-slate-900" />
                    </div>
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.4em] animate-pulse">Mapping Relational Intelligence...</p>
                  </div>
                ) : (
                  <div ref={mapContainerRef} className="absolute inset-0 z-10 w-full h-full cursor-grab active:cursor-grabbing">
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
                      backgroundColor="rgba(0,0,0,0)"
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










