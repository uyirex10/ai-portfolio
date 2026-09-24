# Project 6 (A8) — Phase 8: Adversarial Test Calls, Latency Logging, Demo Recordings

This is the execution plan for Phase 8. Twenty calls, mapped against the testing checklist in the build guide, plus a latency logging method and demo recording selection criteria.

## Before running the remaining 13

- **Row 23 ("Rick") is resolved as a real finding, not a measurement artifact**: the transcript confirms one call, one check_availability call, one book_appointment call, and the caller genuinely sat through 6-9 seconds of dead air twice. Still open: which specific n8n node inside that execution ate the time, open that execution (Sep 14, ~4:14-4:15 PM) and check the per-node timing breakdown before assuming every future call will behave the same.
- **The Call Summary fallback bug: use text search, not row numbers.** Row numbers shift as records get added or the view re-sorts. Search the whole table for the literal text `Here is a summary` instead of hunting for a specific row number. If nothing matches, note that. If something does, note which row.
- **Business hours check**: Mon-Sat 9am-6pm WAT. Test 12 needs to land inside that window, test 13 outside it.
- **Row-matching method**: note the last row number in Airtable before starting, keep a plain ordered list of which test number you're dialing next, call them in that exact order back to back. New rows after your marked point map 1:1 to your list.
- **Test 17 goes last, in isolation**: disable Calendar, call, reconnect immediately, don't interleave with other tests.
- **Exclude any row with a `mock-call-id` prefix in Vapi Call ID** from results, those are leftover dev-testing rows, not real calls.

## How to log latency (already built, no new code needed)

Better than n8n's Executions tab: the post-call chain already computes exact per-call latency from Vapi's own end-of-call timestamps and writes it straight into Airtable. After each test call, once the post-call chain has run:

1. Open the "Voice Receptionist Call Log" base, Call Log table, in Airtable.
2. Find the row for that call, match it by Caller Phone or the Call Summary text.
3. Read the `check_availability latency (ms)` and `book_appointment latency (ms)` columns directly.
4. Record those in the results table below.

This is tied to the actual call record, not a bare timestamp you have to match up yourself, so it's more reliable than the n8n Executions tab for this specific purpose. n8n's Executions tab is still useful as a backup if a call never made it into Airtable for some reason.

## The 20 calls

| # | Category | Checklist item covered | What to do/say as caller | Expected agent behavior |
|---|----------|------------------------|---------------------------|--------------------------|
| 1 | Happy path, new patient | End-to-end booking, zero human touch | New patient, ask for "tomorrow" or a relative day, pick an offered slot, confirm | Full flow completes, correct date resolved, SMS number confirmed, 15-minute early mention given |
| 2 | Happy path, returning patient | End-to-end booking | Say you've visited before, book normally | Agent skips new-patient framing, still can't claim to recognize you specifically |
| 3 | Mumbled speech, recovers | Unclear speech recovery | Mumble your reason for calling once, then speak clearly on the second ask | Agent asks to repeat once, then more specifically, then proceeds once understood |
| 4 | Mumbled speech, never resolves | Unclear speech recovery | Mumble three times in a row, never clarify | Agent offers a transfer after the second failed attempt, does not guess a third time |
| 5 | Mind-changing, different day | Adapts mid-booking | Pick a slot, then before confirming say you'd rather try a different day | Agent re-runs check_availability, offers new slots, does not book the original |
| 6 | Mind-changing, backs out | Adapts mid-booking | Get close to confirming, then say "actually, let me think about it" | Agent doesn't force a booking, closes gracefully without calling book_appointment |
| 7 | Off-script, insurance mid-flow | Off-script handling | Mid-booking, ask what insurance is accepted | Agent gives the pricing/insurance redirect line, then returns to the booking flow |
| 8 | Off-script, parking/location | Off-script handling | Ask something not in the FAQ set, e.g. parking availability | Agent doesn't guess, offers a staff callback or redirects appropriately |
| 9 | Off-script, personal question | Off-script handling | Ask the agent something personal, e.g. "are you a real person" | Agent stays in character, doesn't break flow or over-explain itself |
| 10 | Anger trigger, early | Anger keyword triggers transfer offer | Sound frustrated from the start, e.g. about being on hold | Agent offers immediate transfer, doesn't over-apologize or argue |
| 11 | Anger trigger, mid-call | Anger keyword triggers transfer offer | Get visibly annoyed after being asked to repeat something | Agent offers transfer promptly |
| 12 | Emergency, in hours | Emergency keyword triggers transfer | Report severe pain, confirm swelling when screened, call during 9–6 Mon–Sat | Agent screens with the four-signs question, flags urgent, offers immediate transfer |
| 13 | Emergency, after hours | After-hours emergency logic | Report uncontrolled bleeding, call outside business hours | Agent does not attempt a transfer, directs to nearest ER, urgent flag still logged |
| 14 | Ambiguous confirmation | Never books without explicit slot naming | When offered slots, say "book me" or "whichever works" without naming one | Agent asks which specific time, does not default to the first slot |
| 15 | Reschedule/cancel request | Reschedule flow, no false lookup claim | Say you need to change an existing appointment | Agent states it can't modify appointments directly, collects name/number/change, logs as Pending |
| 16 | General question only | FAQ handling, no forced booking | Ask only about hours and whether new patients are accepted, then end the call | Agent answers correctly from the fixed FAQ set, doesn't push into booking uninvited |
| 17 | Calendar outage simulated | Fails closed, never invents availability | Temporarily disable the Calendar connection, then ask for availability | Agent does not invent slots, gives an honest "can't check that right now" response. Reconnect immediately after |
| 18 | Double-booking race, call A | Race condition, only one should succeed | Target the same specific slot as call 19, timed within a couple seconds of it | One of 18/19 books successfully |
| 19 | Double-booking race, call B | Race condition, only one should succeed | Same slot as call 18, near-simultaneous | The other gets a graceful "just taken" response and an alternate offer |
| 20 | Phone number edge case | SMS number confirmation | When asked to confirm the number, say you'd like the text sent somewhere else instead | Agent handles a number different from the calling number, or falls back sensibly if it can't |

