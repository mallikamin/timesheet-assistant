# Harvest Project & Task Structure

Last updated: 2026-03-05
Status: PARTIAL — based on screenshots. Update when Tariq provides full export.

## How Harvest Works (Our Understanding)

```
Client (billing entity)
  = Project (same name in most cases)
      Task 1 [code]
      Task 2 [code]
      Task 3 [code]
```

- The **client name IS the project** (e.g. "Acuity" is both client and project).
- Codes like `6-1000` appear to be `{project_id}-{task_id}`.
- When a user mentions a client/project, the AI should ask **which task** — not which project.
- If user also specifies the task clearly, log it directly.

## Known Clients & Tasks

### Acuity (Project ID: 6)
| Task Code | Task Name |
|-----------|-----------|
| 6-1000 | Existing Business Growth FY26 |
| 6-1000 | New Business Growth FY26 |
| 6-1003 | Operations & Admin FY26 |

Note: Two tasks share code 6-1000 — may be subtasks or a data issue. Clarify with Tariq.

### Afterpay Australia Pty Ltd (Project IDs: 2, 4)
| Task Code | Task Name |
|-----------|-----------|
| 2-00049 | AUNZ Retainer 2026 |
| 2-1099 | Arena Project |
| 2-1100 | Ads Project Mar-Dec 2026 |
| 4-0048 | Animates |
| 4-0049 | NZ PR Retainer Mar-Dec 2026 |

Note: Codes start with 2- and 4-. Might be separate sub-projects under the same client. Clarify with Tariq.

### AGL
| Task Code | Task Name |
|-----------|-----------|
| — | Existing Growth - AGL |

Note: No code visible in screenshots.

### Internal (Thrive)
| Task Code | Task Name |
|-----------|-----------|
| — | Operations & Admin |
| — | Business Development |

## Waiting For (from Tariq)
- [ ] Full Harvest project/task list export (CSV or API dump)
- [ ] Confirmation of code format (project_id-task_id?)
- [ ] Which tasks are active vs archived
- [ ] Any tasks shared across projects

## AI Conversation Flow

1. User says what they worked on (e.g. "spent 2 hours on Acuity")
2. AI identifies the project → Acuity
3. AI lists available tasks:
   "Which Acuity task was this for?
    1. Existing Business Growth FY26
    2. New Business Growth FY26
    3. Operations & Admin FY26"
4. User picks one (or describes it, AI matches)
5. AI confirms hours + notes, then logs the entry

If user is specific enough upfront (e.g. "2 hours on Acuity admin"), AI can skip straight to logging.
