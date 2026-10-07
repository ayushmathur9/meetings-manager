# CRM sync, business summaries, meeting recordings

This document covers how the four Phase-2 features fit together and where to extend them. Each module's docstring holds the detail.

```
Bigin ──sync──▶ companies/contacts ──address──▶ Geoapify ──▶ map / route planner
                      │
                      └──▶ company page ──▶ Business Overview (website + CRM ──▶ Claude)
                                     └──▶ meeting ──▶ recording ──▶ AssemblyAI ──▶ transcript
Sidebar ──▶ Quote Builder (external URL from /app-config)
```

## Background work

`services/background.py` provides `submit()` for one-off jobs on a small thread pool, and `start_periodic_tasks()` for scheduled jobs that each run under a Postgres advisory lock.

There is no broker. Job state is a `status` column on the row being worked on, so after a restart the periodic tasks find unfinished rows and resume them:

| Job | Row / status | Recovery |
|---|---|---|
| Bigin sync | `bigin_sync_runs.status = running` | A `running` row older than 2 h is closed as failed; the next scheduled run picks up from the watermark. |
| Research | `company_research.status ∈ pending/researching/summarizing` | Re-queued on the next view if it hasn't moved for 15 min. |
| Transcription | `meeting_recordings.status = processing` | The poller polls stored job ids and resubmits stuck rows, up to 3 attempts. |

If load ever outgrows this, move these entrypoints onto a real queue. The candidates are `run_sync_job`, `run_research_job`, `process_recording_job` and `poll_pending_recordings`. Their signatures take only ids.

## Bigin (`services/bigin.py`, `services/bigin_sync.py`)

- **Matching.** Records are matched on `bigin_account_id` / `bigin_contact_id`, never on name. Only a record with no linked local row falls back to one unambiguous match, by phone or domain for companies and by email or phone within the same company for contacts.
- **Incremental sync.** Bigin's docs don't confirm `If-Modified-Since`, so each sync reads records sorted by `Modified_Time desc` and stops at the stored watermark, with a 10-minute overlap.
- **Deletions.** Deleted records are archived (`crm_deleted_at`), not removed. Archived companies disappear from prospects and route candidates; meetings and recordings attached to them are kept.
- **Addresses.** A changed address resets the primary location and is geocoded after the sync, through the existing `LocationService.verify_or_flag`. An address with no confident match is marked `NEEDS_REVIEW` and never given guessed coordinates.
- **Instant notifications.** Notification channels expire after one day, so the scheduled job renews them. Incoming notifications are authenticated by the channel id plus a secret token.

## Business summaries (`services/business_research.py`, `services/business_summary.py`)

- **Sources.** Each source gets a ref (`S1`, `S2`, …):
  - the CRM record
  - the verified address
  - up to 6 pages of the company's own website: visible text plus schema.org JSON-LD
- **Crawl limits.** The crawler honours robots.txt, re-checks every redirect hop against private IP ranges, and caps both response size and time.
- **What Claude does.** Claude (`SUMMARY_MODEL`) receives only those sources and returns structured JSON in which every claim cites refs. Claims citing nothing, or an unknown ref, are dropped before anything is stored.
- **When no LLM call is made.** If there is no public source (no website, or it couldn't be fetched), there is no LLM call and the UI says so.
- **What's stored.** `company_research.research_data` keeps the exact input, so a summary can be regenerated or audited without re-crawling.
- **Swapping providers.** Implement `SummaryProvider` and select it in `get_summary_provider()`.

## Recordings (`services/recording_service.py`, `services/transcription/`, `services/storage.py`)

- **Recording and upload.**
  - The browser records with `MediaRecorder` (Opus WebM, or MP4 on Safari).
  - The file goes to the API, which streams it to object storage.
  - Audio is never stored in Postgres and is never public: S3 audio is served as a 15-minute presigned redirect, and local audio is streamed by the API.
- **Access.** Admins can access any meeting's recordings. Salespeople can access only meetings assigned to them. Anyone else gets 404.
- **Providers.** All three implement `TranscriptionProvider`:

  | Provider | How it works | Notes |
  |---|---|---|
  | AssemblyAI (default) | Async: submit, then poll | Chosen for v1: takes a whole meeting from a URL (up to 10 h) with no chunking, has diarization, and a missed callback can't lose a transcript. |
  | Deepgram | Synchronous call inside the job | |
  | OpenAI | Synchronous call inside the job | Refuses files over 25 MB instead of chunking them. |

- **Speakers.** Labels are normalised to "Speaker 1, 2, …" in order of first appearance. No names are inferred.
- **Next phase.** `meeting_transcripts` is separate from the audio so that meeting summaries, action items and CRM notes can attach to it later. The "Generate Meeting Summary" button is a disabled placeholder.

## Quote Builder

`QUOTE_BUILDER_URL` (backend) is served by `GET /app-config`. The sidebar shows it as an external link that opens in a new tab. If the URL is unset, the link appears disabled with a "Not set" label.