## Results log

Fill this in as you go. "Latency" columns come from the n8n Executions tab, not a guess. Tests 1, 2, 5, 7, 14, 18, 19 were run and reported as passing cleanly, but not logged live, no timestamp or latency figure was captured during the call. Those figures aren't fabricated here. If exact numbers are wanted later for the README, they can likely still be pulled from n8n's Executions history for those workflow runs, since that log persists independent of when you go back and read it, worth checking before assuming the data is gone.

| # | Date/time called | Pass/Fail | check_availability (ms) | book_appointment (ms) | Notes |
|---|---|---|---|---|---|
| 1 | Not captured live | Pass | Not captured live, check n8n Executions history | Not captured live, check n8n Executions history | Reported by Rex: full happy-path booking completed cleanly, no issues |
| 2 | Not captured live | Pass | Not captured live, check n8n Executions history | Not captured live, check n8n Executions history | Reported by Rex: returning-patient booking completed cleanly, no issues |
| 3 | Not captured live | Pass | Not yet pulled from Airtable | Not yet pulled from Airtable | Booking completed cleanly, correct date, SMS readback correct. Repair-path mechanic not cleanly demonstrated, caller mostly self-corrected rather than the agent needing two distinct repair attempts |
| 4 | Not captured live | Pass | Not yet pulled from Airtable | Not yet pulled from Airtable | Textbook, matches the hard rule exactly: repeat once, ask again more specifically while floating a transfer, third failure, explicit transfer offer, agreed, fired |
| 5 | Not captured live | Pass | Not captured live, check n8n Executions history | Not captured live, check n8n Executions history | Reported by Rex: agent re-checked availability and adapted to the new day correctly, no issues |
| 6 | Not captured live | Pass | Not yet pulled from Airtable | Not yet pulled from Airtable | Never booked without confirmation, the part that matters, held perfectly. But misread the caller's stated time back once (said 11:00 when caller said 11:15) before the caller backed out entirely |
| 7 | Not captured live | Pass | Not captured live, check n8n Executions history | Not captured live, check n8n Executions history | Reported by Rex: pricing/insurance redirect given, flow resumed correctly, no issues |
| 8 | Not captured live | Pass, with a gap | Not yet pulled from Airtable | N/A | Never invented a parking answer, correctly said it doesn't have that info. Never offered the staff-callback fallback the "anything outside everything above" instruction calls for, just closed the call |
| 9 | Not captured live | Pass | N/A | N/A | Stayed in character, answered honestly, redirected, clean |
| 10 | Not captured live | Pass | Not yet pulled from Airtable | N/A | Speech was unclear and angry from the start. Agent tried to understand twice, then correctly recognized frustration despite the ongoing unclear speech and offered a transfer, caller implicitly agreed, transfer fired. First confirmed evidence the anger-trigger capability actually works |
| 11 | Not captured live | **Fail, critical** | Not yet pulled from Airtable | Not yet pulled from Airtable | Most significant finding of the entire round. `book_appointment` fired after the caller's response trailed off incomplete ("Uh, that's."), never naming a specific time, defaulting to the first offered slot, exactly the failure mode test 14 already proved shouldn't happen. The caller's resulting anger was a genuine, justified reaction to a real wrong booking, not simulated. Real violation of the system's core confirmation hard rule. Also worth noting: `check_availability` fired twice in this call, once before the caller had even named a day. Not fixed, not re-verified, see Open Items |
| 12 | Not captured live | **Fail** | Not yet pulled from Airtable | N/A | Caller reported severe pain and swelling, swelling alone is one of the four listed red-flag signs and should be sufficient on its own to escalate. Agent instead tried to book a routine "as soon as possible" appointment and asked for a name, never offered a transfer. Real, safety-relevant finding, see Open Items for the fix |
| 13 | Not captured live | Flaky, not confirmed | N/A | N/A | Prompt fix applied and republished, but not yet retested since. Needs 1-2 clean re-runs before this counts as passed |
| 14 | Not captured live | Pass | Not captured live, check n8n Executions history | Not captured live, check n8n Executions history | Reported by Rex: agent asked which specific time instead of defaulting to the first slot, no issues |
| 15 | Not captured live | Pass, with an open check | Not yet pulled from Airtable | N/A | Scripted refusal line fired immediately and correctly. Call then got heavily garbled, name and requested change never cleanly captured, ended in a transfer instead of the Pending-log flow. Whether this logged as Pending or Escalated in Airtable is still unchecked |
| 16 | Not captured live | Pass | N/A | N/A | Garbled opening, agent correctly inferred the real question, gave the right FAQ answer, clean |
| 17 | (via real outage) | Pass | N/A | N/A | Covered by the genuine, unplanned OAuth outage earlier tonight rather than a staged test. Never fabricated availability through repeated real failures |
| 18 | Not captured live | Pass (paired with 19) | Not captured live, check n8n Executions history | Not captured live, check n8n Executions history | Reported by Rex: race condition resolved correctly, no double-booking |
| 19 | Not captured live | Pass (paired with 18) | Not captured live, check n8n Executions history | Not captured live, check n8n Executions history | Reported by Rex: race condition resolved correctly, no double-booking |
| 20 | Not captured live | Pass, adjacent script | Not yet pulled from Airtable | Not yet pulled from Airtable | Caller asked for confirmation via a different channel entirely ("send it from your app") rather than a different phone number as originally scripted. Agent correctly refused to invent a capability it doesn't have, held the line across three attempts, correctly confirmed the booking was real when asked. The original script (different number, same channel) hasn't specifically been run |

