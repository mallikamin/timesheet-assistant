# Harvest master reference data

Snapshots of the live Thrive Harvest account (310089) used as ground truth
for project resolution + prompt construction. Treat these files as
read-only — re-export and re-name with a new date instead of editing
in place.

## Files

| File | Source | Exported |
| --- | --- | --- |
| `projects_2026-05-06.csv` | Harvest webapp → Reports → Project list export | 2026-05-06 |
| `people_2026-05-06.xlsx` | Harvest webapp → Team → Export | 2026-05-06 |
| `tasks_2026-05-06.xlsx` | Harvest webapp → Settings/Manage → Tasks → Export (3,279 account-wide tasks, with active/billable flags) | 2026-05-06 |
| `time_report_fy26_2026-05-06.xlsx` | Harvest webapp → Reports → Detailed time → 2025-07-01 to 2026-06-26 → Export (1,852 rows; Thrive Leave FY26 only) | 2026-05-06 |
| `time_report_rolling12mo_2026-05-06.xlsx` | Harvest webapp → Reports → Detailed time → 2025-05-04 to 2026-05-10 → Export (107,248 rows; **full account-wide project + task usage**) | 2026-05-06 |

## Schema

### projects CSV columns
`Client, Project, Project Code, Start Date, End Date, Project Notes,
Total Hours, Billable Hours, Billable Amount, Budget By, Budget,
Budget Spent, Budget Remaining, Total Costs, Team Costs, Expenses,
Invoiced Amount`

### people xlsx columns
`First Name, Last Name, Email, Employee Id, Roles, Billable Rate,
Cost Rate, Admin, Permissions, Employee, Capacity`

## Key facts derived from these snapshots

- **Total active projects: 107** (not the 51 originally assumed).
- **Project naming pattern for client work**: `<Client> - <Sub-project> FY26`
  (e.g. `Acuity - Existing Business Growth FY26`, code `6-1000`).
- **Project naming pattern for Thrive-internal**: `Thrive <Function> FY26`
  under client `Thrive PR` (e.g. `Thrive Operation FY26` code `3-0011`,
  `Thrive Leave FY26` code `3-0006`).
- **Leave**: single project `Thrive Leave FY26` (`3-0006`). All leave
  subtypes (Annual / Sick / Carer / Compassionate / Unpaid / TIL /
  Funeral) are tasks under this project — confirm via task export.
- **Project codes are not unique**: e.g. both `Thrive New Business -
  Existing Growth FY26` and `Thrive New Business - New Growth FY26`
  share code `3-0004`. Don't use code as a primary key.

## How to refresh

When Harvest naming, project list, or team roster changes:

1. In Harvest, export the project list (Reports → Projects → CSV)
   and the team list (Team → Export → XLSX).
2. Drop them in this directory with a new date suffix
   (`projects_YYYY-MM-DD.csv`, `people_YYYY-MM-DD.xlsx`).
3. Update the date in the table above.
4. Run any scripts that ingest these into prompt context / fallback
   catalog (none yet — see Round-4 work).

## NOT in these snapshots

- **Per-project task assignments** — these files only list projects
  + people. Task names per project still need to be fetched live
  from `/projects/{id}/task_assignments` (or exported separately
  from Harvest if a UI export exists).
