# Use Case 3: Unified Social Registry

## Layman Brief for Presentation

This document explains the approach in simple language for non-technical stakeholders.

---

## 1) What Problem We Are Solving

Public welfare programs often have large beneficiary databases. Over time, records can become duplicated, incomplete, or suspicious. This can cause:

- benefits going to ineligible or duplicate records
- genuine citizens facing delays
- audit teams being overloaded with too many low-quality alerts

Our goal is to help teams find high-risk cases early, investigate faster, and protect genuine beneficiaries.

---

## 2) Our Approach (Simple View)

We follow a practical 4-step approach:

1. **Collect and connect data**
- We take social registry records and connect related entities such as citizens, operators, location units, and identity markers.
- This creates one connected view instead of isolated tables.

2. **Apply transparent fraud rules**
- We run clear business rules (for example: impossible age, future date of birth, exact duplicate identity combinations).
- Every alert has a reason attached.

3. **Prioritize by risk and confidence**
- Alerts are ranked so teams focus first on the most important cases.
- This avoids wasting field capacity on low-priority records.

4. **Verify in field and feed back results**
- Teams verify cases, then outcomes are fed back to improve thresholds and reduce noise.

In short: **Connect data -> detect risk -> prioritize action -> learn and improve.**

---

## 3) How Knowledge Graph Helps Our Approach

Knowledge Graph is the backbone that makes our approach practical and effective.

1. **Connects scattered data into one view**
- Instead of isolated rows, we see how citizens, operators, schemes, and locations are linked.

2. **Finds hidden network patterns**
- It reveals suspicious clusters such as shared identity markers, duplicate groups, and operator-linked anomalies.

3. **Improves prediction and prioritization**
- Graph-based features (cluster size, duplicate links, anomaly concentration) improve risk scoring quality.
- This helps teams focus on higher-value cases first.

4. **Makes every alert explainable**
- Teams can see the evidence path behind a flag, which is critical for audits and policy decisions.

5. **Speeds up operational decisions**
- With linked context and ranked alerts, triage and field assignment become faster and more targeted.

In short: **the Knowledge Graph turns raw data into connected intelligence that improves detection, explainability, and action.**

---

## 4) How We Create the Knowledge Graph

We create the Knowledge Graph in a simple pipeline:

1. **Ingest registry data**
- We take social registry records and related operational fields.

2. **Standardize and clean**
- We normalize names, dates, locations, and identifiers so records can be compared correctly.

3. **Create entities (nodes)**
- We represent important objects as nodes, such as:
  - citizen
  - operator
  - location unit (GP/block/district)
  - scheme
  - identity hubs (mobile, ration card, address)

4. **Create relationships (links)**
- We connect nodes using factual links like:
  - lives in
  - enrolled in
  - registered by
  - shares identity marker with

5. **Add risk signals**
- We attach rule-based fraud flags and confidence scores to relevant nodes/links.

6. **Serve through dashboards and APIs**
- The graph powers alerts, explainability views, and investigator workflows.

In short: **we convert scattered records into a connected risk network that can be searched, explained, and acted on.**

---

## 5) How the Knowledge Graph Helps Better Prediction Modeling

Traditional row-by-row checks miss network patterns. The graph improves prediction modeling by adding relationship context.

### What extra intelligence the graph adds

- duplicate-link counts across records
- shared mobile/ration/address cluster size
- same-DOB cluster density in a location
- operator-level anomaly concentration
- repeated flags around the same hubs

These become strong **graph features** for risk modeling.

### Why this improves prediction quality

- captures fraud rings, not just single bad fields
- reduces blind spots from isolated table checks
- improves prioritization by combining many weak signals into one stronger risk view
- keeps outputs explainable, so teams can trust and validate model decisions

Practical outcome: **better precision-recall balance and lower false-positive burden over time**, especially after field-feedback tuning.

---

## 6) What “Accuracy” Means in This System

For a layman audience, accuracy should be explained as **signal quality**, not final legal guilt.

### Current signal confidence in the deck

- Example rule confidence shown: **85% to 92%**
- This means the rule is strong as an early warning signal.
- It does **not** mean 85-92% of people are fraudsters.

### Metrics we track to measure real performance

- **Precision**: out of flagged cases, how many were truly valid alerts
- **Recall**: out of all real problematic cases, how many we successfully caught
- **False-positive rate**: how many alerts turned out unnecessary after verification
- **Time-to-triage**: how quickly a new alert is reviewed
- **Time-to-closure**: how quickly a case is completed

Target outcome: **higher true positives, lower false positives, faster action**.

### Accuracy scoring formulas (for reporting)

- **Precision** = `True Positives / (True Positives + False Positives)`
- **Recall** = `True Positives / (True Positives + False Negatives)`
- **False-Positive Rate** = `False Positives / (False Positives + True Negatives)`  
  For operations dashboards, teams may also track `False Positives / Total Flagged`.
- **Time-to-Triage** = `triaged_at - detected_at`
- **Time-to-Closure** = `closed_at - detected_at`

### Current data readiness status

For the current dataset snapshot, we can calculate **flag volume**, **rule distribution**, and **confidence distribution**.  
However, true **precision/recall/false-positive rate** needs verified disposition labels (for example: `confirmed_fraud`, `false_positive`, `needs_monitoring`) and timestamped workflow events (`detected_at`, `triaged_at`, `closed_at`).

