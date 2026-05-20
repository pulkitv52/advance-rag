import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import axios from "axios"

import { Badge } from "./ui/badge"
import { Button } from "./ui/button"
import { Card } from "./ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "./ui/dialog"
import { Input } from "./ui/input"

interface EligibilityStudioProps {
  API: string
}

interface DocumentRow {
  id: string
  filename: string
  status: string
  sub_status?: string
  progress_percent?: number
}

interface RuleRow {
  id: string
  scheme_id: string
  rule_name: string
  rule_version: number
  include_conditions: Record<string, unknown>
  exclude_conditions: Record<string, unknown>
  extracted_metadata?: Record<string, any>
  canonical_rule?: CanonicalRule
  source_filename?: string
  created_at?: string
}

interface CanonicalCondition {
  field: string
  operator: string
  value?: unknown
  value_type?: string | null
  evidence_quote?: string | null
}

interface UnmappedCondition {
  requirement: string
  suggested_input_field: string
  input_type: "boolean" | "number" | "text" | "select"
  reason_unmapped: string
  evidence_quote?: string | null
}

interface CanonicalRule {
  scheme_id: string
  rule_name: string
  include_conditions: CanonicalCondition[]
  exclude_conditions: CanonicalCondition[]
  unmapped_conditions: UnmappedCondition[]
}

interface ManualInputRequirement {
  field: string
  input_type: "boolean" | "number" | "text" | "select"
  reason?: string
  requirement?: string
}

interface DecisionRow {
  id: string
  citizen_uid: string
  citizen_name?: string | null
  citizen_scheme_id?: string | null
  decision: "INCLUSION_ERROR" | "EXCLUSION_ERROR" | "VALID_ENROLLMENT" | "NOT_APPLICABLE" | "REVIEW_REQUIRED"
  decision_bucket?: string
  reason: string
  decision_confidence: number
  evidence_json?: {
    checks?: Array<{
      field?: string
      operator?: string
      expected?: unknown
      actual?: unknown
      passed?: boolean
    }>
    source_values?: Record<string, unknown>
    checked_fields?: string[]
    missing_required_fields?: string[]
    blocking_unmapped_criteria?: string[]
    manual_inputs?: Record<string, unknown>
    canonical_rule?: CanonicalRule
  }
  suggested_manual_fields?: string[]
  manual_input_requirements?: ManualInputRequirement[]
  created_at?: string
}

interface EvaluationSummary {
  rule_id: string
  scheme_id: string
  evaluated: number
  decisions_saved: number
  counts: Record<string, number>
  bucket_counts?: Record<string, number>
  bucket_mapping?: Record<string, string>
  evaluation_basis?: {
    message?: string
    executable_include_fields?: string[]
    executable_exclude_fields?: string[]
    unmapped_criteria?: string[]
    no_population_found?: boolean
    no_population_reason?: string | null
  }
  preview: Array<{
    uid: string
    scheme_id: string
    decision: string
    reason: string
    decision_confidence: number
  }>
}

const inferSchemeIdFromFilename = (filename: string): string => {
  const upper = String(filename || "").toUpperCase()
  const match = upper.match(/(?:^|[^A-Z0-9])(SS_\d{2,6}|S\d{2,6}|C\d{2,6})(?:[^A-Z0-9]|$)/)
  return match ? match[1] : ""
}

const decisionColor: Record<string, string> = {
  INCLUSION_ERROR: "bg-rose-100 text-rose-700",
  EXCLUSION_ERROR: "bg-amber-100 text-amber-700",
  VALID_ENROLLMENT: "bg-emerald-100 text-emerald-700",
  NOT_APPLICABLE: "bg-slate-100 text-slate-700",
  REVIEW_REQUIRED: "bg-violet-100 text-violet-700",
}

const bucketLabel: Record<string, string> = {
  ELIGIBLE_ENROLLED: "Eligible + Enrolled",
  NOT_ELIGIBLE_ENROLLED: "Not Eligible + Enrolled",
  ELIGIBLE_NOT_ENROLLED: "Eligible + Not Enrolled",
  NOT_ELIGIBLE_NOT_ENROLLED: "Not Eligible + Not Enrolled",
  REVIEW_REQUIRED: "Review Required",
}

const formatValue = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "-"
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

const buildDecisionBasis = (row: DecisionRow): string => {
  const checks = row.evidence_json?.checks || []
  if (checks.length > 0) {
    const top = checks.slice(0, 3).map((c) => {
      const field = c.field || "field"
      const operator = c.operator || "op"
      const expected = formatValue(c.expected)
      const actual = formatValue(c.actual)
      return `${field} ${operator} ${expected} (actual=${actual})`
    })
    return top.join(" | ")
  }

  const src = row.evidence_json?.source_values || {}
  const quickKeys = ["scheme_id", "employment_status", "annual_income", "caste", "closing_date"]
  const parts = quickKeys
    .filter((k) => src[k] !== undefined && src[k] !== null && src[k] !== "")
    .map((k) => `${k}=${formatValue(src[k])}`)
  return parts.length > 0 ? parts.join(" | ") : "No check-level evidence captured."
}

const getCanonicalRule = (rule: RuleRow | null | undefined): CanonicalRule | null => {
  if (!rule) return null
  return rule.canonical_rule || rule.extracted_metadata?.canonical_rule || null
}

