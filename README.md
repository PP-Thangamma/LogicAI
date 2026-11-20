# LogicAI — The Ticket Queue That Never Shrinks

An end-to-end Flask prototype for intelligent IT ticket intake and triage.

## Included capabilities
- User registration, login and role-based access (user/admin).
- Ticket submission and SQLite persistence.
- NLP-inspired complaint categorization using transparent keyword rules.
- Priority estimation from urgency and impact phrases.
- Department recommendation.
- Similar-ticket detection using token Jaccard + sequence similarity.
- Knowledge-base retrieval ranked by text similarity (RAG-style retrieval foundation).
- Admin dashboard, ticket status/priority/department updates and knowledge article management.
- Seeded knowledge articles and sample test scenarios.

> This is a hackathon-ready prototype, not a production-grade AI service. The current triage and retrieval engine is intentionally explainable and runs locally without external model APIs. The "RAG-style" module retrieves approved knowledge articles; it does not yet call a generative language model. AI recommendations must be reviewed by a human.

## Requirements
- Python 3.10+
- pip

## Run locally
```bash
# Windows PowerShell
py -m venv .venv
.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
python app.py

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

## Admin account
By default, the email `admin@logicai.local` receives admin access when it registers.
1. Open `/register`.
2. Register using `admin@logicai.local`.
3. Use a password of at least 8 characters.
4. Set `ADMIN_EMAIL` before launch to change the configured admin email.

For Windows PowerShell:
```powershell
$env:ADMIN_EMAIL="your-admin-email@example.com"
$env:SECRET_KEY="replace-with-a-long-random-secret"
python app.py
```

## Demo walkthrough
1. Register an ordinary user and submit: "Wi-Fi is not working for everyone in Block B; our class cannot access the internet."
2. Observe Network / Critical / Network Support triage.
3. Submit a similar Wi-Fi report from another account. LogicAI should flag a possible duplicate.
4. Sign in as the admin account and open the ticket queue.
5. Change status to In Progress, then Resolved.
6. Open Knowledge base and add a verified article. Submit a related issue to see retrieved suggestions.

## Project structure
```text
logicai_project/
├── app.py
├── config.py
├── database.py
├── services/ai_engine.py
├── templates/
├── static/css/style.css
├── tests/
├── requirements.txt
└── README.md
```

## Current AI logic and upgrade path
- **Categorization:** transparent keyword scoring. Replace/augment with a trained TF-IDF + Logistic Regression or sentence-transformer classifier after collecting labelled tickets.
- **Priority:** impact/urgency phrase rules. Production version should use an explicit impact × urgency matrix and staff override.
- **Duplicates:** lexical similarity. Upgrade to sentence embeddings + cosine similarity; confirm clusters with support staff.
- **Solution recommendations:** similarity-ranked retrieval over verified knowledge articles. To make this full RAG, pass retrieved passages to an LLM with strict grounding instructions and show citations to the article IDs.
- **MLP:** not included by default because a neural network is not justified without a sufficiently large labelled dataset. Add only after a baseline model is measured.

## Privacy and security before deployment
- Change `SECRET_KEY`; use HTTPS.
- Add CSRF protection, rate limiting, email verification and password reset.
- Restrict admin registration to an invite-only process.
- Add audit logs, retention rules, backups and database migrations.
- Avoid storing passwords, OTPs or sensitive personal information in ticket descriptions.
- Use PostgreSQL and managed secrets for a multi-user deployment.
- Add human approval for priority changes and solution recommendations.

## Tests
Run:
```bash
python -m unittest discover -s tests
```

## Role-based entry update

The landing page now presents three entry roles: Admin, Worker, and Complaint Raiser. The selected role is carried into both sign-in and account creation, and sign-in verifies that the account's stored role matches the selected role before creating a session. Successful authentication routes to the single shared `/dashboard` endpoint, which renders only the matching Admin, Worker, or User dashboard view.

- Complaint Raiser accounts can self-register.
- Worker registration requires a department (Software, Hardware, Electrical, Networking, or Maintenance). Admins can also create workers from the Admin Dashboard.
- Admin registration is restricted to the configured `ADMIN_EMAIL` value (default: `admin@logicai.local`). Set `ADMIN_EMAIL` before first-time admin signup. This restriction prevents arbitrary visitors from selecting Admin and gaining administrator access.
- Existing user records and the configured SQLite database path are preserved; no database reset is required.

## Validation note

In the build environment, Python syntax compilation passed, all 18 unit tests passed, and the synthetic triage smoke set classified 25/25 examples correctly. These tests do not prove browser integration or real-world model accuracy. A full Flask route/browser integration test could not be run here because Flask is not installed in the build environment; install `requirements.txt` and verify the local workflows before presenting the build as fully validated.

## Recent workflow improvements
- Worker/admin complaint updates now use category-specific Cause and Verified Resolution dropdowns.
- Selecting **Others** reveals a manual text field for an unlisted cause or resolution.
- New tickets with a confident AI department classification are automatically assigned within that department. Tickets sent to **Admin Review** remain unassigned until an admin approves the department; approval then attempts automatic assignment.
- Fair assignment excludes Unavailable workers, prefers Available over Busy, then uses relevant skill match, active workload, 30-day assignment count and least-recently-assigned rotation. Assignment events are audited.


## LogicAI innovation upgrades and implementation truth

- **Major incident clustering:** open complaints are compared only within the same predicted category. Similar tickets are grouped under one incident ID while each reporter retains a separate ticket and progress history. Matching uses normalized lexical similarity and should be reviewed by a human; it is not a semantic embedding model.
- **Fair worker assignment:** workers are restricted to the complaint department. Unavailable workers are excluded; Available workers are preferred, with Busy workers used only when no Available worker exists. If skills are supplied, the strongest relevant skill match is preferred. Remaining candidates are ranked by active workload, assignments in the previous 30 days, then least-recently-assigned time. Every automatic or manual assignment is recorded in an audit history shown on ticket details. This is a transparent scheduling policy, not a trained optimization model.
- **Resolution-time estimate:** the app uses the median duration of historical completed tickets, preferring category + priority when at least two examples exist, then category history, then overall history. It applies a documented priority factor and adjusts for the selected worker's active load. If no history exists, it reports a labelled 24-hour cold-start estimate. This is a statistical baseline, not a trained ML model; evaluate it using MAE on real held-out tickets before relying on it.
- **Knowledge base:** only tickets in Completed status can create or update knowledge articles. The service now rejects attempts to add unresolved tickets.
- **Workflow controls:** ticket status must advance sequentially through Open → Seen → Checked → In Progress → Resolved → Completed. A verified resolution is required before Completed.
- **Attachments:** uploaded files are stored in the database and can be downloaded only by users authorized to view that ticket. Text/PDF extraction and image OCR depend on optional local OCR tooling; an upload may be stored even when text extraction is unavailable.
- **Evaluation:** `evaluate_logicai.py` runs a small synthetic classification/similarity smoke test. Its score is not a real-world accuracy claim. The unit test suite checks the assignment policy, duplicate grouping, ETA fallbacks/outlier handling and completion-only knowledge rules.

### Known limitations before real deployment

The classifier is keyword/rule based; duplicate detection is lexical rather than embedding-based; knowledge retrieval is similarity-ranked retrieval rather than generative RAG; and resolution-time prediction is a statistical baseline rather than a trained ML model. A real deployment also needs CSRF protection, rate limiting, email verification/password reset, secure secret management, HTTPS, a production database, backup/restore drills, privacy/retention policy, monitoring and a representative labelled evaluation dataset. Do not claim these production controls or advanced ML components are present unless they are implemented and tested.

## Isolated demo mode (recommended for feature testing)

The demo mode creates a **separate** SQLite database named `demo_logicai.db`.
It does not read, overwrite, or delete your real `logicai.db`. Use this mode to
verify the innovation features with realistic sample users, tickets, history,
incidents, worker skills/workloads, knowledge articles, and feedback.

### Windows CMD setup

```cmd
py -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
run_demo.bat
```

The first run creates `demo_logicai.db` automatically. Later runs reuse it.
To rebuild the demo data from scratch, stop the app and run:

```cmd
.venv\Scripts\python.exe seed_demo.py --reset
```

Then start again with `run_demo.bat`.

### Demo login credentials

| Role | Email | Password |
|---|---|---|
| Admin | `admin.demo@logicai.local` | `AdminDemo123!` |
| Complaint Raiser 1 | `raiser1@logicai.demo` | `RaiserDemo123!` |
| Complaint Raiser 2 | `raiser2@logicai.demo` | `RaiserDemo123!` |
| Complaint Raiser 3 | `raiser3@logicai.demo` | `RaiserDemo123!` |
| Networking Worker 1 | `network1@logicai.demo` | `WorkerDemo123!` |
| Networking Worker 2 | `network2@logicai.demo` | `WorkerDemo123!` |
| Software Worker 1 | `software1@logicai.demo` | `WorkerDemo123!` |
| Software Worker 2 | `software2@logicai.demo` | `WorkerDemo123!` |

Other demo workers exist for Hardware, Electrical and Maintenance. Their
emails follow `hardware1@logicai.demo`, `electrical1@logicai.demo`, and
`maintenance1@logicai.demo`; all use `WorkerDemo123!`.

### Feature verification walkthrough

1. **Major Incident Clustering**
   - Sign in as `raiser3@logicai.demo` and submit a complaint titled
     `Wi-Fi not working in Block B`.
   - Use a description similar to: `Campus Wi-Fi is not working in Block B
     and students cannot access the internet.`
   - Open the ticket details. It should be matched to the existing open
     Wi-Fi incident group. Existing tickets remain separate and keep their
     own ticket IDs/history.
2. **Intelligent Worker Assignment**
   - Submit a new Networking or Software complaint.
   - The assignment service filters by department, excludes Unavailable workers,
     prefers Available over Busy, then considers relevant skill matches, active
     workload, assignments in the last 30 days and least-recently-assigned time.
     Compare the assignment audit history and Admin worker workload table.
   - Sign in as a worker and change Skills / Availability from the worker
     dashboard, then submit another ticket to observe the effect.
3. **Predictive Resolution Time**
   - Open a newly created ticket. Inspect its estimated hours/completion time
     on the ticket detail page.
   - The demo database contains completed examples across categories and
     priorities. The estimate uses historical median duration where enough matching examples
     exist, otherwise it falls back to category/overall history or a clearly
     identified initial estimate.
4. **Classification and priority**
   - Submit examples such as `ERP application crashes during login` (Software)
     and `Power fluctuation in classroom` (Electrical/Critical).
   - Ambiguous low-confidence complaints should be routed to Admin Review.
5. **Low-confidence review queue**
   - The demo includes an intentionally ambiguous ticket, `System behaving strangely`,
     in Admin Review. Admin can select the correct department and approve it.
6. **Knowledge retrieval**
   - Open a new ticket in a category with seeded knowledge articles. Similar
     verified causes and solutions should appear in the Knowledge Retrieval
     section.
7. **Workflow, feedback and analytics**
   - Use a worker account to move a ticket through Seen / Checked / In Progress
     / Resolved / Completed. A verified resolution is required for Completed.
   - Submit feedback as the ticket's Complaint Raiser after resolution.
   - Review Admin metrics, department distribution, worker performance,
     overdue tickets and feedback averages.

### What the demo data proves—and what it does not

- The demo records are synthetic test data, not real campus incidents.
- The resolution-time estimator is a statistical historical-median model
  with fallback rules, not a separately trained ML model.
- Duplicate matching is lexical text similarity; incident grouping is a
  prototype and should be reviewed by a human before operational use.
- Worker ranking uses the current rule-based score; it is not a learned
  optimization model.
- A successful demo run verifies the local prototype workflow, not production
  security, scalability or accuracy.


## Security notes for the demo
- POST forms are protected with session-based CSRF tokens. Logout uses POST.
- Workers can view their department queue, but can change a ticket only when it is assigned to their account.
- Public administrator registration is disabled by default. To create the first administrator, set `ADMIN_REGISTRATION_CODE` to a private one-time invitation code before starting the app, choose the Admin registration option, and enter that code. Remove the environment variable after the administrator account is created. Do not publish the code or commit it to source control.
- Set a stable, private `SECRET_KEY` environment variable for any deployment beyond a disposable local demo.