So today:
- **Can report now**: confidence/rule-level risk signals and queue-level operational counts
- **Cannot report reliably yet**: true precision, recall, and false-positive rate without field-verified outcomes

---

## 7) Evaluation Process (How We Validate It Works)

We evaluate in an operational loop, not one-time testing.

1. **Detect**
- System flags suspicious records based on rules and connected patterns.

2. **Explain**
- Each alert includes why it was flagged and what connections support it.

3. **Prioritize**
- Cases are ranked by severity and confidence.

4. **Assign**
- High-priority cases go to responsible teams.

5. **Field verify**
- Teams confirm, reject, or update the case outcome.

6. **Improve**
- Verified outcomes are used to tune rules, thresholds, and workflows.

This creates a continuous improvement cycle.

---

## 8) Key Risks We Foresee for the Client

Below are the main implementation risks and practical mitigation steps.

### 1. Data Quality Risk

**Risk**: Missing, inconsistent, or outdated records can generate noisy alerts.

**Mitigation**:
- run data quality checks at ingestion
- define mandatory high-impact fields
- assign trust scores by data source

### 2. False-Positive Risk

**Risk**: Too many weak alerts can overwhelm teams and delay true high-risk cases.

**Mitigation**:
- enforce confidence thresholds
- use severity tiers
- review precision trends monthly

### 3. Privacy and Governance Risk

**Risk**: Citizen data exposure due to weak access controls.

**Mitigation**:
- role-based access control
- masking of sensitive fields
- strong audit logging and retention policies

### 4. Operational Adoption Risk

**Risk**: Platform value drops if daily teams do not use it consistently.

**Mitigation**:
- define clear ownership and SOPs
- role-specific dashboards
- structured onboarding and periodic refresher training

### 5. Policy Mismatch Risk

**Risk**: Alert actions can conflict with local legal/approval workflows.

**Mitigation**:
- configurable workflow states
- approval gates for high-severity actions
- policy sign-off before go-live

### 6. Scale and Capacity Risk

**Risk**: Alert volume may grow faster than verification capacity.

**Mitigation**:
- phased rollout by district/program
- SLA monitoring and load balancing
- periodic rule tuning to control alert quality

---

## 9) Suggested Talk Track (2-3 Minutes)

"We built this as an early-warning and decision-support system for welfare delivery. Instead of looking at records one by one, we connect data to see suspicious patterns across people, operators, and locations. We then apply transparent rules, assign confidence, and prioritize what should be checked first. The key point is that alerts are explainable, not black-box outputs. We measure success through precision, recall, false positives, and response time, and we continuously improve using field verification feedback. We also proactively manage risks around data quality, privacy, adoption, policy alignment, and scale."

---

## 10) One-Slide Summary (If Needed)

- **Approach**: Connected data + explainable rules + prioritized action
- **Knowledge Graph Build**: Clean data -> create entities/links -> attach risk signals
- **Prediction Benefit**: Graph features improve fraud-risk modeling and prioritization
- **Accuracy**: Current rule-confidence signals 85-92%; validated through field outcomes
- **Evaluation**: Detect -> Explain -> Prioritize -> Verify -> Improve
- **Client Risks**: Data quality, false positives, privacy, adoption, policy mismatch, scale
- **Business Value**: Faster triage, better audit focus, improved integrity of welfare delivery

---

## 11) Q&A Prep (Likely Questions and Suggested Answers)

### Q1) Is this system automatically declaring citizens as fraudulent?
**Answer**: No. The platform is an early-warning and decision-support tool. It flags risky cases with reasons and confidence, but final decisions are made through human verification and policy process.

### Q2) What does 85-92% confidence actually mean?
**Answer**: It means rule strength as a warning signal, not final guilt. A high-confidence alert means the case should be prioritized for review, then validated by audit teams.

### Q3) How is this better than normal database reports?
**Answer**: Normal reports check records one by one. Our knowledge graph connects records and reveals hidden patterns across people, operators, and locations, which improves risk detection and explainability.

### Q4) Can this reduce false positives over time?
**Answer**: Yes. We use field-verification outcomes as feedback to tune rules, thresholds, and prioritization. This improves precision and reduces unnecessary investigations over time.

### Q5) How do you protect citizen privacy?
**Answer**: Through role-based access, data masking, audit logs, and retention controls. Users only see what their role is allowed to access.

### Q6) What if data quality is poor?
**Answer**: We treat data quality as a core risk. We run data checks, enforce mandatory fields, and apply source trust scoring. Poor-quality data gets flagged early so teams can fix it.

### Q7) How do we know the system is working after go-live?
**Answer**: We track operational KPIs: precision, recall, false-positive rate, time-to-triage, and time-to-closure. Regular review cycles show whether performance is improving.

### Q8) Will this increase workload for field teams?
**Answer**: Initially, there can be a transition period. But the goal is to reduce workload by ranking alerts so teams focus only on the highest-value cases first.

### Q9) Can policy teams control how alerts are handled?
**Answer**: Yes. Workflow states, thresholds, and escalation logic can be configured to match local policy and approval requirements.

### Q10) What is the expected business impact in simple terms?
**Answer**: Better targeting, faster audits, reduced leakage, fewer unnecessary investigations, and stronger trust in welfare delivery decisions.
