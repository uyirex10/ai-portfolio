# AI Voice Receptionist for Bookings (Harborview Dental Clinic, demo)

Status: Phase 8 adversarial testing complete for this build, all 20 planned calls attempted with real, documented results, including one critical finding not yet resolved. See below for exactly what was and wasn't verified.

## Problem

A dental clinic needs a natural-sounding voice agent to handle intake and appointment booking over the phone: connect to the clinic's calendar, capture caller details, qualify callers by intent (booking, reschedule, general question, emergency), send SMS confirmations, and hand off angry or emergency callers to a human immediately. Based on a real Upwork brief posted by a voice-AI agency. Built here against a fictional demo identity, Harborview Dental Clinic, Port Harcourt.

## Results

- **All 20 planned adversarial tests attempted.**
- **Critical, unresolved finding**: in one real call, `book_appointment` fired on an incomplete caller response that never named a specific time, booking the wrong slot. This is a real violation of the system's core confirmation safeguard, not yet fixed or re-verified. See Known Limitations.
- **check_availability / book_appointment latency**: real figures pulled from Airtable across multiple calls show a wider spread than early testing suggested, roughly 1,500ms on the fast end up to 4,759ms on the slow end. `book_appointment` specifically ran over the 2-second ceiling in the majority of calls checked, not the minority, this corrects an earlier, smaller-sample assumption that most calls landed in the 700ms-2s range. Root cause not isolated, Google Calendar API response variance is the leading suspect, not yet confirmed.
- **Double-booking race test**: passed, no double-booking observed.
- **Anger-trigger escalation**: confirmed working in 1 of 2 real attempts, the second is the critical finding above, the anger in that call was a genuine reaction to a real wrong booking, not simulated.
- **Emergency escalation (in-hours)**: confirmed working correctly, a single red-flag sign (e.g. swelling alone) is sufficient to trigger escalation without requiring multiple signs present.
- **Emergency escalation (after-hours)**: correct in 2 of 3 real attempts. The one failure has an identified, documented cause, not an unexplained flake, see Known Limitations.
- 3 demo recordings: selection still pending.

## Architecture

Three tool concepts, one execution split:

1. **`check_availability`** (sync) queries Google Calendar freebusy for a requested day, returns open slots. Must stay fast, the caller is on hold in real time.
2. **`book_appointment`** (sync) re-verifies the slot is still free immediately before writing the event, closing the race condition where two callers get told the same slot is open.
3. **`transfer_to_human`** uses Vapi's native Transfer Call tool type directly, no custom webhook, since redirecting a live call is a telephony capability, not something n8n needs to mediate.
4. **Post-call chain** (async), triggered off Vapi's end-of-call event: transcript → Gemini summary → Airtable log → SMS confirmation → Slack note. No latency pressure, the caller has already hung up.

Implementation note: `check_availability`, `book_appointment`, and the post-call chain currently run as three branches of a single n8n workflow (three separate webhook triggers on one canvas), rather than three independent workflows. Functionally equivalent, but worth knowing when reading the Executions tab, fast tool-call runs and the much slower async summarization runs show up interleaved in one list rather than three.

## Tools used

- **Vapi.ai**, voice platform, sync/async Function Tool split, Live Call Control for transfers
- **n8n**, self-hosted locally, all tool logic and the post-call chain
- **Google Calendar API**, OAuth, freebusy.query and events.insert
- **Twilio**, SMS confirmations (trial tier)
- **Airtable**, call log
- ElevenLabs was evaluated and skipped, Vapi's default voice was sufficient for this build

## Key decisions

