# Quarterly reporting scripts (EPCE-6745)

Scaffolding for the three-lane programme reporting model. See [docs/how-to/quarterly-reporting.md](../../docs/how-to/quarterly-reporting.md).

| Script | Purpose |
|--------|---------|
| `fetch_quarter_goal.py` | Planned SP from EPCE-3897 size-epics aggregate (Smartificer goal) |
| `fetch_epic_timeline.py` | Epic delivery bars on quarter calendar (target engine release) |
| `import_release_plan.py` | Sprint/PRD calendar from xlsx (extended to 1 Apr) |
| `allocate_burn.py` | Claim deploy SP per sprint and PRD release window |
| `deploy_burn.py` | Earned SP by lane (Deploy+ / Done) from Jira changelog |
| `squad_velocity.py` | Per-squad deploy credit across closed sprints in the quarter |
| `quarter_dashboard.py` | HTML dashboard from JSON artifacts |
| `publish_dashboard_pages.py` | Copy dashboard HTML to `docs/quarter/` for GitHub Pages |
| `refresh_dashboard_pages.sh` | Full pipeline + publish (local or GitHub Actions) |
| `publish_quarter_confluence.py` | Publish summary tables to DTRAIN Confluence |
| `create_current_quarter_page.py` | Create Current Quarter template under EPC Delivery Reports |
| `quarter_status.py` | Quarter elapsed / ideal burn / goal variance snapshot (JSON) |

Output: `output/quarterly/{slug}/` (gitignored).

Config: `config/quarterly-reporting.json`
