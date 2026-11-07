# Build plan

One feature at a time. A feature is done only when its API, web and mobile parts (where they apply)
work, tests pass, and the sample dataset shows it. Items refer to the MVP list in the SRS.

| # | Feature | SRS items | Status |
|---|---|---|---|
| 0 | Foundation | – | Done |
| 1 | Sign-in (email and password), roles, matter-level access, audit log | 1 | Done |
| 2 | Team and office setup, assignments | 13 | Built, see notes |
| 3 | Clients and case workspace, configurable stages | 3, 4 | Built, see notes |
| 4 | Bulk import (Excel/CSV) | 2 | Built, see notes |
| 5 | Calendar, next date, clash warning, Today dashboard | 6, 7 | Built, see notes |
| 6 | Tasks and court directions | 8 | Built, see notes |
| 7 | Documents with OCR and AI summary | 10 | Built, see notes |
| 8 | Voice hearing record, review and approval | 5 | Built, see notes |
| 9 | Client message and T-7, T-3, T-1 reminders | 9 | Built, see notes |
| 10 | Case attention alerts | 11 | Built, see notes |
| 11 | BNS, BNSS and BSA search | 12 | Built, see notes |
| 12 | AI-structured consultation | 3 | Built, see notes |
| S | Fee ledger with receipts and notices, client read-only view and chat, activity log, Ask | 15–18 | Built, see notes |

## Notes on what is proven and what is not

"Built" means the API has tests, the web and mobile screens typecheck and the web screens have tests. It does not mean
a person has used it. Nothing here has been tried against a real phone, a real browser session, PostgreSQL, or any live
provider.

| Area | Status |
|---|---|
| API logic, access rules, audit, approval flows | Tested (62 tests, SQLite, fake providers) |
| PostgreSQL migrations and the append-only audit trigger | Not run here. CI runs them on PostgreSQL 16 |
| OpenAI text tasks | Adapter written. Not called. Needs `OPENAI_API_KEY`. Prompts need tuning on real documents |
| Google Speech-to-Text and Vision OCR | Adapters written. Not called. Needs `GOOGLE_API_KEY` (use a service account in production). Phone recordings are AAC/m4a, which Speech-to-Text v1 does not read; convert on the server or record in another format before relying on voice from the phone. The web app records WebM/Opus, which it does accept |
| Scanned PDFs | Text-layer PDFs are read. Scanned PDFs need pages turned into images first (poppler); not done |
| SMTP email | Written. Not sent to a real server |
| Expo push | Written. Needs an EAS project id in `app.json` and a real device |
| WhatsApp | Click-to-send link only. Nothing is sent automatically |
| BNS, BNSS, BSA text and old-to-new mapping | The loader and templates are in `docs/statutes/`. **No official text is included.** Load your own data; every row is shown as Unverified until you mark it verified |
| Malayalam | Navigation labels and the reminder text are starter translations. A Malayalam reader must review them. Other screens are English only for now |
| Client chat policy and cost | Open item O-6 in the SRS |

## Running the reminder job

`python -m app.jobs.reminders` sends due reminders once. `--loop` repeats every 15 minutes.
`docker compose --profile worker up` runs it as a service. Quiet hours and the days before a hearing are firm settings.
