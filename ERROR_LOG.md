# Error Log - Time Logging System

**Purpose**: Cumulative log of errors encountered and fixed. Any agent (Claude, Codex, Cursor) working on this project should read this FIRST to avoid repeating known mistakes.

**Format**: Date, Short Title, Exact Error, Context, Root Cause, Fix, Rule for Future

---

## 2026-03-25: ERROR_LOG Created
**Error**: N/A (initialization)
**Context**: Project priority elevated, ERROR_LOG protocol enforcement
**Fix**: Created ERROR_LOG.md for multi-agent sync
**Rule**: All agents MUST read this file before making changes, append new errors when fixed

---

<!-- New entries go below this line -->

---

## 2026-04-23: Supabase stale seed data blocked Phase 2 dashboard demo
- **Error**: Startup seed check saw 8 pre-existing task rows (Afterpay/AGL/Acuity) from an old seed run and skipped reseeding → `/board` showed 0 tasks per Thrive initiative
- **Context**: Rebuilding local-only Phase 2 dashboard in `poc/app.py` with Tariq's 8 Thrive initiatives, Supabase was auto-connecting via credentials in `.env`
- **Root Cause**: `tasks._use_memory` only flips to True on Supabase failure; when Supabase is reachable, existing rows take precedence over the new seed
- **Fix**: In `seed_demo_tasks()` startup handler, force `tasks._use_memory = True`, `tasks._supabase_available = False`, clear `_in_memory_tasks`, and call `tasks.seed_tasks()` unconditionally. Deterministic and isolates local demo from cloud state.
- **Rule**: For local PoC/demo data, force in-memory mode on startup. Only use Supabase when demo data parity with cloud is actually required.

---

## 2026-04-23: `create_task() got an unexpected keyword argument 'hours_logged'`
- **Error**: Startup seeding crashed — `TypeError: create_task() got an unexpected keyword argument 'hours_logged'`
- **Context**: Adding richer seed data to `tasks.py` that included `hours_logged` values for the "Build POC" and similar already-worked tasks
- **Root Cause**: `create_task()` set `hours_logged: 0.0` internally on the returned dict but didn't accept it as a kwarg
- **Fix**: Added `hours_logged: float = 0.0` to `create_task()` signature and used it in the task dict
- **Rule**: When extending seed data with new fields that make sense to preset, add the kwarg to the CRUD factory — don't rely on post-create patches.

---

## 2026-04-23: Unicode middle-dot (`·`) rendered as `?` in ffmpeg drawtext output
- **Error**: Dry-run ffmpeg command showed `Kanban � Notifications` instead of `Kanban · Notifications` — risk of boxes in final rendered video
- **Context**: Professional subtitles for `ProjectMgmtDemo.mp4` used `·` and `—` for elegant separators
- **Root Cause**: Windows console cp1252 + Python subprocess + ffmpeg filter_complex chain is unreliable with non-ASCII chars; even when Segoe UI Bold supports the glyph, the string can get mangled between YAML → Python → subprocess → filter_complex
- **Fix**: Replaced all `·` → `|` and `—` → `-` in the YAML spec content. Produces identical visual rhythm with 100% ASCII safety.
- **Rule**: For video subtitle content passed through ffmpeg drawtext on Windows, stick to ASCII. Use `|`, `-`, `/` as separators instead of `·`, `—`, `•`.
