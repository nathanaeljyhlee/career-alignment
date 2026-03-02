---
purpose: Living PR queue for Codex → Claude review → merge workflow
updated: 2026-03-02 (post-PR-#7 merge; CMF-038/039/040 merged)
how_to_use: |
  Codex: read this file + CODEX-ONBOARDING.md before creating any PR.
  Claude: review open PRs against specs here, merge approved ones, update log below.
---

# CMF Engine — Codex Review Queue

## How This Works

1. **Codex** reads the "Next Up" queue below, picks the top item, opens a PR titled `[CMF-XXX] Short description`
2. **Claude** reviews the PR diff against the spec in this doc, approves or requests changes, merges via `git fetch + merge --no-ff + push`
3. **Claude** moves the item from "Next Up" to the merge log, adds any follow-up notes
4. Repeat

**One PR per item** unless items are pure data-only and trivially coupled (e.g. two alias additions to the same file). Code changes always get their own PR.

---

## Next Up (priority order — Codex works top to bottom)

### CMF-005 — Tally intake end-to-end run test
**Type:** Verification / minor bug fixes expected
**Files:** `tally_intake.py`, `runs/processed_submissions.json`
**Problem:** `tally_intake.py` is fully implemented (Session 11) but has never been run end-to-end. The PR's Codex notes flagged a `FileNotFoundError` when running `--list` without a Tally API key available in their environment.
**Fix approach:**
- This item requires running the actual script. If Codex cannot run it (no API key access), create a PR that adds a `--dry-run` flag that exercises the full intake code path against a fixture JSON response (no live API call). This verifies the parsing and routing logic without needing credentials.
- If Codex can run it: run `python tally_intake.py` against one of the 3 existing submissions, confirm run saves to `runs/` with submission ID in filename, confirm `processed_submissions.json` updates. Fix any crashes.
**Verify:** Either a clean end-to-end run log OR a working `--dry-run` path with fixture data.

---

### CMF-037 — Expand role taxonomy from 20 to 80 roles with track and MBA flags
**Type:** Data addition (two data files — no code changes)
**Files:** `data/role_taxonomy.json`, `data/onet_skills.json`
**Problem:** The 20-role taxonomy was calibrated on one candidate profile (tech/strategy/product builder). It has no internship vs FT distinction, no MBA-specific vs general-professional flag, and no Babson entrepreneurial track. Running it on any non-builder profile produces meaningless results because the right roles don't exist. Need 80 roles covering all major MBA internship tracks and general professional paths.

**Part A — Schema changes to all existing 20 roles:**
Add 4 new fields to every existing role object (insert after `"category"` field):
- `"functional_category"`: string (see table below)
- `"track"`: `"internship"` | `"ft"` | `"both"`
- `"mba_track"`: `true` | `false`
- `"babson_fit"`: `true` | `false`

Values for existing 20 roles:
| role_id | functional_category | track | mba_track | babson_fit |
|---------|-------------------|-------|-----------|------------|
| product-manager | product | both | true | false |
| product-manager-healthcare | product | both | true | false |
| product-manager-edtech | product | both | true | false |
| management-consultant | consulting | both | true | false |
| strategy-consultant | consulting | both | true | false |
| corporate-strategy-analyst | strategy | both | true | false |
| data-analytics-manager | data_analytics | both | true | false |
| business-intelligence-analyst | data_analytics | both | false | false |
| operations-manager | operations | both | false | false |
| supply-chain-analyst | operations | both | false | false |
| government-digital-services | government | both | false | false |
| government-analytics | government | both | false | false |
| venture-capital-analyst | finance | both | true | true |
| private-equity-associate | finance | both | true | false |
| marketing-manager | marketing | both | false | false |
| financial-analyst | finance | both | false | false |
| technology-program-manager | technology | both | true | false |
| startup-operations | entrepreneurial | both | true | true |
| healthcare-technology-consulting | consulting | both | true | false |
| digital-health-strategy | strategy | both | true | false |

**Part B — 14 new canonical skills to add to `onet_skills.json`:**
Append to the `"skills"` array. Each entry needs: `skill_id`, `skill_name`, `category`, `description`, `aliases`.

| skill_id | skill_name | category | description | aliases |
|----------|-----------|----------|-------------|---------|
| valuation | Valuation | finance | Determining economic value of a business or asset using DCF, comparables, or precedent transactions. | ["business valuation","dcf modeling","valuation modeling","equity valuation","company valuation"] |
| credit_analysis | Credit Analysis | finance | Assessing creditworthiness of a borrower by analyzing financial statements, cash flows, and risk factors. | ["credit assessment","credit underwriting","loan analysis","credit evaluation","debt analysis"] |
| esg_analysis | ESG Analysis | strategy | Evaluating environmental, social, and governance factors in investment decisions or business strategy. | ["esg","environmental social governance","sustainable investing","esg scoring","responsible investing"] |
| impact_measurement | Impact Measurement | strategy | Designing and tracking metrics to quantify social, environmental, or mission-driven outcomes. | ["impact metrics","social impact measurement","theory of change","outcomes measurement","impact reporting"] |
| innovation_management | Innovation Management | management | Structuring and driving innovation processes within organizations including ideation, experimentation, and scaling. | ["corporate innovation","innovation strategy","innovation pipeline","open innovation","innovation leadership"] |
| design_thinking | Design Thinking | complex_problem_solving | Human-centered problem-solving methodology emphasizing empathy, ideation, prototyping, and iterative testing. | ["human-centered design","design sprint","user-centered design","empathy mapping","design process"] |
| crm | CRM | technical | Proficiency with customer relationship management platforms (Salesforce, HubSpot) to manage pipelines and customer data. | ["salesforce","hubspot","customer relationship management","crm platform","crm system","crm tools"] |
| business_development | Business Development | strategy | Identifying and pursuing new business opportunities through partnerships, new markets, or strategic relationships. | ["biz dev","BD","new business","business growth","revenue development","commercial development"] |
| community_engagement | Community Engagement | social | Building relationships with external communities or stakeholder groups to advance organizational goals. | ["community outreach","stakeholder engagement","community relations","outreach programs","civic engagement"] |
| organizational_development | Organizational Development | management | Designing and improving organizational structures, culture, and capabilities to enhance effectiveness. | ["OD","org design","organizational effectiveness","org effectiveness","people development"] |
| hr_strategy | HR Strategy | management | Aligning human resources practices and workforce planning with organizational strategy and business objectives. | ["people strategy","human capital strategy","strategic HR","workforce strategy","talent strategy"] |
| talent_management | Talent Management | management | Attracting, developing, retaining, and deploying talent to meet organizational and individual goals. | ["talent development","talent pipeline","performance management","succession planning","talent programs"] |
| grant_writing | Grant Writing | communication | Writing compelling grant proposals and reports to secure funding from foundations, government agencies, or donors. | ["grant proposal","grant applications","proposal writing","funding proposals","grant management"] |
| budgeting | Budgeting | finance | Planning, allocating, and managing financial resources across departments, projects, or organizations. | ["budget management","budget planning","annual budget","budget oversight","financial budgeting"] |

**Part C — 60 new roles to add to `role_taxonomy.json`:**
All skill names MUST exactly match a `skill_name` in `onet_skills.json` (469 existing + 14 new above). Use approximate BLS data where exact data unavailable. Write 2-3 sentence descriptions, 3 barrier_conditions, 4 expected_signals per role. Set version to `"1.1.0"`.

**Finance & Investing (10 new roles):**

`investment-banking-associate` — role_name: "Investment Banking Associate" | onet: 13-2051.00 | category: finance | functional_category: finance | track: internship | mba_track: true | babson_fit: false | required: Financial Modeling, Accounting, Due Diligence, Communication, Presentation Skills, Critical Thinking, Excel Advanced | preferred: M&A Analysis, LBO Modeling, Valuation, Industry Expertise, Competitive Analysis | motivation: impact=low, capital=high, innovation=low, leadership=moderate, autonomy=low, volatility=low (high-volatility role), prestige=high | bls: 175000, 5.7%, Bachelor's

`corporate-finance-fpa` — role_name: "Corporate Finance / FP&A" | onet: 13-2051.00 | category: finance | functional_category: finance | track: both | mba_track: true | babson_fit: false | required: Financial Modeling, Forecasting, Data Analysis, Communication, Excel Advanced, Reporting, Critical Thinking | preferred: Budgeting, SQL, ERP Systems, Accounting, Tableau or Power BI | motivation: impact=low, capital=moderate, innovation=low, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=moderate | bls: 101350, 5.7%, Bachelor's

`strategic-finance` — role_name: "Strategic Finance" | onet: 13-2051.00 | category: finance | functional_category: finance | track: both | mba_track: true | babson_fit: false | required: Financial Modeling, Strategic Planning, Communication, Data Analysis, Presentation Skills, Critical Thinking | preferred: Scenario Planning, Excel Advanced, Business Case Development, SQL, Forecasting | motivation: impact=moderate, capital=moderate, innovation=moderate, leadership=moderate, autonomy=moderate, volatility=moderate, prestige=moderate | bls: 120000, 6.0%, Bachelor's

`corporate-development` — role_name: "Corporate Development / M&A" | onet: 11-1011.00 | category: finance | functional_category: finance | track: both | mba_track: true | babson_fit: false | required: Financial Modeling, Due Diligence, M&A Analysis, Communication, Competitive Analysis, Critical Thinking | preferred: LBO Modeling, Valuation, Strategic Planning, Excel Advanced, Industry Expertise | motivation: impact=low, capital=high, innovation=low, leadership=moderate, autonomy=moderate, volatility=moderate, prestige=high | bls: 135000, 5.7%, Bachelor's

`growth-equity-associate` — role_name: "Growth Equity Associate" | onet: 13-2051.00 | category: finance | functional_category: finance | track: both | mba_track: true | babson_fit: true | required: Financial Modeling, Market Research, Due Diligence, Communication, Critical Thinking, Competitive Analysis | preferred: Startup Ecosystem Knowledge, Cap Table Modeling, Data Analysis, Networking, Strategic Planning | motivation: impact=moderate, capital=high, innovation=moderate, leadership=low, autonomy=high, volatility=low (high-volatility), prestige=high | bls: 125000, 5.7%, Bachelor's

`credit-risk-analyst` — role_name: "Credit Risk Analyst" | onet: 13-2041.00 | category: finance | functional_category: finance | track: both | mba_track: false | babson_fit: false | required: Financial Modeling, Accounting, Data Analysis, Critical Thinking, Communication, Reporting | preferred: Credit Analysis, Risk Management, Excel Advanced, ERP Systems, Statistical Analysis | motivation: impact=low, capital=moderate, innovation=low, leadership=low, autonomy=moderate, volatility=high (stable), prestige=low | bls: 95000, 8.0%, Bachelor's

`wealth-management-associate` — role_name: "Wealth Management Associate" | onet: 13-2052.00 | category: finance | functional_category: finance | track: both | mba_track: true | babson_fit: false | required: Financial Modeling, Communication, Presentation Skills, Networking, Critical Thinking | preferred: Financial Analysis, Market Research, Data Analysis, Industry Knowledge, Accounting | motivation: impact=low, capital=high, innovation=low, leadership=low, autonomy=moderate, volatility=moderate, prestige=high | bls: 99580, 17.0%, Bachelor's

`commercial-banking-associate` — role_name: "Commercial Banking Associate" | onet: 13-2071.00 | category: finance | functional_category: finance | track: internship | mba_track: true | babson_fit: false | required: Financial Modeling, Accounting, Credit Analysis, Communication, Due Diligence, Critical Thinking | preferred: Excel Advanced, Risk Management, Industry Knowledge, Data Analysis, Negotiation | motivation: impact=low, capital=moderate, innovation=low, leadership=moderate, autonomy=low, volatility=low (stable), prestige=moderate | bls: 110000, 5.0%, Bachelor's

`asset-management-associate` — role_name: "Asset Management Associate" | onet: 13-2051.00 | category: finance | functional_category: finance | track: both | mba_track: true | babson_fit: false | required: Financial Modeling, Market Research, Statistical Analysis, Communication, Critical Thinking | preferred: Data Analysis, Industry Expertise, Networking, Presentation Skills, Risk Management | motivation: impact=low, capital=high, innovation=low, leadership=low, autonomy=moderate, volatility=low (stable), prestige=high | bls: 108000, 5.7%, Bachelor's

`impact-investing-associate` — role_name: "Impact Investing Associate" | onet: 13-2051.00 | category: finance | functional_category: finance | track: both | mba_track: true | babson_fit: true | required: Financial Modeling, Due Diligence, Market Research, Communication, Critical Thinking | preferred: ESG Analysis, Startup Ecosystem Knowledge, Data Analysis, Strategic Planning, Impact Measurement | motivation: impact=high, capital=high, innovation=moderate, leadership=low, autonomy=high, volatility=low (high-volatility), prestige=moderate | bls: 101350, 5.7%, Bachelor's

**Strategy & Business Development (6 new roles):**

`business-development-partnerships` — role_name: "Business Development & Partnerships" | onet: 11-2022.00 | category: strategy | functional_category: strategy | track: both | mba_track: true | babson_fit: true | required: Strategic Planning, Negotiation, Market Research, Communication, Competitive Analysis, Stakeholder Management | preferred: Financial Modeling, Due Diligence, Business Development, Networking, CRM | motivation: impact=moderate, capital=moderate, innovation=moderate, leadership=moderate, autonomy=moderate, volatility=moderate, prestige=moderate | bls: 130000, 6.0%, Bachelor's

`pricing-revenue-strategy` — role_name: "Pricing & Revenue Strategy" | onet: 13-1111.00 | category: strategy | functional_category: strategy | track: both | mba_track: true | babson_fit: false | required: Data Analysis, Financial Modeling, Strategic Planning, Communication, Critical Thinking, Market Research | preferred: SQL, Pricing Strategy, A/B Testing, Excel Advanced, Competitive Analysis | motivation: impact=moderate, capital=moderate, innovation=moderate, leadership=low, autonomy=moderate, volatility=high (stable), prestige=moderate | bls: 101190, 8.8%, Bachelor's

`esg-sustainability-strategy` — role_name: "ESG & Sustainability Strategy" | onet: 13-1199.05 | category: strategy | functional_category: strategy | track: both | mba_track: true | babson_fit: true | required: Strategic Planning, Stakeholder Management, Communication, Data Analysis, Project Management | preferred: ESG Analysis, Change Management, Regulatory Awareness, Presentation Skills, Impact Measurement | motivation: impact=high, capital=low, innovation=moderate, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=low | bls: 90000, 6.0%, Bachelor's

`corporate-communications` — role_name: "Corporate Communications Manager" | onet: 11-2011.00 | category: marketing | functional_category: marketing | track: both | mba_track: false | babson_fit: false | required: Communication, Presentation Skills, Strategic Planning, Stakeholder Management, Writing | preferred: Market Research, Change Management, Brand Management, Competitive Analysis, Critical Thinking | motivation: impact=low, capital=low, innovation=low, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=moderate | bls: 136000, 7.0%, Bachelor's

`competitive-intelligence-manager` — role_name: "Competitive Intelligence Manager" | onet: 13-1161.01 | category: strategy | functional_category: strategy | track: both | mba_track: false | babson_fit: false | required: Market Research, Competitive Analysis, Data Analysis, Communication, Critical Thinking | preferred: Strategic Planning, Industry Expertise, Presentation Skills, SQL, Statistical Analysis | motivation: impact=low, capital=low, innovation=low, leadership=low, autonomy=moderate, volatility=high (stable), prestige=low | bls: 95000, 6.0%, Bachelor's

`business-transformation-manager` — role_name: "Business Transformation Manager" | onet: 13-1111.00 | category: strategy | functional_category: strategy | track: both | mba_track: true | babson_fit: false | required: Change Management, Stakeholder Management, Project Management, Communication, Strategic Planning, Cross-Functional Leadership | preferred: Process Improvement, Data Analysis, Risk Management, Presentation Skills, Lean Six Sigma | motivation: impact=moderate, capital=low, innovation=moderate, leadership=high, autonomy=moderate, volatility=moderate, prestige=moderate | bls: 101190, 8.8%, Bachelor's

**Product, Tech & Analytics (8 new roles):**

`product-marketing-manager` — role_name: "Product Marketing Manager" | onet: 11-2021.00 | category: product | functional_category: product | track: both | mba_track: true | babson_fit: false | required: Market Research, Communication, Competitive Analysis, Stakeholder Management, Strategic Planning, Presentation Skills | preferred: Customer Segmentation, Digital Marketing, A/B Testing, Data Analysis, Product Roadmapping | motivation: impact=moderate, capital=low, innovation=moderate, leadership=moderate, autonomy=moderate, volatility=moderate, prestige=moderate | bls: 161030, 6.6%, Bachelor's

`growth-product-manager` — role_name: "Growth Product Manager" | onet: 11-2021.00 | category: product | functional_category: product | track: both | mba_track: true | babson_fit: true | required: Product Roadmapping, Data Analysis, A/B Testing, User Research, Critical Thinking, Communication | preferred: SQL, Python, Growth Strategy, Machine Learning, Statistical Analysis | motivation: impact=high, capital=low, innovation=high, leadership=moderate, autonomy=high, volatility=low (high-volatility), prestige=moderate | bls: 161030, 6.6%, Bachelor's

`product-analyst` — role_name: "Product Analyst" | onet: 15-2051.00 | category: data_analytics | functional_category: data_analytics | track: both | mba_track: false | babson_fit: false | required: Data Analysis, SQL, Communication, Critical Thinking, Statistical Analysis | preferred: Python, A/B Testing, Tableau or Power BI, Product Sense, Data Visualization | motivation: impact=low, capital=low, innovation=low, leadership=low, autonomy=moderate, volatility=high (stable), prestige=low | bls: 112590, 33.5%, Bachelor's

`ai-product-manager` — role_name: "AI Product Manager" | onet: 11-2021.00 | category: product | functional_category: product | track: both | mba_track: true | babson_fit: true | required: Product Roadmapping, Data Analysis, User Research, Critical Thinking, Communication, Stakeholder Management | preferred: Machine Learning, Python, Technical Fluency, A/B Testing, Strategic Planning | motivation: impact=high, capital=low, innovation=high, leadership=moderate, autonomy=high, volatility=low (high-volatility), prestige=high | bls: 161030, 6.6%, Bachelor's

`data-product-manager` — role_name: "Data Product Manager" | onet: 11-2021.00 | category: product | functional_category: product | track: both | mba_track: true | babson_fit: false | required: Product Roadmapping, Data Analysis, SQL, Communication, Stakeholder Management, Critical Thinking | preferred: Python, Data Modeling, Strategic Planning, A/B Testing, Technical Fluency | motivation: impact=moderate, capital=low, innovation=moderate, leadership=moderate, autonomy=moderate, volatility=moderate, prestige=moderate | bls: 161030, 6.6%, Bachelor's

`strategy-operations-bizops` — role_name: "Strategy & Operations (BizOps)" | onet: 11-1021.00 | category: strategy | functional_category: strategy | track: both | mba_track: true | babson_fit: true | required: Data Analysis, Problem Solving, Strategic Planning, Communication, Cross-Functional Leadership, Project Management | preferred: Financial Modeling, SQL, Process Improvement, Change Management, Stakeholder Management | motivation: impact=moderate, capital=low, innovation=moderate, leadership=moderate, autonomy=moderate, volatility=moderate, prestige=moderate | bls: 102950, 4.4%, Bachelor's

`customer-experience-manager` — role_name: "Customer Experience Manager" | onet: 11-2021.00 | category: product | functional_category: product | track: both | mba_track: false | babson_fit: false | required: User Research, Data Analysis, Stakeholder Management, Communication, Project Management | preferred: Customer Segmentation, Service Design, Process Improvement, SQL, Change Management | motivation: impact=moderate, capital=low, innovation=moderate, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=low | bls: 120000, 6.0%, Bachelor's

`solutions-consultant` — role_name: "Solutions Consultant" | onet: 41-3099.01 | category: consulting | functional_category: consulting | track: both | mba_track: false | babson_fit: true | required: Communication, Stakeholder Management, Problem Solving, Presentation Skills, Technical Fluency | preferred: Product Roadmapping, User Research, Data Analysis, Strategic Planning, CRM | motivation: impact=moderate, capital=low, innovation=moderate, leadership=low, autonomy=moderate, volatility=moderate, prestige=low | bls: 99280, 10.6%, Bachelor's

**Marketing & Commercial (7 new roles):**

`brand-manager-cpg` — role_name: "Brand Manager (CPG)" | onet: 11-2021.00 | category: marketing | functional_category: marketing | track: both | mba_track: true | babson_fit: false | required: Market Research, Strategic Planning, Communication, Competitive Analysis, Data Analysis, Creative Thinking | preferred: Brand Management, Customer Segmentation, Pricing Strategy, Digital Marketing, A/B Testing | motivation: impact=moderate, capital=low, innovation=moderate, leadership=moderate, autonomy=moderate, volatility=moderate, prestige=moderate | bls: 161030, 6.6%, Bachelor's

`digital-marketing-manager` — role_name: "Digital Marketing Manager" | onet: 11-2021.00 | category: marketing | functional_category: marketing | track: both | mba_track: false | babson_fit: false | required: Digital Marketing, Data Analysis, Communication, Market Research, Competitive Analysis | preferred: SQL, A/B Testing, Marketing Analytics, Customer Segmentation, Tableau or Power BI | motivation: impact=low, capital=low, innovation=moderate, leadership=low, autonomy=moderate, volatility=moderate, prestige=low | bls: 161030, 6.6%, Bachelor's

`performance-marketer` — role_name: "Performance Marketer" | onet: 11-2021.00 | category: marketing | functional_category: marketing | track: both | mba_track: false | babson_fit: false | required: Digital Marketing, Data Analysis, A/B Testing, Critical Thinking, Communication | preferred: SQL, Marketing Analytics, Python, Statistical Analysis, Customer Segmentation | motivation: impact=low, capital=low, innovation=moderate, leadership=low, autonomy=high, volatility=moderate, prestige=low | bls: 161030, 6.6%, Bachelor's

`consumer-insights-manager` — role_name: "Consumer Insights Manager" | onet: 19-3022.00 | category: marketing | functional_category: marketing | track: both | mba_track: true | babson_fit: false | required: Market Research, Data Analysis, User Research, Communication, Statistical Analysis | preferred: Customer Segmentation, SQL, Presentation Skills, A/B Testing, Critical Thinking | motivation: impact=moderate, capital=low, innovation=low, leadership=low, autonomy=moderate, volatility=high (stable), prestige=low | bls: 76140, 8.0%, Bachelor's

`sales-strategy-operations` — role_name: "Sales Strategy & Operations" | onet: 11-2022.00 | category: marketing | functional_category: marketing | track: both | mba_track: true | babson_fit: true | required: Data Analysis, Strategic Planning, Communication, Stakeholder Management, Project Management | preferred: SQL, CRM, Financial Modeling, Process Improvement, Excel Advanced | motivation: impact=moderate, capital=moderate, innovation=moderate, leadership=moderate, autonomy=moderate, volatility=moderate, prestige=moderate | bls: 130000, 6.0%, Bachelor's

`revenue-operations-manager` — role_name: "Revenue Operations Manager" | onet: 11-1021.00 | category: marketing | functional_category: marketing | track: both | mba_track: false | babson_fit: true | required: Data Analysis, Process Improvement, Communication, Stakeholder Management, Project Management | preferred: SQL, CRM, Financial Modeling, Excel Advanced, Business Development | motivation: impact=moderate, capital=moderate, innovation=moderate, leadership=moderate, autonomy=moderate, volatility=low (high-volatility), prestige=low | bls: 102950, 4.4%, Bachelor's

`account-executive` — role_name: "Account Executive / Enterprise Sales" | onet: 41-3099.00 | category: marketing | functional_category: marketing | track: ft | mba_track: false | babson_fit: true | required: Communication, Negotiation, Stakeholder Management, Strategic Planning, Critical Thinking | preferred: CRM, Data Analysis, Presentation Skills, Customer Segmentation, Market Research | motivation: impact=low, capital=high, innovation=low, leadership=low, autonomy=high, volatility=low (high-volatility), prestige=low | bls: 85000, 4.0%, Bachelor's

**Operations & Supply Chain (5 new roles):**

`supply-chain-strategy` — role_name: "Supply Chain Strategy" | onet: 13-1081.00 | category: operations | functional_category: operations | track: both | mba_track: true | babson_fit: false | required: Supply Chain Optimization, Data Analysis, Strategic Planning, Communication, Project Management | preferred: ERP Systems, Excel Advanced, Process Improvement, Financial Modeling, Demand Forecasting | motivation: impact=moderate, capital=low, innovation=moderate, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=low | bls: 80880, 16.7%, Bachelor's

`procurement-sourcing` — role_name: "Procurement & Strategic Sourcing" | onet: 13-1023.00 | category: operations | functional_category: operations | track: both | mba_track: true | babson_fit: false | required: Negotiation, Data Analysis, Communication, Stakeholder Management, Project Management | preferred: Supply Chain Optimization, Excel Advanced, ERP Systems, Process Improvement, Risk Management | motivation: impact=low, capital=moderate, innovation=low, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=low | bls: 87500, 4.0%, Bachelor's

`logistics-manager` — role_name: "Logistics Manager" | onet: 11-3071.00 | category: operations | functional_category: operations | track: both | mba_track: false | babson_fit: false | required: Supply Chain Optimization, Data Analysis, Communication, Project Management, Problem Solving | preferred: ERP Systems, Excel Advanced, Process Improvement, Demand Forecasting, Negotiation | motivation: impact=low, capital=low, innovation=low, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=low | bls: 80700, 4.0%, Bachelor's

`general-management-ldp` — role_name: "General Management LDP" | onet: 11-1021.00 | category: operations | functional_category: operations | track: internship | mba_track: true | babson_fit: false | required: Strategic Planning, Cross-Functional Leadership, Communication, Problem Solving, Data Analysis | preferred: Process Improvement, Change Management, Financial Modeling, Project Management, Stakeholder Management | motivation: impact=moderate, capital=low, innovation=moderate, leadership=high, autonomy=moderate, volatility=moderate, prestige=high | bls: 102950, 4.4%, Bachelor's

`operations-excellence-manager` — role_name: "Operations Excellence Manager" | onet: 11-1021.00 | category: operations | functional_category: operations | track: both | mba_track: false | babson_fit: false | required: Process Improvement, Lean Six Sigma, Data Analysis, Communication, Change Management | preferred: Project Management, Stakeholder Management, Statistical Analysis, ERP Systems, Problem Solving | motivation: impact=moderate, capital=low, innovation=moderate, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=low | bls: 102950, 4.4%, Bachelor's

**Entrepreneurial / Startup / VC (10 new roles):**

`vc-associate` — role_name: "Venture Capital Associate" | onet: 13-2051.00 | category: finance | functional_category: entrepreneurial | track: both | mba_track: true | babson_fit: true | required: Financial Modeling, Due Diligence, Market Research, Communication, Critical Thinking, Networking | preferred: Startup Ecosystem Knowledge, Cap Table Modeling, Strategic Planning, Competitive Analysis, Data Analysis | motivation: impact=moderate, capital=high, innovation=high, leadership=low, autonomy=high, volatility=low (high-volatility), prestige=high | bls: 101350, 5.7%, Bachelor's

`corporate-innovation-manager` — role_name: "Corporate Innovation Manager" | onet: 11-1021.00 | category: strategy | functional_category: entrepreneurial | track: both | mba_track: true | babson_fit: true | required: Strategic Planning, Innovation Management, Stakeholder Management, Communication, Project Management | preferred: Design Thinking, Market Research, Data Analysis, Change Management, Product Sense | motivation: impact=high, capital=low, innovation=high, leadership=moderate, autonomy=high, volatility=low (high-volatility), prestige=moderate | bls: 102950, 4.4%, Bachelor's

`growth-strategy` — role_name: "Growth Strategy Manager" | onet: 11-2022.00 | category: strategy | functional_category: entrepreneurial | track: both | mba_track: true | babson_fit: true | required: Strategic Planning, Data Analysis, Market Research, Communication, Critical Thinking, Growth Strategy | preferred: A/B Testing, SQL, Financial Modeling, Competitive Analysis, Product Sense | motivation: impact=high, capital=moderate, innovation=high, leadership=moderate, autonomy=high, volatility=low (high-volatility), prestige=moderate | bls: 130000, 6.0%, Bachelor's

`gtm-strategy-lead` — role_name: "GTM Strategy Lead" | onet: 11-2022.00 | category: strategy | functional_category: entrepreneurial | track: both | mba_track: true | babson_fit: true | required: Strategic Planning, Market Research, Communication, Stakeholder Management, Data Analysis | preferred: Financial Modeling, Business Development, Customer Segmentation, Growth Strategy, A/B Testing | motivation: impact=high, capital=moderate, innovation=high, leadership=moderate, autonomy=high, volatility=low (high-volatility), prestige=moderate | bls: 130000, 6.0%, Bachelor's

`founder-associate` — role_name: "Founder's Associate / Special Projects" | onet: 11-1021.00 | category: strategy | functional_category: entrepreneurial | track: both | mba_track: true | babson_fit: true | required: Problem Solving, Communication, Cross-Functional Leadership, Strategic Planning, Project Management | preferred: Financial Modeling, Product Sense, Market Research, Data Analysis, Growth Strategy | motivation: impact=high, capital=moderate, innovation=high, leadership=low, autonomy=high, volatility=low (high-volatility), prestige=low | bls: 102950, 4.4%, Bachelor's

`search-fund-associate` — role_name: "Search Fund Associate" | onet: 13-2051.00 | category: finance | functional_category: entrepreneurial | track: both | mba_track: true | babson_fit: true | required: Financial Modeling, Due Diligence, Strategic Planning, Communication, Critical Thinking | preferred: M&A Analysis, Valuation, Market Research, Networking, LBO Modeling | motivation: impact=high, capital=high, innovation=moderate, leadership=high, autonomy=high, volatility=low (high-volatility), prestige=moderate | bls: 101350, 5.7%, Bachelor's

`family-office-analyst` — role_name: "Family Office Analyst" | onet: 13-2051.00 | category: finance | functional_category: finance | track: both | mba_track: true | babson_fit: true | required: Financial Modeling, Due Diligence, Market Research, Communication, Critical Thinking | preferred: M&A Analysis, Risk Management, Networking, Data Analysis, Valuation | motivation: impact=low, capital=high, innovation=low, leadership=low, autonomy=moderate, volatility=moderate, prestige=high | bls: 101350, 5.7%, Bachelor's

`corporate-venture-capital` — role_name: "Corporate Venture Capital Associate" | onet: 13-2051.00 | category: finance | functional_category: entrepreneurial | track: both | mba_track: true | babson_fit: true | required: Financial Modeling, Due Diligence, Market Research, Strategic Planning, Communication, Networking | preferred: Startup Ecosystem Knowledge, Cap Table Modeling, Competitive Analysis, Industry Expertise, Data Analysis | motivation: impact=moderate, capital=high, innovation=high, leadership=low, autonomy=moderate, volatility=low (high-volatility), prestige=high | bls: 101350, 5.7%, Bachelor's

`social-enterprise-strategy` — role_name: "Social Enterprise Strategy" | onet: 11-1021.00 | category: strategy | functional_category: entrepreneurial | track: both | mba_track: true | babson_fit: true | required: Strategic Planning, Stakeholder Management, Communication, Data Analysis, Project Management | preferred: Impact Measurement, Financial Modeling, Market Research, Community Engagement, Change Management | motivation: impact=high, capital=low, innovation=moderate, leadership=moderate, autonomy=moderate, volatility=moderate, prestige=low | bls: 102950, 4.4%, Bachelor's

`bizops-startup` — role_name: "BizOps Manager (Startup)" | onet: 11-1021.00 | category: operations | functional_category: entrepreneurial | track: both | mba_track: true | babson_fit: true | required: Problem Solving, Data Analysis, Communication, Project Management, Cross-Functional Leadership | preferred: Financial Modeling, Process Improvement, Growth Strategy, Hiring and Recruiting, Stakeholder Management | motivation: impact=high, capital=moderate, innovation=high, leadership=moderate, autonomy=high, volatility=low (high-volatility), prestige=low | bls: 102950, 4.4%, Bachelor's

**People & HR (5 new roles):**

`hr-business-partner` — role_name: "HR Business Partner" | onet: 13-1071.00 | category: people_hr | functional_category: people_hr | track: both | mba_track: false | babson_fit: false | required: Communication, Stakeholder Management, Problem Solving, Data Analysis, Change Management | preferred: HR Strategy, Talent Management, Organizational Development, Process Improvement, Presentation Skills | motivation: impact=moderate, capital=low, innovation=low, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=low | bls: 86800, 5.0%, Bachelor's

`people-analytics` — role_name: "People Analytics Manager" | onet: 15-2051.00 | category: people_hr | functional_category: people_hr | track: both | mba_track: false | babson_fit: false | required: Data Analysis, SQL, Statistical Analysis, Communication, Critical Thinking | preferred: Python, Tableau or Power BI, HR Strategy, R, Data Visualization | motivation: impact=moderate, capital=low, innovation=moderate, leadership=low, autonomy=moderate, volatility=high (stable), prestige=low | bls: 112590, 33.5%, Bachelor's

`talent-acquisition-manager` — role_name: "Talent Acquisition Manager" | onet: 13-1071.00 | category: people_hr | functional_category: people_hr | track: both | mba_track: false | babson_fit: false | required: Communication, Stakeholder Management, Project Management, Negotiation, Critical Thinking | preferred: Hiring and Recruiting, Data Analysis, HR Strategy, Networking, Problem Solving | motivation: impact=moderate, capital=low, innovation=low, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=low | bls: 86800, 5.0%, Bachelor's

`organizational-development` — role_name: "Organizational Development Specialist" | onet: 13-1071.00 | category: people_hr | functional_category: people_hr | track: both | mba_track: false | babson_fit: false | required: Change Management, Stakeholder Management, Communication, Project Management, Critical Thinking | preferred: Organizational Development, HR Strategy, Data Analysis, Presentation Skills, Process Improvement | motivation: impact=moderate, capital=low, innovation=moderate, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=low | bls: 86800, 5.0%, Bachelor's

`dei-program-manager` — role_name: "DEI Program Manager" | onet: 13-1071.00 | category: people_hr | functional_category: people_hr | track: both | mba_track: false | babson_fit: false | required: Stakeholder Management, Communication, Project Management, Data Analysis, Critical Thinking | preferred: HR Strategy, Organizational Development, Change Management, Community Engagement, Presentation Skills | motivation: impact=high, capital=low, innovation=moderate, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=low | bls: 86800, 5.0%, Bachelor's

**Healthcare, Public Sector & Nonprofit (9 new roles):**

`policy-analyst` — role_name: "Policy Analyst" | onet: 19-3094.00 | category: government | functional_category: government | track: both | mba_track: false | babson_fit: false | required: Data Analysis, Policy Analysis, Communication, Critical Thinking, Writing | preferred: Statistical Analysis, Program Evaluation, Policy Knowledge, Presentation Skills, Market Research | motivation: impact=high, capital=low, innovation=moderate, leadership=low, autonomy=moderate, volatility=high (stable), prestige=low | bls: 69200, 7.0%, Master's degree

`nonprofit-program-manager` — role_name: "Nonprofit Program Manager" | onet: 11-9151.00 | category: nonprofit | functional_category: nonprofit | track: both | mba_track: false | babson_fit: true | required: Project Management, Stakeholder Management, Communication, Data Analysis, Strategic Planning | preferred: Grant Writing, Impact Measurement, Program Evaluation, Community Engagement, Change Management | motivation: impact=high, capital=low, innovation=moderate, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=low | bls: 74240, 9.0%, Bachelor's

`healthcare-administrator` — role_name: "Healthcare Administrator" | onet: 11-9111.00 | category: healthcare | functional_category: healthcare | track: both | mba_track: false | babson_fit: false | required: Healthcare Domain Knowledge, Stakeholder Management, Project Management, Communication, Data Analysis | preferred: Process Improvement, Regulatory Awareness, Financial Analysis, Change Management, ERP Systems | motivation: impact=moderate, capital=low, innovation=low, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=low | bls: 110680, 28.0%, Bachelor's

`hospital-operations-manager` — role_name: "Hospital Operations Manager" | onet: 11-9111.00 | category: healthcare | functional_category: healthcare | track: both | mba_track: false | babson_fit: false | required: Healthcare Domain Knowledge, Process Improvement, Cross-Functional Leadership, Data Analysis, Communication | preferred: Clinical Workflow Understanding, Change Management, Stakeholder Management, ERP Systems, Lean Six Sigma | motivation: impact=moderate, capital=low, innovation=moderate, leadership=high, autonomy=moderate, volatility=high (stable), prestige=moderate | bls: 110680, 28.0%, Bachelor's

`clinical-program-manager` — role_name: "Clinical Program Manager" | onet: 11-9111.00 | category: healthcare | functional_category: healthcare | track: both | mba_track: false | babson_fit: false | required: Healthcare Domain Knowledge, Project Management, Stakeholder Management, Communication, Data Analysis | preferred: Clinical Workflow Understanding, Regulatory Awareness, Change Management, Process Improvement, Program Evaluation | motivation: impact=high, capital=low, innovation=moderate, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=low | bls: 110680, 28.0%, Bachelor's

`health-informatics-analyst` — role_name: "Health Informatics Analyst" | onet: 15-1211.01 | category: healthcare | functional_category: healthcare | track: both | mba_track: false | babson_fit: false | required: Data Analysis, SQL, Healthcare Domain Knowledge, Communication, Critical Thinking | preferred: Python, Statistical Analysis, Tableau or Power BI, Regulatory Awareness, ERP Systems | motivation: impact=moderate, capital=low, innovation=moderate, leadership=low, autonomy=moderate, volatility=high (stable), prestige=low | bls: 112590, 33.5%, Bachelor's

`grants-manager` — role_name: "Grants Manager" | onet: 13-1131.00 | category: nonprofit | functional_category: nonprofit | track: both | mba_track: false | babson_fit: false | required: Communication, Project Management, Financial Analysis, Stakeholder Management, Writing | preferred: Grant Writing, Program Evaluation, Data Analysis, Impact Measurement, Regulatory Awareness | motivation: impact=high, capital=low, innovation=low, leadership=low, autonomy=moderate, volatility=high (stable), prestige=low | bls: 74240, 9.0%, Bachelor's

`development-fundraising-manager` — role_name: "Development & Fundraising Manager" | onet: 11-2033.00 | category: nonprofit | functional_category: nonprofit | track: both | mba_track: false | babson_fit: true | required: Communication, Stakeholder Management, Strategic Planning, Networking, Presentation Skills | preferred: Market Research, Data Analysis, Impact Measurement, Project Management, CRM | motivation: impact=high, capital=low, innovation=low, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=low | bls: 74240, 9.0%, Bachelor's

`customer-success-manager` — role_name: "Customer Success Manager" | onet: 11-2021.00 | category: product | functional_category: product | track: both | mba_track: false | babson_fit: true | required: Communication, Stakeholder Management, Data Analysis, Problem Solving, Critical Thinking | preferred: CRM, Product Sense, Strategic Planning, SQL, Process Improvement | motivation: impact=moderate, capital=low, innovation=low, leadership=moderate, autonomy=moderate, volatility=moderate, prestige=low | bls: 120000, 6.0%, Bachelor's

**Verify after writing both files:**
- `python -c "import json; d=json.load(open('data/role_taxonomy.json')); print(len(d['roles']), 'roles')"`  → should print 80
- `python -c "import json; d=json.load(open('data/onet_skills.json')); print(len(d['skills']), 'skills')"` → should print 483 (469 + 14)
- `python -c "from engine import run_pipeline; print('imports OK')"` → should not raise ImportError
- Update `feature-roadmap.csv`: set CMF-037 status to Done with a completion note

---

~~### CMF-038 — MERGED (PR #7, 2026-03-02)~~
~~### CMF-039 — MERGED (PR #7, 2026-03-02)~~
~~### CMF-040 — MERGED (PR #7, 2026-03-02)~~

---

~~### CMF-031 — MERGED (PR #6, 2026-03-02)~~

---

### CMF-033 — Validate barrier conditions against candidate profile before flagging as gaps
**Type:** Prompt engineering
**Files:** `agents/gap_analyzer.py`
**Problem:** `barrier_conditions` from `role_taxonomy.json` are passed verbatim to the gap analyzer prompt and appear in `evidence_source` without verifying they actually apply to the candidate. Example: "No experience managing multi-workstream initiatives" appeared as a gap for a physician who managed multiple clinical departments simultaneously.
**Fix:** In the gap_analyzer system prompt, add an explicit instruction before the barrier_conditions list:
> "Before including any barrier condition as a gap, you MUST verify it applies to this specific candidate. Check the candidate profile and skills list. If you cannot cite specific evidence of absence from the profile, omit the barrier entirely. Do not flag barriers by default."
**Verify:** After the prompt change, a second run on the Amos profile should not flag "no multi-workstream" as a gap given his clinical department management experience is in the profile.

---

### CMF-007 — Transferable language enrichment layer
**Type:** Feature (new skills.py substep)
**Files:** `skills.py`, `engine.py`
**Problem:** Candidates describe transferable skills in domain-specific language that misses alias matching. "Led quarterly business reviews with C-suite" doesn't match "Stakeholder Management" or "Executive Communication" unless those specific aliases exist. A general LLM pass that translates experience descriptions into transferable skill labels would catch these systematically.
**Fix:** New substep `generate_transfer_labels()` in `skills.py`:
- One batched LLM call (extraction model / Qwen 7B) with all resume text
- Prompt: for each described experience, generate 2-3 transferable skill labels a career advisor in a different industry would use
- Output: list of `(label, source_phrase)` tuples
- Labels appended to alias pool before O*NET normalization, tagged `match_method: "transfer_label"`
- Anti-hallucination guard: model must ground each label in a quoted phrase from the resume. If it cannot quote the phrase, label is discarded.
- Wire into `engine.py` Stage 1 after existing alias extraction, before LLM extraction
**Verify:** After adding, `skills_flat` should contain at least some entries with `match_method: "transfer_label"` when run on a resume with domain-specific language (e.g., clinical, military, nonprofit). The observability UI (CMF-006, done) will surface these automatically.

---

### CMF-035 — Add expected_signal_coverage to skill_overlap computation
**Type:** Feature (new PipelineState field)
**Files:** `matching/skill_overlap.py`, `engine.py`, `tuning.yaml`
**Problem:** `expected_signals` in `role_taxonomy.json` (e.g., "Prior government/nonprofit experience", "Experience with digital transformation") carry no structural weight — they only surface as soft `market_signals` gaps. A candidate can score highly on required/preferred skills while completely lacking the domain signals the role actually requires. This is the root cause of GovTech over-scoring.
**Fix:**
1. In `skill_overlap.py`: compute `expected_signal_coverage` as the fraction of `expected_signals` that have an embedding match (cosine >= 0.50) against the candidate profile text
2. Add `expected_signal_coverage` to the dict returned by `compute_skill_overlap()`
3. In `engine.py`: apply `expected_signal_coverage` as a penalty multiplier on `overlap_score`. Weight configurable in `tuning.yaml` (suggested default: 0.15 — modest penalty).
4. Add `expected_signal_penalty_weight: 0.15` to `skill_overlap` section of `tuning.yaml`
**Verify:** A candidate with 0/4 expected signals for GovTech should see their overlap_score reduced by ~15% (e.g., 0.70 → 0.595). A candidate who matches all expected signals should see no penalty.

---

## Pending Verification (waiting on local run)

| Item | Status | What's needed |
|------|--------|--------------|
| CMF-030 | Resolved | Straggler alias (`"clinical experience"` → `"Healthcare Domain Knowledge"`) added via patch commit on main (2026-03-02). |
| CMF-031 | Merged (PR #6) | Verify: `HIPAA Compliance` absent from role_taxonomy.json; `Healthcare Regulatory Compliance` exists in onet_skills.json; all 8 aliases present in skill_aliases.json. |
| CMF-005 | Verified 2026-03-02 | `--dry-run` processes fixture end-to-end clean. Live API confirmed: `--list` returns 3 real submissions (Abhi Pradhan, Delzaan Sutaria, Amos Ng). Ollama must be running for full pipeline execution. |
| CMF-007 | Merged | Verify: `skills_flat` contains entries with `match_method: "transfer_label"` when run on a domain-specific resume (clinical, military, nonprofit). |
| CMF-033 | Merged | Verify: second run on Amos profile should not flag "no multi-workstream" as a gap. |
| CMF-035 | Merged | Verify: GovTech candidate with 0/4 expected signals sees overlap_score reduced by ~15%. |
| CMF-038 | Merged (PR #7) | Verify: Decision Sprint card appears on every successful run. Low-confidence role shows "explore" not "commit". Copy block readable. Also: confirm motivation guardrail direction (isdisjoint logic) and section_8 display order in app. |
| CMF-039 | Merged (PR #7) | Verify: `python -c "from skills import get_skill_graph; g1=get_skill_graph(); g2=get_skill_graph(); assert g1 is g2"` passes. |
| CMF-040 | Merged (PR #7) | Verify: `python -c "from engine import run_pipeline; print('imports OK')"` no error. Stage 2 wall-clock ≤ max(profile_time, motivation_time) on next real run. |

---

## Merge Log

| PR | Items | Merged | Notes |
|----|-------|--------|-------|
| #1 | CMF-029/030/032/034/036/006 | 2026-03-02 | CMF-030 missing one alias (`clinical experience`) — folded into CMF-031. CMF-006 expander was pre-existing, PR added `transfer_label` support. Format-correct across all data files. |
| (no PR) | CMF-004 | 2026-03-02 | Resolved in Sessions 12-13 via targeted data edits (CMF-034 GovTech filter, CMF-036 two new roles, Technical Fluency promoted to required in technology-program-manager). No standalone Codex PR — changes shipped as part of PR #1 items. |
| #2 | CMF-033 | 2026-03-02 | Barrier condition guard instruction added to gap_analyzer CRITICAL RULES as rule #6. feature-roadmap.csv not updated in PR — update manually. |
| #3 | CMF-005 | 2026-03-02 | `--dry-run` flag + fixture files (tally_submission_sample.json, resume_sample.pdf) added to tally_intake.py. Full code path exercisable without API key. |
| #4 | CMF-007 | 2026-03-02 | `generate_transfer_labels()` in skills.py with anti-hallucination phrase-grounding guard. Wired into engine.py Stage 1. Bonus: infer_skills_against_taxonomy switched from format="json" to InferenceResult.model_json_schema(). Note: `transfer_num_predict` not added to tuning.yaml — `or 1024` fallback in code. |
| #5 | CMF-035 | 2026-03-02 | `expected_signal_coverage` added to skill_overlap.py (cosine ≥ 0.50 vs profile text). Penalty applied in engine.py: `overlap_score = raw * (1 - 0.15 * (1 - coverage))`. `expected_signal_penalty_weight: 0.15` added to tuning.yaml with formula comment. |
| #6 + patch | CMF-031 + CMF-030 straggler | 2026-03-02 | `HIPAA Compliance` renamed to `Healthcare Regulatory Compliance` in onet_skills.json + role_taxonomy.json. 7 aliases added to skill_aliases.json. Missing Part A alias (`clinical experience` → `Healthcare Domain Knowledge`) added as follow-up patch commit directly on main. |
| #7 | CMF-038/039/040 | 2026-03-02 | Decision Sprint card (output.py + app.py + tuning.yaml). Skill graph singleton cache (matching/skill_graph.py). Stage 2 parallel agents via ThreadPoolExecutor. Follow-up: verify motivation guardrail direction (isdisjoint check) on real profile run; confirm section_8 vs section_7 display order is intentional. |

---

## Review Checklist (Claude uses this for every PR)

**Data files:**
- [ ] `skill_aliases.json` keys are lowercase; values exactly match a canonical name in `onet_skills.json`
- [ ] New `onet_skills.json` entries use `skills: [array]` format with `skill_id`, `skill_name`, `category`, `description`, `aliases`
- [ ] New `role_taxonomy.json` role IDs are kebab-case; required/preferred skill names match canonicals in `onet_skills.json`
- [ ] `feature-roadmap.csv` updated: status → Done, completion note added to `notes` column

**Code files:**
- [ ] No hardcoded thresholds or model names — all parameters read from `tuning.yaml` via `get_tuning()`
- [ ] LLM calls use `format=Model.model_json_schema()`, not `format="json"`
- [ ] New `tuning.yaml` parameters have comments explaining their purpose
- [ ] Import chain clean: `python -c "from engine import run_pipeline"` should not error

**PR hygiene:**
- [ ] Title format: `[CMF-XXX] Short description`
- [ ] Body includes: what changed, which files, how to verify
- [ ] Code changes are in their own PR (not bundled with data-only changes unless trivially coupled)

**KPI impact (Claude notes after each merge):**
- [ ] Speed: does this change expected run time? If yes, note est. delta and update ROADMAP.md KPI table
- [ ] Accuracy: does this change which roles/gaps appear? If yes, flag for re-run verification
- [ ] Comprehensiveness: does this expand or contract the role/skill space? If yes, update direction in ROADMAP.md