const describeCondition = (condition: CanonicalCondition): string => {
  const valuePart = condition.value === undefined ? "" : ` ${formatValue(condition.value)}`
  return `${condition.field} ${condition.operator}${valuePart}`
}

export function EligibilityStudio({ API }: EligibilityStudioProps) {
  const [documents, setDocuments] = useState<DocumentRow[]>([])
  const [rules, setRules] = useState<RuleRow[]>([])
  const [decisions, setDecisions] = useState<DecisionRow[]>([])

  const [selectedDocumentId, setSelectedDocumentId] = useState("")
  const [schemeId, setSchemeId] = useState("")
  const [selectedRuleId, setSelectedRuleId] = useState("")
  const [runLimit, setRunLimit] = useState("500")

  const [extracting, setExtracting] = useState(false)
  const [evaluating, setEvaluating] = useState(false)
  const [uploadingPolicy, setUploadingPolicy] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [loadingRules, setLoadingRules] = useState(false)
  const [loadingDecisions, setLoadingDecisions] = useState(false)
  const [showAllDecisions, setShowAllDecisions] = useState(false)

  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [latestSummary, setLatestSummary] = useState<EvaluationSummary | null>(null)
  const [operationLabel, setOperationLabel] = useState("")
  const [operationProgress, setOperationProgress] = useState(0)
  const [operationActive, setOperationActive] = useState(false)
  const [editingDecisionId, setEditingDecisionId] = useState<string | null>(null)
  const [savingManual, setSavingManual] = useState(false)
  const [manualInputDrafts, setManualInputDrafts] = useState<Record<string, Record<string, string>>>({})
  const progressTimerRef = useRef<number | null>(null)
  const uploadInputRef = useRef<HTMLInputElement | null>(null)
  const [trackedUploadDocId, setTrackedUploadDocId] = useState<string | null>(null)
  const lastAutoFilledDocIdRef = useRef<string | null>(null)

  const readyDocuments = useMemo(
    () => documents.filter((doc) => doc.status === "success"),
    [documents],
  )

  const beginOperationProgress = (label: string) => {
    if (progressTimerRef.current) {
      window.clearInterval(progressTimerRef.current)
    }
    setOperationLabel(label)
    setOperationProgress(8)
    setOperationActive(true)

    progressTimerRef.current = window.setInterval(() => {
      setOperationProgress((prev) => Math.min(prev + 6, 90))
    }, 500)
  }

  const advanceOperationProgress = (label: string, progress: number) => {
    setOperationLabel(label)
    setOperationProgress(Math.max(progress, operationProgress))
  }

  const completeOperationProgress = (label: string) => {
    if (progressTimerRef.current) {
      window.clearInterval(progressTimerRef.current)
      progressTimerRef.current = null
    }
    setOperationLabel(label)
    setOperationProgress(100)
    window.setTimeout(() => {
      setOperationActive(false)
      setOperationLabel("")
      setOperationProgress(0)
    }, 900)
  }

  const loadDocuments = useCallback(async (silent = false) => {
    if (!silent) setLoadingDocs(true)
    try {
      const res = await axios.get(`${API}/documents/`)
      const docs = (res.data?.documents || []) as DocumentRow[]
      setDocuments(docs)
      if (!selectedDocumentId && docs.length > 0) {
        const firstReady = docs.find((d) => d.status === "success")
        if (firstReady) setSelectedDocumentId(firstReady.id)
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to load documents")
    } finally {
      if (!silent) setLoadingDocs(false)
    }
  }, [API, selectedDocumentId])

  const loadRules = useCallback(async (scheme?: string, silent = false) => {
    if (!silent) setLoadingRules(true)
    try {
      const params = new URLSearchParams()
      if (scheme) params.set("scheme_id", scheme)
      const query = params.toString()
      const res = await axios.get(`${API}/api/eligibility/rules${query ? `?${query}` : ""}`)
      const rows = (res.data?.rules || []) as RuleRow[]
      setRules(rows)
      if (!selectedRuleId && rows.length > 0) {
        setSelectedRuleId(rows[0].id)
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to load rules")
    } finally {
      if (!silent) setLoadingRules(false)
    }
  }, [API, selectedRuleId])

  const loadDecisions = useCallback(async (ruleId?: string, silent = false) => {
    const targetRule = showAllDecisions ? "" : (ruleId || selectedRuleId)
    if (!showAllDecisions && !targetRule) return

    if (!silent) setLoadingDecisions(true)
    try {
      const url = targetRule
        ? `${API}/api/eligibility/decisions?rule_id=${targetRule}&limit=200`
        : `${API}/api/eligibility/decisions?limit=200`
      const res = await axios.get(url)
      setDecisions((res.data?.decisions || []) as DecisionRow[])
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to load decisions")
    } finally {
      if (!silent) setLoadingDecisions(false)
    }
  }, [API, selectedRuleId, showAllDecisions])

  const handleExtract = async () => {
    if (!selectedDocumentId) {
      setError("Select a processed document.")
      return
    }

    setExtracting(true)
    setError(null)
    setSuccess(null)
    beginOperationProgress("Reading policy document and extracting rule metadata...")

    try {
      advanceOperationProgress("Parsing document text...", 25)
      const res = await axios.post(`${API}/api/eligibility/rules/extract/${selectedDocumentId}`, {
        scheme_id: schemeId.trim() || undefined,
      })
      advanceOperationProgress("Saving extracted criteria and refreshing rules...", 70)
      setSuccess(`Rule extracted: ${res.data?.rule_name} (version ${res.data?.rule_version})`)
      if (res.data?.scheme_id) {
        setSchemeId(String(res.data.scheme_id))
      }
      await loadRules(res.data?.scheme_id || undefined)
      if (res.data?.rule_id) {
        setSelectedRuleId(res.data.rule_id)
      }
      completeOperationProgress("Eligibility metadata extraction completed.")
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Rule extraction failed")
      completeOperationProgress("Extraction failed.")
    } finally {
      setExtracting(false)
    }
  }

  const handlePolicyUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return

    const file = files[0]
    setUploadingPolicy(true)
    setUploadProgress(0)
    setError(null)
    setSuccess(null)
    setOperationActive(true)
    setOperationLabel(`Uploading ${file.name}...`)
    setOperationProgress(5)

    if (progressTimerRef.current) {
      window.clearInterval(progressTimerRef.current)
      progressTimerRef.current = null
    }

    try {
      const form = new FormData()
      form.append("files", file)
      form.append("auto_extract_eligibility", "true")

      const res = await axios.post(`${API}/documents/upload`, form, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (evt) => {
          if (!evt.total) return
          const pct = Math.min(100, Math.round((evt.loaded / evt.total) * 100))
          setUploadProgress(pct)
          // Reserve first 35% for file transfer.
          setOperationProgress(Math.max(5, Math.min(35, Math.round(pct * 0.35))))
          setOperationLabel(`Uploading ${file.name} (${pct}%)`)
        },
      })

      const docId = res.data?.documents?.[0]?.document_id as string | undefined
      if (docId) {
        setTrackedUploadDocId(docId)
        setSelectedDocumentId(docId)
      }

      setOperationLabel("Upload complete. Processing document, extracting text, and generating eligibility metadata...")
      setOperationProgress(40)
      setSuccess(
        "Document uploaded. Auto-detection + metadata extraction started in background. Track status below.",
      )
      await loadDocuments()
    } catch (e: any) {
      setOperationLabel("Upload failed.")
      setOperationProgress(100)
      setError(e?.response?.data?.detail || "Policy upload failed")
      window.setTimeout(() => {
        setOperationActive(false)
        setOperationLabel("")
        setOperationProgress(0)
      }, 900)
    } finally {
      setUploadingPolicy(false)
      setUploadProgress(0)
      if (uploadInputRef.current) {
        uploadInputRef.current.value = ""
      }
    }
  }

  const handleEvaluate = async () => {
    if (!selectedRuleId) {
      setError("Select a rule first.")
      return
    }

    setEvaluating(true)
    setError(null)
    setSuccess(null)
    beginOperationProgress("Starting eligibility evaluation over citizen dump...")

    try {
      const lim = Math.max(1, Number.parseInt(runLimit || "500", 10) || 500)
      advanceOperationProgress(`Evaluating ${lim.toLocaleString()} citizens...`, 30)
      const res = await axios.post(`${API}/api/eligibility/evaluate/${selectedRuleId}?limit=${lim}&scheme_only=true`)
      advanceOperationProgress("Saving decisions and loading latest rows...", 80)
      setLatestSummary(res.data as EvaluationSummary)
      setSuccess("Evaluation run completed.")
      await loadDecisions(selectedRuleId)
      completeOperationProgress("Evaluation completed successfully.")
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Evaluation failed")
      completeOperationProgress("Evaluation failed.")
    } finally {
      setEvaluating(false)
    }
  }

  const handleEvaluateAllRules = async () => {
    setEvaluating(true)
    setError(null)
    setSuccess(null)
    beginOperationProgress("Running eligibility evaluation for all active rules...")
    try {
      const lim = Math.max(1, Number.parseInt(runLimit || "500", 10) || 500)
      const res = await axios.post(`${API}/api/eligibility/evaluate-all?limit=${lim}&scheme_only=true`)
      const totalRules = Number(res.data?.total_rules || 0)
      setSuccess(`Evaluation completed for ${totalRules} active rules.`)
      setShowAllDecisions(true)
      await loadDecisions(undefined)
      completeOperationProgress("Evaluation for all rules completed.")
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Evaluate-all failed")
      completeOperationProgress("Evaluate-all failed.")
    } finally {
      setEvaluating(false)
    }
  }

  const parseManualInputValue = (
    raw: string,
    inputType: "boolean" | "number" | "text" | "select" = "text",
  ): unknown => {
    const v = raw.trim()
    if (!v) return null
    if (inputType === "text" || inputType === "select") return v
    if (inputType === "number") {
      if (!Number.isNaN(Number(v)) && /^-?\d+(\.\d+)?$/.test(v)) return Number(v)
      return v
    }
    const upper = v.toUpperCase()
    if (["TRUE", "YES", "Y", "1"].includes(upper)) return true
    if (["FALSE", "NO", "N", "0"].includes(upper)) return false
    return v
  }

  const handleRejudge = async (row: DecisionRow) => {
    const draft = manualInputDrafts[row.id] || {}
    const requirementByField = new Map(
      (row.manual_input_requirements || []).map((req) => [req.field, req.input_type] as const),
    )
    const manual_inputs: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(draft)) {
      if (v.trim()) {
        manual_inputs[k] = parseManualInputValue(v, requirementByField.get(k) || "text")
      }
    }

    try {
      setSavingManual(true)
      const res = await axios.post(`${API}/api/eligibility/decisions/${row.id}/manual-inputs`, {
        manual_inputs,
        scheme_only: true,
      })
      const updated = res.data as DecisionRow
      setDecisions((prev) => prev.map((d) => (d.id === row.id ? { ...d, ...updated } : d)))
      setSuccess(`Decision updated for UID ${row.citizen_uid} using manual inputs.`)
      setError(null)
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to apply manual inputs")
    } finally {
      setSavingManual(false)
    }
  }

  const activeEditingRow = useMemo(
    () => decisions.find((d) => d.id === editingDecisionId) || null,
    [decisions, editingDecisionId],
  )
  const activeManualRequirements = useMemo(
    () => (activeEditingRow?.manual_input_requirements || []).filter((f) => f?.field && f.field.trim()),
    [activeEditingRow],
  )
  const activeRemainingMissingFields = useMemo(
    () =>
      (activeEditingRow?.evidence_json?.missing_required_fields || []).filter(
        (f) => f && String(f).trim(),
      ),
    [activeEditingRow],
  )
  const activeRemainingUnmapped = useMemo(
    () =>
      (activeEditingRow?.evidence_json?.blocking_unmapped_criteria || []).filter(
        (f) => f && String(f).trim(),
      ),
    [activeEditingRow],
  )

  useEffect(() => {
    void loadDocuments()
    void loadRules()
    return () => {
      if (progressTimerRef.current) {
        window.clearInterval(progressTimerRef.current)
      }
    }
  }, [loadDocuments, loadRules])

  useEffect(() => {
    if (!selectedDocumentId) return
    if (lastAutoFilledDocIdRef.current === selectedDocumentId) return

    const selectedDoc = documents.find((doc) => doc.id === selectedDocumentId)
    if (!selectedDoc) return

    const inferred = inferSchemeIdFromFilename(selectedDoc.filename)
    setSchemeId(inferred)
    lastAutoFilledDocIdRef.current = selectedDocumentId
  }, [documents, selectedDocumentId])

  useEffect(() => {
    const timer = window.setInterval(() => {
      void loadDocuments(true)

      if (extracting) {
        void loadRules(schemeId.trim() || undefined, true)
      }

      if (selectedRuleId && (evaluating || operationActive)) {
        void loadDecisions(selectedRuleId, true)
      }
    }, 4000)

    return () => window.clearInterval(timer)
  }, [
    loadDocuments,
    loadRules,
    loadDecisions,
    selectedRuleId,
    evaluating,
    operationActive,
    extracting,
    schemeId,
  ])

  useEffect(() => {
    if (!trackedUploadDocId) return

    const doc = documents.find((d) => d.id === trackedUploadDocId)
    if (!doc) return

    if (doc.status === "pending" || doc.status === "processing") {
      const p = doc.progress_percent ?? 0
      setOperationActive(true)
      setOperationLabel(
        doc.sub_status
          ? `Processing: ${doc.sub_status}`
          : "Processing document and extracting eligibility metadata...",
      )
      setOperationProgress(Math.max(40, Math.min(95, p)))
      return
    }

    if (doc.status === "success") {
      setOperationLabel("Document processed and eligibility metadata extraction completed.")
      setOperationProgress(100)
      setSuccess("Smart extraction finished. Review extracted rule in the Rule dropdown.")
      setTrackedUploadDocId(null)
      window.setTimeout(() => {
        setOperationActive(false)
        setOperationLabel("")
        setOperationProgress(0)
      }, 1000)
      void loadRules(schemeId.trim() || undefined, true)
      return
    }

    if (doc.status === "failed") {
      setOperationLabel("Document processing failed.")
      setOperationProgress(100)
      setTrackedUploadDocId(null)
      window.setTimeout(() => {
        setOperationActive(false)
        setOperationLabel("")
        setOperationProgress(0)
      }, 1000)
    }
  }, [documents, trackedUploadDocId, loadRules, schemeId])

  return (
    <div className="h-full overflow-auto bg-slate-50/40 p-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <Card className="rounded-3xl border-slate-200 bg-white p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.25em] text-slate-400">Eligibility Studio</p>
              <h2 className="mt-1 text-2xl font-black text-slate-900">PDF to Metadata to Inclusion/Exclusion</h2>
              <p className="mt-2 text-sm text-slate-600">
                Select a policy document, extract eligibility metadata for a scheme, and evaluate citizens from dump data.
              </p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" className="rounded-xl" onClick={() => { void loadDocuments() }} disabled={loadingDocs}>
                {loadingDocs ? "Refreshing..." : "Refresh Documents"}
              </Button>
              <Button variant="outline" className="rounded-xl" onClick={() => loadRules(schemeId.trim())} disabled={loadingRules}>
                {loadingRules ? "Loading..." : "Refresh Rules"}
              </Button>
            </div>
          </div>
        </Card>

        {error && (
          <Card className="rounded-2xl border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">{error}</Card>
        )}
        {success && (
          <Card className="rounded-2xl border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">{success}</Card>
        )}
        {operationActive && (
          <Card className="rounded-2xl border-sky-200 bg-sky-50 p-4">
            <div className="flex items-center justify-between gap-4">
              <p className="text-sm font-semibold text-sky-800">{operationLabel}</p>
              <p className="text-xs font-bold text-sky-700">{operationProgress}%</p>
            </div>
            <div className="mt-3 h-2 w-full rounded-full bg-sky-100">
              <div
                className="h-2 rounded-full bg-sky-600 transition-all duration-300"
                style={{ width: `${operationProgress}%` }}
              />
            </div>
          </Card>
        )}

        <div className="grid gap-6 lg:grid-cols-2">
          <Card className="rounded-3xl border-slate-200 bg-white p-6">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Step 1: Extract Rule</p>
            <div className="mt-4 space-y-3">
              <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-3">
                <p className="text-xs font-semibold text-slate-600">Upload Policy Document (Auto Smart Extraction)</p>
                <p className="mt-1 text-[11px] text-slate-500">
                  Upload PDF/DOCX and system auto-detects scheme + eligibility metadata. Scheme ID below is optional as override hint.
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <input
                    ref={uploadInputRef}
                    type="file"
                    accept=".pdf,.doc,.docx,.txt,.html,.htm"
                    className="hidden"
                    onChange={(e) => { void handlePolicyUpload(e.target.files) }}
                  />
                  <Button
                    variant="outline"
                    className="rounded-xl"
                    disabled={uploadingPolicy}
                    onClick={() => uploadInputRef.current?.click()}
                  >
                    {uploadingPolicy ? "Uploading..." : "Upload Policy"}
                  </Button>
                  {uploadingPolicy && (
                    <p className="text-xs font-semibold text-slate-500">Upload progress: {uploadProgress}%</p>
                  )}
                </div>
              </div>

              <div>
                <p className="mb-1 text-xs font-semibold text-slate-500">Policy Document (ingested)</p>
                <select
                  value={selectedDocumentId}
                  onChange={(e) => setSelectedDocumentId(e.target.value)}
                  className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 outline-none"
                >
                  <option value="">Select document</option>
                  {readyDocuments.map((doc) => (
                    <option key={doc.id} value={doc.id}>
                      {doc.filename}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <p className="mb-1 text-xs font-semibold text-slate-500">Scheme ID (optional override)</p>
                <Input value={schemeId} onChange={(e) => setSchemeId(e.target.value)} placeholder="Auto-detect from filename/text (e.g., S767)" className="rounded-xl" />
              </div>

              <Button className="w-full rounded-xl" onClick={handleExtract} disabled={extracting || !selectedDocumentId}>
                {extracting ? "Extracting metadata..." : "Extract Eligibility Metadata"}
              </Button>

              {readyDocuments.length === 0 && (
                <p className="text-xs font-medium text-slate-500">No successful documents found yet. Upload and wait for processing to complete.</p>
              )}
            </div>
          </Card>

          <Card className="rounded-3xl border-slate-200 bg-white p-6">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Extracted Rule Metadata</p>
            {selectedRuleId ? (
              (() => {
                const rule = rules.find((r) => r.id === selectedRuleId)
                if (!rule) {
                  return <p className="mt-3 text-sm text-slate-500">Rule not found in current list.</p>
                }
                return (
                  <div className="mt-4 space-y-4">
                    <div className="flex flex-wrap gap-2">
                      <Badge className="bg-slate-900 text-white">{rule.scheme_id}</Badge>
                      <Badge className="bg-slate-100 text-slate-700">v{rule.rule_version}</Badge>
                      <Badge className="bg-slate-100 text-slate-700">{rule.rule_name}</Badge>
                    </div>
                    <div>
                      <p className="mb-1 text-xs font-bold uppercase tracking-widest text-slate-400">Canonical Rule JSON</p>
                      <pre className="max-h-52 overflow-auto rounded-xl bg-slate-950 p-3 text-xs text-slate-100">{JSON.stringify(getCanonicalRule(rule), null, 2)}</pre>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                      <p className="text-[11px] font-bold uppercase tracking-widest text-slate-500">Fetched Eligibility Criteria</p>
                      <div className="mt-2 space-y-2 text-sm">
                        {(getCanonicalRule(rule)?.include_conditions || []).length > 0 ? (
                          getCanonicalRule(rule)?.include_conditions.map((condition, idx) => (
                            <p key={`inc-${idx}`} className="text-slate-700">
                              <span className="font-semibold text-slate-900">{describeCondition(condition)}</span>
                              {condition.evidence_quote ? ` — ${condition.evidence_quote}` : ""}
                            </p>
                          ))
                        ) : (
                          <p className="text-slate-500">No mapped include criteria found.</p>
                        )}
                        {(getCanonicalRule(rule)?.exclude_conditions || []).length > 0 && (
                          <>
                            <p className="pt-1 text-[11px] font-bold uppercase tracking-widest text-slate-500">Exclusions</p>
                            {getCanonicalRule(rule)?.exclude_conditions.map((condition, idx) => (
                              <p key={`exc-${idx}`} className="text-slate-700">
                                <span className="font-semibold text-slate-900">{describeCondition(condition)}</span>
                                {condition.evidence_quote ? ` — ${condition.evidence_quote}` : ""}
                              </p>
                            ))}
                          </>
                        )}
                        {(getCanonicalRule(rule)?.unmapped_conditions || []).length > 0 && (
                          <>
                            <p className="pt-1 text-[11px] font-bold uppercase tracking-widest text-slate-500">Manual Review Conditions</p>
                            {getCanonicalRule(rule)?.unmapped_conditions.map((condition, idx) => (
                              <p key={`unmapped-${idx}`} className="text-slate-700">
                                <span className="font-semibold text-slate-900">{condition.requirement}</span>
                                {` -> ${condition.suggested_input_field} (${condition.input_type})`}
                              </p>
                            ))}
                          </>
                        )}
                      </div>
                    </div>
                    {!!rule.extracted_metadata?.document_intent?.summary && (
                      <Card className="rounded-2xl border-sky-200 bg-sky-50 px-3 py-2">
                        <p className="text-xs font-semibold text-sky-700">
                          Document intent: {rule.extracted_metadata.document_intent.summary}
                        </p>
                      </Card>
                    )}
                    {!!rule.extracted_metadata?.evidence?.length && (
                      <div>
                        <p className="mb-1 text-xs font-bold uppercase tracking-widest text-slate-400">Evidence From Document</p>
                        <div className="max-h-52 space-y-2 overflow-auto rounded-xl border border-slate-200 bg-white p-3">
                          {rule.extracted_metadata.evidence.slice(0, 8).map((ev: any, idx: number) => (
                            <div key={`ev-${idx}`} className="rounded-lg border border-slate-100 bg-slate-50 px-2 py-1.5">
                              <p className="text-[11px] font-bold text-slate-700">{ev.field || "field"}</p>
                              <p className="text-xs text-slate-600">{ev.quote || "-"}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {!!rule.extracted_metadata?.detected_criteria?.length && (
                      <div>
                        <p className="mb-1 text-xs font-bold uppercase tracking-widest text-slate-400">Detected Criteria (Dynamic)</p>
                        <div className="max-h-56 space-y-2 overflow-auto rounded-xl border border-slate-200 bg-white p-3">
                          {rule.extracted_metadata.detected_criteria.slice(0, 20).map((dc: any, idx: number) => (
                            <div key={`dc-${idx}`} className="rounded-lg border border-slate-100 bg-slate-50 px-2 py-1.5">
                              <p className="text-[11px] font-bold text-slate-700">
                                {dc.criterion_key}{" "}
                                <span className="font-normal text-slate-500">
                                  [{dc.bucket}] [{dc.status}]
                                </span>
                              </p>
                              {!!dc.suggested_input_field && (
                                <p className="text-[11px] text-sky-700">Suggested input: {dc.suggested_input_field}</p>
                              )}
                              {!!dc.evidence_quote && <p className="text-xs text-slate-600">{dc.evidence_quote}</p>}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {!!(getCanonicalRule(rule)?.unmapped_conditions?.length) && (
                      <Card className="rounded-2xl border-violet-200 bg-violet-50 px-3 py-2">
                        <p className="text-xs font-semibold text-violet-700">
                          Unmapped criteria detected: {(getCanonicalRule(rule)?.unmapped_conditions || []).map((item) => item.suggested_input_field || item.requirement).join(", ")}.
                          Evaluation will be marked REVIEW_REQUIRED until the needed manual inputs are supplied.
                        </p>
                      </Card>
                    )}
                    {(getCanonicalRule(rule)?.include_conditions || []).length === 0 && (getCanonicalRule(rule)?.exclude_conditions || []).length === 0 && (
                      <Card className="rounded-2xl border-amber-200 bg-amber-50 px-3 py-2">
                        <p className="text-xs font-semibold text-amber-700">
                          No usable eligibility criteria were extracted from this document yet. Evaluation will mark rows as REVIEW_REQUIRED.
                        </p>
                      </Card>
                    )}
                  </div>
                )
              })()
            ) : (
              <p className="mt-3 text-sm text-slate-500">Select a rule to inspect metadata.</p>
            )}
          </Card>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card className="rounded-3xl border-slate-200 bg-white p-6">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Step 2: Evaluate Citizens</p>
            <div className="mt-4 space-y-3">
              <div>
                <p className="mb-1 text-xs font-semibold text-slate-500">Rule</p>
                <select
                  value={selectedRuleId}
                  onChange={(e) => setSelectedRuleId(e.target.value)}
                  className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 outline-none"
                >
                  <option value="">Select rule</option>
                  {rules.map((rule) => (
                    <option key={rule.id} value={rule.id}>
                      {rule.rule_name} | {rule.scheme_id} | v{rule.rule_version}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <p className="mb-1 text-xs font-semibold text-slate-500">Run Limit</p>
                <Input value={runLimit} onChange={(e) => setRunLimit(e.target.value)} placeholder="500" className="rounded-xl" />
              </div>

              <Button className="w-full rounded-xl" onClick={handleEvaluate} disabled={evaluating || !selectedRuleId}>
                {evaluating ? "Running evaluation..." : "Run Inclusion/Exclusion Evaluation"}
              </Button>
              <Button
                variant="outline"
                className="w-full rounded-xl"
                onClick={handleEvaluateAllRules}
                disabled={evaluating || rules.length === 0}
              >
                {evaluating ? "Running..." : "Run Evaluation For All Rules"}
              </Button>

              <Button
                variant="outline"
                className="w-full rounded-xl"
                onClick={() => loadDecisions(selectedRuleId)}
                disabled={(!selectedRuleId && !showAllDecisions) || loadingDecisions}
              >
                {loadingDecisions ? "Loading decisions..." : "Refresh Decisions"}
              </Button>
              <label className="flex items-center gap-2 text-xs font-medium text-slate-600">
                <input
                  type="checkbox"
                  checked={showAllDecisions}
                  onChange={(e) => setShowAllDecisions(e.target.checked)}
                />
                Show decisions from all schemes/rules
              </label>
            </div>
          </Card>

          <Card className="rounded-3xl border-slate-200 bg-white p-6">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Latest Evaluation Summary</p>
            {latestSummary ? (
              <div className="mt-4 space-y-3 text-sm">
                <p className="font-semibold text-slate-800">Evaluated: {latestSummary.evaluated}</p>
                <p className="font-semibold text-slate-800">Decisions Saved: {latestSummary.decisions_saved}</p>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(
                    (latestSummary.bucket_counts && Object.keys(latestSummary.bucket_counts).length > 0)
                      ? latestSummary.bucket_counts
                      : latestSummary.counts || {},
                  ).map(([key, value]) => (
                    <Card key={key} className="rounded-2xl border-slate-100 bg-slate-50 px-3 py-2">
                      <p className="text-[11px] font-bold uppercase tracking-widest text-slate-500">
                        {bucketLabel[key] || key}
                      </p>
                      <p className="text-lg font-black text-slate-900">{value}</p>
                    </Card>
                  ))}
                </div>
                <Card className="rounded-2xl border-sky-200 bg-sky-50 px-3 py-2">
                  <p className="text-xs font-semibold text-sky-700">
                    {latestSummary.evaluation_basis?.message ||
                      "Decision buckets are based on mapped criteria available in the master dataset."}
                  </p>
                  <p className="mt-1 text-[11px] text-sky-700">
                    Include fields used:{" "}
                    {(latestSummary.evaluation_basis?.executable_include_fields || []).join(", ") || "none"}
                  </p>
                  <p className="mt-0.5 text-[11px] text-sky-700">
                    Exclude fields used:{" "}
                    {(latestSummary.evaluation_basis?.executable_exclude_fields || []).join(", ") || "none"}
                  </p>
                  {!!latestSummary.evaluation_basis?.unmapped_criteria?.length && (
                    <p className="mt-0.5 text-[11px] text-sky-700">
                      Unmapped policy criteria (lead to review where critical):{" "}
                      {latestSummary.evaluation_basis.unmapped_criteria.join(", ")}
                    </p>
                  )}
                  {!!latestSummary.evaluation_basis?.no_population_found && (
                    <p className="mt-1 text-[11px] font-semibold text-rose-700">
                      {latestSummary.evaluation_basis?.no_population_reason ||
                        "No citizens found for the selected scheme in the current dataset."}
                    </p>
                  )}
                </Card>
              </div>
            ) : (
              <p className="mt-3 text-sm text-slate-500">Run evaluation to see summary counts.</p>
            )}
          </Card>
        </div>

        <Card className="rounded-3xl border-slate-200 bg-white p-6">
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Decisions</p>
            <p className="text-xs font-semibold text-slate-500">{decisions.length} rows</p>
          </div>

          <div className="mt-4 overflow-auto">
            <table className="w-full min-w-[900px] text-left">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="py-2 pr-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">UID</th>
                  <th className="py-2 pr-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">Citizen Name</th>
                  <th className="py-2 pr-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">Citizen Scheme</th>
                  <th className="py-2 pr-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">Decision</th>
                  <th className="py-2 pr-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">Bucket</th>
                  <th className="py-2 pr-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">Confidence</th>
                  <th className="py-2 pr-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">Reason</th>
                  <th className="py-2 pr-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">LLM Checked Fields</th>
                  <th className="py-2 pr-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">Decision Basis (DB Values)</th>
                  <th className="py-2 pr-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">Manual Inputs</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map((row) => (
                  <tr key={row.id} className="border-b border-slate-50">
                    <td className="py-2 pr-3 text-sm font-medium text-slate-800">{row.citizen_uid}</td>
                    <td className="py-2 pr-3 text-sm text-slate-700">{row.citizen_name || "-"}</td>
                    <td className="py-2 pr-3 text-sm text-slate-700">{row.citizen_scheme_id || "-"}</td>
                    <td className="py-2 pr-3 text-sm">
                      <Badge className={decisionColor[row.decision] || "bg-slate-100 text-slate-700"}>{row.decision}</Badge>
                    </td>
                    <td className="py-2 pr-3 text-sm text-slate-700">{bucketLabel[row.decision_bucket || ""] || row.decision_bucket || "-"}</td>
                    <td className="py-2 pr-3 text-sm text-slate-700">{Math.round((row.decision_confidence || 0) * 100)}%</td>
                    <td className="py-2 pr-3 text-sm text-slate-700">{row.reason}</td>
                    <td className="py-2 pr-3 text-xs text-slate-600">{(row.evidence_json?.checked_fields || []).join(", ") || "-"}</td>
                    <td className="py-2 pr-3 text-xs text-slate-600">{buildDecisionBasis(row)}</td>
                    <td className="py-2 pr-3 text-xs text-slate-600">
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 rounded-lg"
                        onClick={() => {
                          setEditingDecisionId(row.id)
                          if (!manualInputDrafts[row.id]) {
                            const existing = row.evidence_json?.manual_inputs || {}
                            const initial: Record<string, string> = {}
                            for (const req of (row.manual_input_requirements || [])) {
                              initial[req.field] = String((existing as any)?.[req.field] ?? "")
                            }
                            setManualInputDrafts((prev) => ({ ...prev, [row.id]: initial }))
                          }
                        }}
                      >
                        {editingDecisionId === row.id ? "Close" : "Edit"}
                      </Button>
                    </td>
                  </tr>
                ))}
                {decisions.length === 0 && (
                  <tr>
                    <td colSpan={10} className="py-8 text-center text-sm font-medium text-slate-500">
                      No decisions yet. Run an evaluation to populate this table.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        <Card className="rounded-3xl border-slate-200 bg-white p-6">
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Document Processing Status</p>
            <p className="text-xs font-semibold text-slate-500">{documents.length} documents</p>
          </div>
          <div className="mt-4 overflow-auto">
            <table className="w-full min-w-[780px] text-left">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="py-2 pr-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">Filename</th>
                  <th className="py-2 pr-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">Status</th>
                  <th className="py-2 pr-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">Stage</th>
                  <th className="py-2 pr-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">Progress</th>
                </tr>
              </thead>
              <tbody>
                {documents.slice(0, 20).map((doc) => (
                  <tr key={doc.id} className="border-b border-slate-50">
                    <td className="py-2 pr-3 text-sm font-medium text-slate-800">{doc.filename}</td>
                    <td className="py-2 pr-3 text-sm">
                      <Badge className={doc.status === "success" ? "bg-emerald-100 text-emerald-700" : doc.status === "failed" ? "bg-rose-100 text-rose-700" : "bg-slate-100 text-slate-700"}>
                        {doc.status}
                      </Badge>
                    </td>
                    <td className="py-2 pr-3 text-sm text-slate-600">{doc.sub_status || "-"}</td>
                    <td className="py-2 pr-3 text-sm text-slate-600">{doc.progress_percent ?? 0}%</td>
                  </tr>
                ))}
                {documents.length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-8 text-center text-sm font-medium text-slate-500">
                      No documents found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
        <Dialog open={!!activeEditingRow} onOpenChange={(open) => { if (!open) setEditingDecisionId(null) }}>
          <DialogContent className="max-h-[90vh] max-w-3xl overflow-hidden rounded-2xl p-0">
            <div className="flex max-h-[90vh] flex-col">
            <div className="border-b border-slate-200 px-6 py-5">
            <DialogHeader>
              <DialogTitle>Manual Inputs For Eligibility Re-judgement</DialogTitle>
              <DialogDescription>
                Suggested fields are generated from missing required fields and unmapped criteria for this citizen/rule.
              </DialogDescription>
            </DialogHeader>
            </div>
            {activeEditingRow && (
              <div className="flex-1 overflow-y-auto px-6 py-5">
              <div className="space-y-3">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
                  <p><span className="font-semibold">UID:</span> {activeEditingRow.citizen_uid}</p>
                  <p><span className="font-semibold">Current Decision:</span> {activeEditingRow.decision_bucket || activeEditingRow.decision}</p>
                  <p className="mt-1"><span className="font-semibold">Reason:</span> {activeEditingRow.reason}</p>
                </div>
                <div className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-xs text-sky-800">
                  <p className="font-semibold">Suggested inputs by system:</p>
                  <p className="mt-1">
                    {activeManualRequirements.map((item) => item.field).join(", ") || "No missing essential fields detected from current mapped rules."}
                  </p>
                </div>
                {(activeRemainingMissingFields.length > 0 || activeRemainingUnmapped.length > 0) && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                    <p className="font-semibold">Remaining unresolved criteria after latest judgement:</p>
                    {activeRemainingMissingFields.length > 0 && (
                      <p className="mt-1">
                        Missing required fields: {activeRemainingMissingFields.join(", ")}
                      </p>
                    )}
                    {activeRemainingUnmapped.length > 0 && (
                      <p className="mt-1">
                        Unresolved policy criteria: {activeRemainingUnmapped.join(", ")}
                      </p>
                    )}
                  </div>
                )}
                {activeManualRequirements.length > 0 ? (
                  <div className="grid grid-cols-2 gap-2">
                    {activeManualRequirements.map((req) => (
                      <div key={`${activeEditingRow.id}-${req.field}`} className="space-y-1">
                        <p className="text-[11px] font-semibold text-slate-600">
                          {req.field} ({req.input_type})
                        </p>
                        <Input
                          value={manualInputDrafts[activeEditingRow.id]?.[req.field] ?? ""}
                          onChange={(e) =>
                            setManualInputDrafts((prev) => ({
                              ...prev,
                              [activeEditingRow.id]: {
                                ...(prev[activeEditingRow.id] || {}),
                                [req.field]: e.target.value,
                              },
                            }))
                          }
                          placeholder={req.requirement || req.reason || req.field}
                          className="h-9 rounded-md text-xs"
                        />
                        {!!req.reason && <p className="text-[11px] text-slate-500">{req.reason}</p>}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
                    No manual input required for mapped essential fields. If decision is still REVIEW_REQUIRED, it is due to unmapped policy logic that needs rule-mapping updates.
                  </div>
                )}
              </div>
              </div>
            )}
            <div className="border-t border-slate-200 px-6 py-4">
            <DialogFooter>
              <Button variant="outline" onClick={() => setEditingDecisionId(null)}>Cancel</Button>
              <Button
                onClick={() => { if (activeEditingRow) void handleRejudge(activeEditingRow) }}
                disabled={!activeEditingRow || savingManual || activeManualRequirements.length === 0}
              >
                {savingManual ? "Saving..." : "Save & Re-judge"}
              </Button>
            </DialogFooter>
            </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}
