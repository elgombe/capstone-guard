# CapstoneGuard

> An academic project submission and duplicate detection platform for universities and institutions. Students submit capstone projects and the system automatically flags semantic duplicates using AI-powered embeddings, catching paraphrased similarities that basic string matching misses.

---

## Features

- **AI Duplicate Detection** — Uses Google Gemini embeddings (`gemini-embedding-001`) to semantically compare project titles and descriptions, catching paraphrased duplicates with configurable similarity thresholds
- **Live Duplicate Check** — Real-time feedback as students type via HTMX, before they even submit
- **Role-Based Access** — Three roles: Student, Reviewer and Admin, each with different permissions
- **Project Lifecycle Management** — Full status workflow: `Pending → Under Review → Approved / Rejected`
- **Stream Organisation** — Projects are categorised by academic streams (e.g. Software Engineering, Electronics)
- **Notifications** — In-app notifications for duplicate warnings, status changes and comments
- **Commenting System** — Reviewers and students can discuss projects via threaded comments
- **Similarity Records** — Every flagged duplicate stores title, description and overall similarity scores for audit trails

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3, Flask |
| Database | SQLAlchemy ORM (PostgreSQL / SQLite) |
| AI / Embeddings | Google Gemini API (`gemini-embedding-001`) |
| Frontend | Jinja2 templates, Bulma CSS, Bootstrap Icons |
| Reactivity | HTMX (live duplicate check, paginated project list) |
| Typography | DM Sans (Google Fonts) |
| Config | python-dotenv |

---

## Getting Started

### Prerequisites

- Python 3.9+
- A [Google AI Studio](https://aistudio.google.com/app/apikey) API key (free, no credit card needed)

### Installation

**1. Clone the repository**
```bash
git clone https://github.com/yourusername/capstoneguard.git
cd capstoneguard
```

**2. Create and activate a virtual environment**
```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Configure environment variables**

Create a `.env` file in the project root:
```env
# Flask
SECRET_KEY=your-secret-key-here
FLASK_ENV=development

# Database
DATABASE_URL=sqlite:///capstoneguard.db

# Google Gemini (free at https://aistudio.google.com/app/apikey)
GEMINI_API_KEY=your-gemini-api-key-here

# Similarity Thresholds
SIMILARITY_THRESHOLD=0.82
TITLE_SIMILARITY_WEIGHT=0.4
DESCRIPTION_SIMILARITY_WEIGHT=0.6
```

**5. Run the development server**
```bash
flask run
```

Visit `http://localhost:5000`

---

## How Duplicate Detection Works

When a project is submitted (or while the student is still typing), CapstoneGuard:

1. Generates a 768-dimensional embedding vector for the incoming **title** and **description** using `gemini-embedding-001` with `SEMANTIC_SIMILARITY` task type
2. Generates embeddings for every **approved** project in the database
3. Computes **cosine similarity** between the vectors
4. Calculates a weighted **overall similarity score**:
   ```
   overall = (TITLE_WEIGHT × title_similarity) + (DESC_WEIGHT × desc_similarity)
   ```
5. Any project exceeding the `SIMILARITY_THRESHOLD` is flagged, stored as a `SimilarityRecord` and triggers a notification

This approach catches paraphrased duplicates that character-level methods (like `difflib.SequenceMatcher`) miss entirely.

### Tuning the threshold

| `SIMILARITY_THRESHOLD` | Behaviour |
|---|---|
| `0.75` | More sensitive — catches loose similarities, higher false positives |
| `0.82` | Recommended — catches paraphrased duplicates reliably (default) |
| `0.90` | Strict — only flags near-identical submissions |

---

## User Roles

| Role | Permissions |
|---|---|
| **Student** | Submit projects, edit own projects, add comments, view notifications |
| **Reviewer** | All student permissions + update project status, add review notes |
| **Admin** | All reviewer permissions + full platform access |

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Landing page |
| `GET` | `/dashboard` | User dashboard |
| `GET` | `/projects` | Browse all projects |
| `GET POST` | `/projects/new` | Submit a new project |
| `GET` | `/projects/<id>` | Project detail |
| `GET POST` | `/projects/<id>/edit` | Edit project |
| `POST` | `/projects/<id>/status` | Update status (reviewer/admin) |
| `POST` | `/projects/<id>/comments` | Add a comment |
| `GET` | `/notifications` | Notification centre |
| `POST` | `/htmx/check-duplicate` | Live duplicate check (HTMX) |
| `GET` | `/htmx/projects` | Paginated project list (HTMX) |

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | — | Flask session secret key |
| `DATABASE_URL` | — | SQLAlchemy database URI |
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `SIMILARITY_THRESHOLD` | `0.82` | Minimum score to flag a duplicate |
| `TITLE_SIMILARITY_WEIGHT` | `0.4` | Weight given to title similarity |
| `DESCRIPTION_SIMILARITY_WEIGHT` | `0.6` | Weight given to description similarity |

---

## License

MIT License — see `LICENSE` for details.