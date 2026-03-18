# Time Logging Automation

**AI-first time tracking platform for professional services firms**

[![Live Demo](https://img.shields.io/badge/demo-live-success)](https://timesheet-assistant-jclk.onrender.com/)
[![Status](https://img.shields.io/badge/phase-1%20complete-blue)]()
[![Tech](https://img.shields.io/badge/tech-FastAPI%20%7C%20React%20%7C%20Gemini-orange)]()

---

## 🎯 What is This?

An intelligent system that captures, categorizes, and submits 95% of billable hours automatically using AI, ambient capture, and deep Google Workspace integration.

**Problem**: Knowledge workers waste 30-60 minutes per week manually logging time.

**Solution**: AI learns from your calendar, emails, documents, meetings, and browser activity to autonomously generate accurate timesheets.

---

## ✨ Current Features (Phase 1)

- 🗣️ **Voice/text AI assistant** - Conversational timesheet logging
- 🔐 **Google SSO** - One-click login
- 📅 **Calendar sync** - Auto-pull meetings → suggest time entries
- 📁 **Drive tracking** - Document editing activity → time suggestions
- 📊 **Google Sheets sync** - Real-time visibility
- 🎯 **Smart mapping** - AI maps work to Harvest projects/tasks
- 📝 **Draft entries** - Review before submitting

**Live Demo**: https://timesheet-assistant-jclk.onrender.com/

---

## 📚 Documentation

### **Quick Start**
- **[EXECUTIVE-SUMMARY.md](./EXECUTIVE-SUMMARY.md)** - 2-page overview for stakeholders
- **[STATUS.md](./STATUS.md)** - Current system health and blockers

### **Planning & Roadmap**
- **[NEXT-LEVEL-PLAN.md](./NEXT-LEVEL-PLAN.md)** - Full 32-feature roadmap (Phases 2-5)
- **[ROADMAP-VISUAL.md](./ROADMAP-VISUAL.md)** - ASCII visual timeline and matrix
- **[FEATURE-CHECKLIST.md](./FEATURE-CHECKLIST.md)** - Progress tracking (32 checkboxes)

### **Process Documentation**
- **[Master-Notes.md](./Master-Notes.md)** - Build log, architecture, infrastructure
- **[Decision-Log.md](./Decision-Log.md)** - Client calls, decisions, action items
- **[harvest-structure.md](./harvest-structure.md)** - Harvest project/task mapping

### **Call Prep**
- **[Tomorrow-Call-Plan.md](./Tomorrow-Call-Plan.md)** - Client meeting agenda
- **[Talk-Track-2min.md](./Talk-Track-2min.md)** - Elevator pitch

---

## 🚀 The Roadmap

### **Phase 2: Google AI Native** (Q2 2026 - 12 weeks)
- Gemini 2.0 AI (replace Claude)
- Gmail, Chat, Meet intelligence
- Vertex AI learning engine
- Daily automation (Cloud Scheduler)
- **Target**: 50% automation, 75% accuracy

### **Phase 3: Omnichannel Platform** (Q3-Q4 2026 - 20 weeks)
- Chrome extension (browser tracking)
- Desktop apps (Windows/Mac)
- Mobile app (React Native)
- Slack integration
- BigQuery + Looker analytics
- **Target**: 70% automation, 85% accuracy

### **Phase 4: Enterprise Grade** (Q1-Q2 2027 - 20 weeks)
- Multi-org support + white-label
- SSO/SAML (Okta, Azure AD)
- Admin portal + audit logs
- Multi-system integrations (Jira, Asana, Salesforce)
- Ambient intelligence ("zero-touch" mode)
- **Target**: 90% automation, 95% accuracy

### **Phase 5: Autonomous** (Q3 2027+ - Continuous)
- Continuous learning pipeline
- Autonomous submission
- Predictive pre-filling
- **Target**: 95% automation, 98% accuracy, $10M ARR

See **[NEXT-LEVEL-PLAN.md](./NEXT-LEVEL-PLAN.md)** for full details.

---

## 💰 Revenue Model

### SaaS Pricing
- **Starter**: $8/user/month - Basic Google integration
- **Professional**: $15/user/month - Multi-platform + analytics
- **Enterprise**: $25/user/month - Advanced AI + SSO
- **Enterprise+**: Custom - White-label + support

### Projections
- **Year 1**: $54K ARR (10 clients, 30 users avg)
- **Year 2**: $600K ARR (50 clients, 50 users avg)
- **Year 3**: $6M ARR (200 clients, 100 users avg)

**Customer ROI**: 13-22x (saves 1 hour/week = $4K/year at $80/hr loaded cost)

---

## 🛠️ Tech Stack

### Current (Phase 1)
```
Frontend:  HTML/JS (vanilla)
Backend:   Python FastAPI
AI:        Claude Sonnet 4.5
Database:  Supabase PostgreSQL
Hosting:   Render (free tier)
Auth:      Google OAuth
```

### Future (Phase 3-5)
```
Frontend:   React + TypeScript + PWA
Backend:    Cloud Run microservices (FastAPI)
AI:         Gemini 2.0 + Vertex AI custom models
Database:   Cloud SQL + BigQuery
Mobile:     React Native (Expo)
Desktop:    Electron or native
Infra:      GKE, Cloud CDN, Terraform
```

---

## 🏗️ Project Structure

```
timelogging/
├── poc/                        # Phase 1 POC code
│   ├── app.py                  # FastAPI backend
│   ├── harvest_mock.py         # Supabase persistence
│   ├── calendar_sync.py        # Google Calendar API
│   ├── drive_sync.py           # Google Drive API
│   ├── sheets_sync.py          # Google Sheets sync
│   ├── project_mapping.py      # Harvest project/task mapping
│   ├── templates/              # Jinja2 HTML templates
│   │   ├── index.html          # Main chat interface
│   │   └── login.html          # Google SSO login
│   ├── requirements.txt        # Python dependencies
│   └── .env                    # Environment variables (local)
├── EXECUTIVE-SUMMARY.md        # 2-page stakeholder overview
├── NEXT-LEVEL-PLAN.md          # Full 32-feature roadmap
├── ROADMAP-VISUAL.md           # ASCII timeline & matrix
├── FEATURE-CHECKLIST.md        # Progress tracking sheet
├── STATUS.md                   # Current health & blockers
├── Master-Notes.md             # Build log & infrastructure
├── Decision-Log.md             # Client calls & decisions
├── harvest-structure.md        # Harvest mapping docs
├── render.yaml                 # Render deployment config
├── runtime.txt                 # Python version (production)
└── README.md                   # This file
```

---

## 📦 Installation & Setup

### Prerequisites
- Python 3.9+
- Google Cloud Project (for OAuth + service account)
- Supabase account (free tier)
- Anthropic API key (for Claude) or Google AI Studio (for Gemini)

### Local Development

1. **Clone the repo**
```bash
git clone https://github.com/mallikamin/timesheet-assistant.git
cd timesheet-assistant/poc
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set up environment variables**
```bash
cp .env.example .env
# Edit .env with your credentials:
# - ANTHROPIC_API_KEY
# - SUPABASE_URL + SUPABASE_KEY
# - GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET
# - GOOGLE_SHEET_ID
# - GOOGLE_SERVICE_ACCOUNT_JSON
```

4. **Run the server**
```bash
python app.py
# Open http://localhost:8080
```

### Production Deployment (Render)

See `render.yaml` for deployment config. Auto-deploys from `main` branch.

**Environment variables** (set in Render dashboard):
- All the same as local `.env`
- `PORT` is provided by Render automatically

---

## 🎯 Current Status

**Phase**: Phase 1 COMPLETE ✅
**Demo**: Live at https://timesheet-assistant-jclk.onrender.com/
**Next**: Waiting for client feedback, then start Phase 2A (Gemini migration)

### System Health (2026-03-18)
- ✅ All APIs functional (Calendar, Drive, Sheets, Claude)
- ✅ Authentication working (Google SSO)
- ✅ 17 endpoints operational
- ✅ 1,032 lines of code, zero errors
- ✅ All dependencies up to date

### Blockers
1. **Harvest API token** - Waiting from Tariq (Phase 2 blocker)
2. **Client feedback** - Demo sent, awaiting response
3. **Pricing approval** - $3K-5K dev + $12-15/user/month quoted

See **[STATUS.md](./STATUS.md)** for full details.

---

## 🤝 Contributing

This is currently a private project for a specific client (Thrive PR). If you'd like to collaborate or license this for your organization, contact the team.

---

## 📞 Contact

**Developer**: Malik Amin
**First Client**: Tariq Munir (Thrive PR, Australia)
**GitHub**: https://github.com/mallikamin/timesheet-assistant

---

## 📄 License

Proprietary - All rights reserved (for now)

---

## 🎬 Quick Links

- **Live Demo**: https://timesheet-assistant-jclk.onrender.com/
- **GitHub Repo**: https://github.com/mallikamin/timesheet-assistant
- **Supabase Project**: vsbhiuozqyxxvqwxwyuh (Time assistant)
- **Google Cloud Project**: pure-feat-380217 (My First Project)
- **Google Sheet**: [Timesheet Log](https://docs.google.com/spreadsheets/d/1PcDZ-5xPQr2mTyhujHLHmwIHp0INmOAITkGFbFwDwzw)

---

**Built with ❤️ and AI** 🤖
