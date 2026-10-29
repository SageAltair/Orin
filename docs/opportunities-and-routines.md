# Opportunities, risks and routines

Opportunities is a private workspace for jobs, business openings, learning, creative collaborations, ministry and other possibilities. Capture a title and a small next action first; expand Context & decision when helpful. Stages are inbox, exploring, pursuing, waiting, won and closed. Project links are optional. Source URLs allow HTTP/HTTPS only. Review dates and deadlines remain explicit dates rather than invented schedules.

Value, fit and effort are self-ratings from 1–5. The list sorts by value + fit − effort. This heuristic supports comparison; it is not a probability of success, financial forecast or AI judgment. Review now filters dated items due for review. Creating the next task is idempotent while its task is active: repeated clicks open the same linked task, with the action as its first step. Once it is completed/cancelled, the next click creates a follow-up task from the current next action. Later opportunity edits do not silently rewrite an active task. Deleting the opportunity keeps its task and linked risks; the latter become independent records.

The Risk register works independently or links to an owned opportunity/project. It records likelihood, impact, warning signs, response strategy, mitigation, review date and status. Likelihood × impact orders the register: 15–25 high, 8–14 medium, 1–7 low. These are qualitative planning priorities, not measured probabilities. Resolved risks are hidden in Active and retained in All records. Transfer records a chosen strategy; it does not automatically transfer liability or contact anyone.

## Calendar routines

Use Calendar → Routines to create a daily or selected-weekday schedule with optional end date, IANA timezone, local start time and duration. Routines appear alongside events in month/week/day/agenda, but are calculated for the visible range rather than materialized into thousands of event rows. Click an occurrence to open the routine view. The schedule uses routine-local weekdays and dates; times in the calendar use its selected display timezone. Spring-forward times that do not exist are skipped. Repeated autumn times use the first occurrence. Occurrence requests are bounded to 93 days.

Each routine can contain a familiar cue, steps, minimum action/duration, and something to look forward to afterwards. The visible timer is a voluntary aid; it does not auto-complete a routine and resets if the workspace is unmounted/reloaded. Check-ins are full, minimum or skipped, with undo. Future or unscheduled check-ins are rejected. Missed days do not generate catch-up tasks or reset a punitive streak. Pausing hides occurrences and stops new reminders; resuming restores the schedule. Editing changes the repeating schedule and retains check-ins by their original dates. Delete removes the routine/check-ins. These are routines, not a general RFC 5545 recurrence editor.

In-app reminders are optional, at start or 5/10/15/30 minutes before. Background maintenance deduplicates delivery and suppresses reminders for checked-in days. It catches up until one hour after start. It does not provide email, SMS or operating-system push. Existing delivered notifications are historical records. Run background maintenance as described in operations.md.

## Evidence and boundaries

The design is informed by support strategies described by NIMH and NICE: consistent routines, breaking large tasks into smaller steps, written cues/instructions, shorter focus periods and breaks. The cue/minimum-version/reward workflow and non-punitive check-ins are product design choices; this implementation has not been clinically evaluated and does not diagnose or treat ADHD. Users can choose what helps them without declaring a diagnosis.

- NIMH: https://www.nimh.nih.gov/health/publications/attention-deficit-hyperactivity-disorder-what-you-need-to-know
- NICE NG87, environmental modifications: https://www.nice.org.uk/guidance/ng87/chapter/recommendations

All new records use authenticated, owner-scoped APIs and cascading account deletion. Account export includes these records through the existing metadata-based export. Lists support pagination, with the UI loading all owned pages. Dates, recurrence, rating bounds, URL schemes and linked ownership are validated server-side. This feature does not automatically apply for opportunities, scrape listings, contact people, make financial decisions, or expose planning records to AI providers.