- **Booking-race fix:** the brief only described a mid-call availability check and a post-call confirmation chain, it never specified when the calendar event actually gets written. Writing the event live, as a second synchronous tool with a re-verify-before-write step, closes the double-booking window that a purely async design would leave open. *This closes the double-write race specifically. A separate, more basic confirmation failure was found in real testing, see Known Limitations, the two are not the same problem and the second one is not yet resolved.*
- **Escalation detection:** originally planned to detect a transfer by checking Vapi's `transfers` array in the end-of-call report. That array only reflects completed transfers, not attempted ones. Switched to detecting whether the assistant called `transfer_to_human` at all, which is also the more meaningful signal for staff regardless of whether the telephony leg connected.
- **Latency budget:** Vapi's own guidance caps a blocking webhook at roughly 100ms of processing; the brief's "feels broken at 3 seconds" is the caller-facing failure point, not the engineering target. Built and tested against the tighter number, treating 2s as an absolute ceiling rather than a goal. *The target was set correctly, real testing shows it wasn't consistently met, `book_appointment` ran over 2s in most checked calls, see Results and Known Limitations rather than treating this as solved.*
- **Emergency escalation, single-sign rule:** real adversarial testing surfaced a genuine bug, the agent required something close to multiple red-flag signs together before escalating, when the brief's own logic says any one sign (e.g. swelling alone) should be sufficient. Fixed with an explicit instruction that a single sign is enough on its own. This is the clearest example in the whole build of a bug that only real testing, not prompt review, would have caught.

## Known limitations

- **Critical, unresolved: `book_appointment` can fire without a genuinely confirmed time.** A real call showed the agent booking the first offered slot after the caller's response trailed off mid-sentence ("Uh, that's.") without ever naming a specific time. This is a real violation of the system's core hard rule, not a minor edge case, and the caller's resulting anger in that call was a justified reaction to a wrong booking, not simulated frustration. Possible cause: Vapi's voice-endpointing may be cutting the caller's turn short before they finish speaking, rather than a pure prompt-following gap, not yet confirmed either way. Checked against the other 19 real calls, this specific pattern wasn't observed elsewhere, one confirmed occurrence, not a repeatable ratio like the after-hours issue below. That rules out "constant failure," it doesn't rule out recurrence, a sample of 20 isn't enough to call it a true one-off. Not fixed. Not re-verified. This is the single most important open item in this project.
- **`book_appointment` latency exceeded the 2-second target in most real calls checked, not a rare exception.** Values from Airtable range roughly 1,500ms to 4,759ms, with the majority of `book_appointment` calls landing over 2s. This corrects an earlier, smaller-sample claim that most calls were in the 700ms-2s range. Root cause not isolated, Google Calendar API response variance is the leading suspect.
- Twilio's trial tier blocks both free-text SMS bodies and the Content Template API. SMS failures are handled with a retry-then-dead-letter path rather than upgrading Twilio for a demo.
- Vapi's free/trial phone numbers are inbound-only, so live call transfers don't actually connect, the tool call itself completes correctly and is logged, but the telephony leg fails. Documented as a trial-tier limitation rather than paid around.
- ngrok's free tier changes the tunnel URL on every restart, requiring a manual update across every tool pointing at it.
- Timezone handling (WAT to UTC) is hardcoded for Port Harcourt, not dynamic.
- **After-hours emergency escalation has an identified failure pattern, not fully resolved.** In 1 of 3 real attempts, a garbled report that required back-and-forth clarification before the emergency was confirmed caused the agent to lose track of needing to re-check the current time before choosing how to escalate, resulting in an attempted transfer instead of the correct ER redirect. The other 2 attempts, including ones with similarly unclear speech, resolved correctly. Documented as a real, specific limitation under conversational ambiguity, not silently fixed and not left unexplained.
- **The Airtable call log's Booked Slot field can record the wrong time**, confirmed once, a one-hour discrepancy matching the WAT/UTC offset, most likely a timezone construction bug in the post-call summary step. Affects the staff-facing log only, no evidence the real Google Calendar event or what the caller was told was ever wrong.

## Testing summary

All 20 planned adversarial tests were run against the live system, real phone calls, real transcripts, real Airtable logs, not simulated. Full call-by-call detail, including exact transcripts and root-cause notes for each finding above, is in the companion test plan document. Every scenario, happy-path booking, mumbled speech recovery, mid-call mind-changing, off-script questions, ambiguous confirmations, reschedule requests, general FAQ handling, anger-trigger escalation, a real (unplanned) Calendar API outage, the double-booking race condition, and emergency escalation both in and after hours, was tested against the real, running system, and every finding above, including the critical one, came from an actual call, not a hypothetical.

## How to run / demo (pending)

*Demo recording links to be added once the 3 best calls are selected from the full Phase 8 run.*
