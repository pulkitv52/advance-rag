import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import axios from "axios"

import { Badge } from "./ui/badge"
import { Button } from "./ui/button"
import { Card } from "./ui/card"
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
  source_filename?: string
  created_at?: string
}

interface DecisionRow {
  id: string
  citizen_uid: string
  citizen_name?: string | null
  citizen_scheme_id?: string | null
  decision: "INCLUSION_ERROR" | "EXCLUSION_ERROR" | "VALID_ENROLLMENT" | "NOT_APPLICABLE" | "REVIEW_REQUIRED"
  reason: string
  decision_confidence: number
  created_at?: string
}

interface EvaluationSummary {
  rule_id: string
  scheme_id: string
  evaluated: number
  decisions_saved: number
  counts: Record<string, number>
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
  const match = upper.match(/(?:^|[^A-Z0-9])(SS_\d{2,6}|S\d{2,6})(?:[^A-Z0-9]|$)/)
  return match ? match[1] : ""
}

const decisionColor: Record<string, string> = {
  INCLUSION_ERROR: "bg-rose-100 text-rose-700",
  EXCLUSION_ERROR: "bg-amber-100 text-amber-700",
  VALID_ENROLLMENT: "bg-emerald-100 text-emerald-700",
  NOT_APPLICABLE: "bg-slate-100 text-slate-700",
  REVIEW_REQUIRED: "bg-violet-100 text-violet-700",
}

export function EligibilityStudio({ API }: EligibilityStudioProps) {
  const [documents, setDocuments] = useState<DocumentRow[]>([])
  const [rules, setRules] = useState<RuleRow[]>([])
  const [decisions, setDecisions] = useState<DecisionRow[]>([])

  const [selectedDocumentId, setSelectedDocumentId] = useState("")
  const [schemeId, setSchemeId] = useState("")
  const [ruleName, setRuleName] = useState("")
  const [selectedRuleId, setSelectedRuleId] = useState("")
  const [runLimit, setRunLimit] = useState("500")

  const [extracting, setExtracting] = useState(false)
  const [evaluating, setEvaluating] = useState(false)
  const [uploadingPolicy, setUploadingPolicy] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [loadingRules, setLoadingRules] = useState(false)
  const [loadingDecisions, setLoadingDecisions] = useState(false)

  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [latestSummary, setLatestSummary] = useState<EvaluationSummary | null>(null)
  const [operationLabel, setOperationLabel] = useState("")
  const [operationProgress, setOperationProgress] = useState(0)
  const [operationActive, setOperationActive] = useState(false)
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
    const targetRule = ruleId || selectedRuleId
    if (!targetRule) return

    if (!silent) setLoadingDecisions(true)
    try {
      const res = await axios.get(`${API}/api/eligibility/decisions?rule_id=${targetRule}&limit=200`)
      setDecisions((res.data?.decisions || []) as DecisionRow[])
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to load decisions")
    } finally {
      if (!silent) setLoadingDecisions(false)
    }
  }, [API, selectedRuleId])

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
        rule_name: ruleName.trim() || undefined,
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
      const res = await axios.post(`${API}/api/eligibility/evaluate/${selectedRuleId}?limit=${lim}`)
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

              <div>
                <p className="mb-1 text-xs font-semibold text-slate-500">Rule Name (optional)</p>
                <Input value={ruleName} onChange={(e) => setRuleName(e.target.value)} placeholder="Widow Pension Eligibility" className="rounded-xl" />
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
                onClick={() => loadDecisions(selectedRuleId)}
                disabled={!selectedRuleId || loadingDecisions}
              >
                {loadingDecisions ? "Loading decisions..." : "Refresh Decisions"}
              </Button>
            </div>
          </Card>
        </div>

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

        <div className="grid gap-6 lg:grid-cols-2">
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
                      <p className="mb-1 text-xs font-bold uppercase tracking-widest text-slate-400">Include Conditions</p>
                      <pre className="max-h-52 overflow-auto rounded-xl bg-slate-950 p-3 text-xs text-slate-100">{JSON.stringify(rule.include_conditions || {}, null, 2)}</pre>
                    </div>
                    <div>
                      <p className="mb-1 text-xs font-bold uppercase tracking-widest text-slate-400">Exclude Conditions</p>
                      <pre className="max-h-52 overflow-auto rounded-xl bg-slate-950 p-3 text-xs text-slate-100">{JSON.stringify(rule.exclude_conditions || {}, null, 2)}</pre>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                      <p className="text-[11px] font-bold uppercase tracking-widest text-slate-500">Fetched Eligibility Criteria</p>
                      <div className="mt-2 space-y-2 text-sm">
                        {Object.keys(rule.include_conditions || {}).length > 0 ? (
                          Object.entries(rule.include_conditions || {}).map(([k, v]) => (
                            <p key={`inc-${k}`} className="text-slate-700">
                              <span className="font-semibold text-slate-900">{k}</span>: {JSON.stringify(v)}
                            </p>
                          ))
                        ) : (
                          <p className="text-slate-500">No mapped include criteria found.</p>
                        )}
                        {Object.keys(rule.exclude_conditions || {}).length > 0 && (
                          <>
                            <p className="pt-1 text-[11px] font-bold uppercase tracking-widest text-slate-500">Exclusions</p>
                            {Object.entries(rule.exclude_conditions || {}).map(([k, v]) => (
                              <p key={`exc-${k}`} className="text-slate-700">
                                <span className="font-semibold text-slate-900">{k}</span>: {JSON.stringify(v)}
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
                    {!!(rule.extracted_metadata?.unmapped_criteria?.length) && (
                      <Card className="rounded-2xl border-violet-200 bg-violet-50 px-3 py-2">
                        <p className="text-xs font-semibold text-violet-700">
                          Unmapped criteria detected: {rule.extracted_metadata?.unmapped_criteria?.join(", ")}.
                          Evaluation will be marked REVIEW_REQUIRED until these are structurally mapped.
                        </p>
                      </Card>
                    )}
                    {Object.keys(rule.include_conditions || {}).length === 0 && Object.keys(rule.exclude_conditions || {}).length === 0 && (
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

          <Card className="rounded-3xl border-slate-200 bg-white p-6">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Latest Evaluation Summary</p>
            {latestSummary ? (
              <div className="mt-4 space-y-3 text-sm">
                <p className="font-semibold text-slate-800">Evaluated: {latestSummary.evaluated}</p>
                <p className="font-semibold text-slate-800">Decisions Saved: {latestSummary.decisions_saved}</p>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(latestSummary.counts || {}).map(([key, value]) => (
                    <Card key={key} className="rounded-2xl border-slate-100 bg-slate-50 px-3 py-2">
                      <p className="text-[11px] font-bold uppercase tracking-widest text-slate-500">{key}</p>
                      <p className="text-lg font-black text-slate-900">{value}</p>
                    </Card>
                  ))}
                </div>
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
                  <th className="py-2 pr-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">Confidence</th>
                  <th className="py-2 pr-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">Reason</th>
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
                    <td className="py-2 pr-3 text-sm text-slate-700">{Math.round((row.decision_confidence || 0) * 100)}%</td>
                    <td className="py-2 pr-3 text-sm text-slate-700">{row.reason}</td>
                  </tr>
                ))}
                {decisions.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-sm font-medium text-slate-500">
                      No decisions yet. Run an evaluation to populate this table.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  )
}
