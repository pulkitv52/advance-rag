# Client Discovery Checklist — Use Case 3 (Fraud Intelligence)

Project: Advance-RAG (USR Fraud Intelligence)  
Date: __________  
Client team present: __________  
Prepared by: __________

---

## 1) Business Outcomes and Priorities

- [ ] Which fraud patterns are top priority for this quarter?
- [ ] What is more costly for you: false positives or false negatives?
- [ ] Which KPI matters most for success?
  - [ ] Leakage reduction
  - [ ] Faster audit closure
  - [ ] Better targeting accuracy
  - [ ] Other: __________
- [ ] What 90-day target do you expect (numeric)?

Notes:

---

## 2) Decision Policy and Risk Thresholds

- [ ] What minimum confidence threshold is acceptable for escalation?
- [ ] Should action require multi-signal confirmation (e.g., 2+ independent rules)?
- [ ] Which actions are policy-allowed?
  - [ ] Monitor
  - [ ] Investigate
  - [ ] Suspend recommendation
  - [ ] Direct suspension
- [ ] Who is final approver for high-severity actions?

Notes:

---

## 3) Data Questions (Based on Provided Dump)

- [ ] Is the registry-source dump fully representative of production data?
- [ ] Which fields are trusted vs noisy vs incomplete?
- [ ] What is source-of-truth for eligibility criteria and policy updates?
- [ ] Can we receive incremental updates (delta/CDC), not only full dumps?
- [ ] Do you have labeled historical fraud outcomes for validation?

Notes:

---

## 4) Governance, Privacy, and Compliance

- [ ] PII masking requirements by role (viewer/auditor/admin)?
- [ ] Required retention period for alerts/case logs?
- [ ] Any restrictions on cross-linking with grievance/call/social data?
- [ ] Mandatory audit-trail/reporting format for regulators/internal audit?

Notes:

---

## 5) Operational Workflow

- [ ] Who will triage alerts day-to-day?
- [ ] Team capacity (cases/day) and expected load?
- [ ] SLA targets:
  - [ ] Time to triage: ________
  - [ ] Time to closure: ________
- [ ] What evidence must field teams receive per case?
- [ ] How should false-positive feedback be captured and used?

Notes:

---

## 6) Frontend and UX Needs

- [ ] Must-have screens for go-live:
  - [ ] Executive dashboard
  - [ ] Alert queue
  - [ ] Case management board
  - [ ] Operator forensic drill-down
  - [ ] Geo view
- [ ] Mandatory exports:
  - [ ] CSV
  - [ ] PDF audit brief
  - [ ] Weekly executive summary
- [ ] Most important filters (district/rule/severity/date/assignee)?
- [ ] Language requirements:
  - [ ] English only
  - [ ] Bilingual
  - [ ] Other: ________

Notes:

---

## 7) Integration and IT Constraints

- [ ] Required integrations (MIS/ticketing/SSO/reporting)?
- [ ] Security/network constraints for deployment?
- [ ] Preferred deployment model:
  - [ ] On-prem
  - [ ] Private cloud
  - [ ] Hybrid
- [ ] Platform constraints (DB size, job windows, API limits)?

Notes:

---

## 8) Rollout and Acceptance Criteria

- [ ] Pilot scope (district/block/time window)?
- [ ] UAT scenarios required for sign-off?
- [ ] Baseline metrics to compare pre vs post deployment?
- [ ] Final sign-off owners:
  - [ ] Business
  - [ ] Audit
  - [ ] IT
  - [ ] Program leadership

Notes:

---

## 9) Meeting Outcomes (Fill Before Closing)

- [ ] Confirmed top 3 business priorities
- [ ] Confirmed threshold/policy decision framework
- [ ] Confirmed data refresh model (full dump vs incremental)
- [ ] Confirmed go-live module scope
- [ ] Confirmed pilot timeline and owners

Immediate next actions:

1. __________________________________________  
2. __________________________________________  
3. __________________________________________