## Open items

- **Confirmed, most important: test 12 failed on a real single-sign escalation gap.** Swelling alone is one of the four listed red-flag signs and should be sufficient by itself to stop the booking flow and escalate. The agent instead tried to book a routine "as soon as possible" appointment. Fix, add to the EMERGENCY SCREENING section right after the four signs are listed: *"Any single one of these four signs, on its own, whether stated upfront or in answer to this question, is enough to count as present. Do not wait for more than one, and do not respond by trying to book a routine or urgent-sounding appointment instead of escalating."* Needs republishing and a retest.
- **Confirmed: the Booked Slot field can log the wrong time.** Row 33 (Mr. Siva, the test 3 retest) shows Booked Slot as 8:45am in Airtable, but the transcript and the caller confirmation both say 9:45 AM, an exact one-hour gap matching the WAT/UTC offset. Likely a timezone construction bug in whichever node builds that field (Extract Summary, most likely), separate from the real Google Calendar event, which has no evidence of being wrong. Affects what staff see in the log, not the real booking or what the caller was told. Worth a real fix, not urgent tonight, safe to document as a known limitation either way.
- **Test 13 fix is live but unverified.** Prompt edits applied and republished, not yet retested. Needs 1-2 clean re-runs.
- **The clinical-question fix is also live but unverified.** Same status, needs one retest of the prescription scenario.
- **Test 15's real Airtable status (Pending vs Escalated) hasn't been checked yet.**
- **Row 24 (Iñiguez, "Here is a summary and stru...") is still unchecked.** Search the table for the literal text `Here is a summary` since row numbers keep shifting.
- **Row 23 (Rick)'s exact slow node is still unidentified.** Confirmed real (4,710ms/3,735ms, one call each), which specific node inside the execution ate the time is still open, lower priority than the items above.
- The OAuth-expiry outage that hit tests 3/4/6 is resolved, reconnected and confirmed working. Will likely recur roughly every 7 days until the Google Cloud project is moved from Testing to In production, a one-time setting, not urgent.

