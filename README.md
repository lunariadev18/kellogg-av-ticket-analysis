# Classroom AV Support Ticket Analysis

> **Analyzing 18 months of classroom AV support data to identify recurring operational issues, improve IT support performance, and recommend infrastructure improvements using Python, SQL, and Looker Studio.**

> ⚠️ **This project uses a privacy-preserving synthetic dataset calibrated from real ServiceNow summary statistics.** No confidential university data, room numbers, ticket text, or personally identifiable information are included. The workflow mirrors a real operational analytics project end-to-end.

**🔗 Interactive Dashboard:** https://lookerstudio.google.com/reporting/d73c802e-b650-4b93-8d8b-0593e27f0bd6

![Operations Dashboard](dashboard/dashboard.png)

---

# Executive Summary

## Business Problem

University IT departments generate thousands of support tickets every year, making it difficult to identify recurring issues, measure support performance, or prioritize infrastructure improvements.

This project recreates a real-world IT operations analytics workflow using a statistically calibrated synthetic dataset based on 18 months of ServiceNow support activity. The objective was to transform raw operational data into actionable insights through data cleaning, SQL analysis, statistical testing, and interactive dashboarding.

---

## My Role

This was an end-to-end analytics project completed independently.

Responsibilities included:

- Designing a privacy-preserving synthetic dataset based on real ServiceNow summary statistics
- Cleaning and preparing data using Python
- Writing SQL queries for operational analysis
- Building interactive dashboards in Looker Studio
- Performing exploratory and statistical analysis
- Developing operational recommendations for IT leadership

---

# Business Questions

This analysis was designed to answer several operational questions:

- Which classrooms generate the highest support demand?
- Which issue categories consume the most technician time?
- What factors contribute to recurring incidents?
- Which AV configurations are associated with repeat support requests?
- When should preventative maintenance occur?
- Which KPIs should IT leadership monitor?

---

# Tech Stack

| Category | Technologies |
|-----------|--------------|
| Programming | Python |
| Querying | SQL |
| Dashboarding | Looker Studio |
| Analysis | pandas, NumPy, SciPy |
| Visualization | matplotlib |
| Notebook | Jupyter |
| Version Control | Git |

---

# Dashboard Features

The interactive dashboard includes:

- Ticket Volume Trends
- Resolution Time KPIs
- Issue Category Distribution
- Classroom Comparison
- Repeat Ticket Analysis
- Configuration Analysis
- Monthly Operational Trends

---

# Key Findings

## 1. Most raw records were not actual support work

Approximately **71% of the exported records** originated from automated scheduling integrations rather than technician-created support requests.

After filtering automation, removing duplicates, and cleaning inconsistent values:

- **2,546 raw records**
- became **737 human-generated AV support tickets**

Additionally:

- **27% of support tickets lacked room information**, limiting room-level operational analysis.

---

## 2. Five classrooms generated a disproportionate number of repeat incidents

Joining support tickets with classroom AV inventory revealed that the five highest-volume classrooms shared the same legacy AV configuration.

| Configuration | Rooms | Tickets / Room | 14-Day Repeat Rate |
|---|---|---|---|
| Legacy Matrix (2017) | 5 | **56** | **37%** |
| NVX Early Rollout | 4 | 15 | 26% |
| NVX Standard | 13 | 15 | 19% |

Display signal issues represented:

- **38% of tickets in legacy classrooms**
- compared to **10% elsewhere**

Statistical testing showed this difference was highly significant.

![Ticket Volume by Room](dashboard/figures/volume_by_room.png)

---

## 3. Resolution times were misleading without controlling for issue type

While legacy classrooms initially appeared to have faster resolution times, comparing identical issue categories showed they actually required **more than twice as long** to resolve.

Without adjusting for ticket mix, the operational conclusion would have been incorrect.

![Resolution Comparison](dashboard/figures/resolution_compare.png)

---

## 4. Support demand follows predictable seasonal patterns

Ticket volume:

- peaks during Spring Quarter
- drops significantly during academic breaks
- increases approximately **32% year-over-year** in this synthetic dataset

These patterns identify ideal preventative maintenance windows before demand spikes.

![Monthly Volume](dashboard/figures/monthly_volume.png)

---

# Operational Recommendations

Based on the analysis:

1. Modernize the five legacy AV classrooms to the current NVX standard.
2. Add preventative cold-start AV checks before morning and evening class blocks.
3. Schedule preventative maintenance during seasonal demand troughs.
4. Require classroom identifiers on future support requests to improve reporting quality.

### Estimated Operational Impact

Addressing the legacy classroom configuration alone could eliminate approximately:

- **54 recurring tickets per year**
- **11% of total annual human-generated AV support volume**

while improving classroom reliability and reducing technician workload.

---

# Skills Demonstrated

- Operational Analytics
- Dashboard Development
- SQL
- Python
- Data Cleaning
- ETL
- Exploratory Data Analysis
- Statistical Testing
- KPI Reporting
- Root Cause Analysis
- Executive Reporting
- Business Recommendations

---

# Repository Structure

```text
├── data/
│   ├── av_tickets.csv
│   └── classrooms.csv
├── notebooks/
│   └── av_ticket_analysis.ipynb
├── scripts/
│   ├── generate_data.py
│   ├── build_dashboard.py
│   └── export_looker.py
├── sql/
│   └── analysis_queries.sql
├── dashboard/
│   ├── dashboard.png
│   ├── figures/
│   └── looker/
├── interview-prep/
│   └── INTERVIEW_PREP.md
└── requirements.txt
```

---

# Synthetic Dataset Methodology

Because the original ServiceNow export contains confidential university information, this repository uses a statistically calibrated synthetic dataset.

The synthetic data reproduces:

- overall ticket volume
- academic seasonality
- issue category distributions
- technician workload
- resolution time distributions
- automation noise
- missing data
- duplicate submissions

using only aggregate summary statistics measured from the original dataset.

No real support tickets, room numbers, user information, or ticket descriptions are included.

The legacy AV configuration pattern was intentionally introduced to demonstrate a realistic operational analytics workflow, including joining operational and asset-management data, statistical validation, and business recommendation development.

---

# Future Improvements

Potential future enhancements include:

- Live ServiceNow API integration
- Automated ETL pipeline
- Power BI implementation
- Predictive modeling for ticket recurrence
- Technician workload forecasting
- Automated executive reporting

---

# Reproducing the Project

```bash
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

python scripts/generate_data.py

jupyter nbconvert --to notebook --execute --inplace notebooks/av_ticket_analysis.ipynb

python scripts/build_dashboard.py
```
