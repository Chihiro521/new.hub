# Backend Utility Scripts

This directory contains utility scripts for database management and data initialization.

## Initialization

### `init_demo_data.py`

Populates the database with a demo user, tech news sources, and auto-tagging rules.

**Usage:**

```powershell
# From backend directory
cd backend
python scripts/init_demo_data.py
```

**What it creates:**
- **User**: `demo` / `demo123`
- **Sources**: 36Kr, V2EX, InfoQ, Hacker News
- **Tag Rules**: AI, Frontend, Backend, Startup

## Other Scripts

(Add other scripts here as needed)