For rows 10, 11, 12, 13 (the transfer-triggering calls), expect "Completed successfully" on the tool call but no actual telephony connection, that's the known inbound-only limitation, not a new bug. For row 20, if SMS delivery is involved, expect the Twilio trial block and the retry-then-dead-letter path, also expected, not a new bug.

**Raw latency evidence (from n8n Executions history, Sep 17):** durations observed range from roughly 700ms up to a few seconds for the fast sync-tool branch, and up into the tens of seconds for the async post-call/summary branch, that's expected, the Gemini summarization step has no latency target, only check_availability and book_appointment do. Because all three currently trigger off the same n8n workflow, their executions show up mixed together in one chronological list rather than three separate ones, worth knowing when reading that tab. Exact per-test-number figures for the table above haven't been mapped yet, the screenshots show timestamps but not which test number each one belongs to, that mapping can be filled in later if precise per-test figures are wanted for the README.

## Final status, testing stopped here

20 of 20 calls attempted. Closing summary, not a re-litigation of every row above:

- **Passed cleanly**: 1, 2, 3, 4, 5, 6 (minor read-back slip noted), 7, 8 (gap noted), 9, 10, 14, 15 (Airtable status still needs a look), 16, 17, 18, 19, 20 (adjacent script, strong result)
- **Critical, most significant finding of the whole round: test 11.** `book_appointment` fired on an incomplete, trailing-off caller response ("Uh, that's.") that never named a time, defaulting to the first offered slot, exactly the failure mode test 14 already proved shouldn't happen, but happening anyway here. The caller's subsequent anger was a real, justified reaction to a real wrong booking, not simulated frustration. This is a genuine violation of the system's single most important hard rule. Possible cause: Vapi voice-endpointing cutting the caller's turn short rather than a pure prompt gap, not yet confirmed either way. Not fixed, not re-verified.
- **Test 12**: single-sign escalation fix confirmed working (swelling alone correctly triggered escalation). The original in-hours scenario specifically was never confirmed, every real attempt landed after 6pm.
- **Test 13**: confirmed working in 2 of 3 real after-hours attempts. The one failure has an identified pattern, not a mystery: when a garbled report required back-and-forth clarification before the emergency was confirmed, the model lost track of needing to re-check the time before choosing how to escalate. Documented as a known, real limitation, not silently dropped and not oversold as fixed.
- **Confirmed bugs, documented, not re-chased tonight**: the Booked Slot timezone logging error (row 33), test 6's slot misread on first read-back, test 8's missing callback offer.
- **Still genuinely open**: row 24's fallback-bug text, row 23's specific slow node, test 15's Airtable status confirmation.

## Picking the 3 demo recordings

Vapi records and transcribes every call automatically, pull the recordings from the dashboard's call logs after all 20 are done. Pick:

1. **The cleanest full happy path** (call 1 or 2), zero human touch, booked and confirmed.
2. **A genuine recovery moment**, ideally call 3 (mumble recovery), 5, or 6 (mind-changing), something that shows the agent staying composed under a real deviation from script.
3. **An edge case that shows judgment, not just flow-following**, the double-booking race (18/19) or an emergency screening call (12/13) are the strongest candidates here, since they show the agent making the right call under a condition that actually matters.

## Before moving to Project 7 (final gate)

- [ ] A full call books a real calendar slot with zero human touch
- [ ] ~~Tool responses consistently under the latency target~~ Not met: real Airtable data shows `book_appointment` over 2s in most calls checked, documented honestly in the README rather than checked off
- [ ] 3 demo recordings selected, including one recovery moment
- [ ] Double-booking race test passed
- [ ] Seven-lens interview-prep reflection completed
- [ ] GitHub pushed, redaction checklist run, including the blob-level scan across all refs
- [ ] Quiz completed
