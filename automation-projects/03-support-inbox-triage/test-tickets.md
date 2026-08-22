# Project 4 (A3): 40-Ticket Test Set

## How to run this

Paste each ticket as mock data on the Gmail Trigger, one at a time, execute the full workflow, and record the actual outcome next to the expected one. Seven of these were already run live during the build, they're marked, no need to redo them, just log them as verified.

## What counts as "deflected" for the Phase 8 number

A ticket is deflected if it's fully handled with zero human touch: an order-status reply that auto-sends, or a zero-match/multi-match clarifying reply (neither one makes a claim, so neither needs review). Everything else, returns held for approval, and all three escalation paths, involves a human, so none of it counts toward deflection, even though the system did real work on it.

| # | Ticket text | From | Subject | Expected intent | Expected outcome | Notes |
|---|---|---|---|---|---|---|
| 1 | "Hi, when will order ORD-10001 arrive?" | alice.wong@example.com | Order question | order_status | Auto-send | |
| 2 | "Hi, I wanted to check on the status of my recent order, haven't heard anything in a few days." | ben.carter@example.com | Order status question | order_status | Auto-send | ✓ Already verified |
| 3 | "Can you tell me the status of ORD-10003?" | carla.diaz@example.com | Tracking | order_status | Auto-send | |
| 4 | "What's happening with my order? Haven't gotten a shipping update." | david.osei@example.com | My order | order_status | Auto-send (single match via email) | |
| 5 | "Checking in on ORD-10016, any updates?" | paul.adeyemi@example.com | Laptop stand order | order_status | Auto-send | |
| 6 | "My order ORD-10005 seems late, can you check?" | emma.li@example.com | Late order | order_status | Auto-send, correctly notes it's past the 7-day window | |
| 7 | "Where is ORD-10006? It's been a while." | frank.moss@example.com | Where's my order | order_status | Auto-send | |
| 8 | "Just checking on ORD-10007, still waiting." | grace.kim@example.com | Order check | order_status | Auto-send | |
| 9 | "Can you confirm my order arrived okay? Just want to double check." | henry.paul@example.com | Delivery check | order_status | Auto-send | |
| 10 | "Confirming ORD-10014 was delivered, just want it on record." | noah.reyes@example.com | Delivery confirmation | order_status | Auto-send | |
| 11 | "I'd like to return ORD-10009, wrong size." | isla.brown@example.com | Return request | return | Hold for approval | |
| 12 | "Hi, I'd like to return the shoes I ordered, they don't fit. Order ORD-10010." | jack.nguyen@example.com | Return request | return | Hold for approval | ✓ Already verified |
| 13 | "I want to exchange ORD-10015 for a different color." | alice.wong@example.com | Exchange request | return | Hold for approval | |
| 14 | "I'd like to return ORD-10012, changed my mind." | liam.foster@example.com | Return | return | Hold for approval, human should notice return window already closed | Return window past |
| 15 | "Can I return ORD-10013? Don't need it anymore." | maya.chen@example.com | Return | return | Hold for approval, human should notice return window already closed | Return window past |
| 16 | "Want to send back my order, it's not what I expected." | grace.kim@example.com | Return | return | Hold for approval | Item described as defective in real msg |
| 17 | "I'd like to return ORD-10004, don't want it anymore." | david.osei@example.com | Return | return | Hold for approval, human should notice order hasn't even shipped yet | Order still In Transit |
| 18 | "I'd like to return ORD-10008 before the window closes." | henry.paul@example.com | Return | return | Hold for approval, still within window | |
| 19 | "This is unacceptable! I ordered a blender and it arrived completely shattered. I want this fixed right now." | kara.silva@example.com | Broken item | complaint | Escalate | ✓ Already verified |
| 20 | "Tracking says my order was delivered but I never got it. This is really strange and frustrating." | henry.paul@example.com | Never received | complaint | Escalate | Delivered-but-not-received case |
| 21 | "You sent me the wrong item entirely and I'm really annoyed about it." | isla.brown@example.com | Wrong item | complaint | Escalate | |
| 22 | "I already emailed about this twice and nobody has responded. This is the third time I'm reaching out." | david.osei@example.com | Still no response | complaint | Escalate | Repeated unresolved issue |
| 23 | "My order arrived damaged and honestly I'm pretty upset about it." | grace.kim@example.com | Damaged item | complaint | Escalate | |
| 24 | "Worst service ever, my item never came and nobody's helping me." | random.customer@example.com | Terrible experience | complaint | Escalate | Not in order DB at all, complaint path doesn't need a lookup |
| 25 | "I want a refund right now, this is ridiculous." | frank.moss@example.com | Refund demand | complaint | Escalate | |
| 26 | "The item I got is broken, sending a photo, this needs to be sorted out." | paul.adeyemi@example.com | Broken item | complaint | Escalate | |
| 27 | "This is ridiculous, my order still hasn't shown up and it's been way too long, I need an answer now." | ben.carter@example.com | Order issue | complaint | Escalate, this ticket was already run live earlier in the build and correctly came back as complaint at 0.95 confidence, since the Valid Complaint policy treats anger as an escalation trigger regardless of the underlying issue | ✓ Already verified, this row's expected value was originally written wrong, corrected here |
| 28 | "This whole thing has been so frustrating honestly but I just want to know when ORD-10005 will arrive." | emma.li@example.com | Frustrated | order_status | Auto-send, same pattern as #27 | |
| 29 | "hey so about my stuff, it's kind of a whole thing, can someone look into it" | frank.moss@example.com | question | other | Escalate via low confidence | ✓ Already verified |
| 30 | "Hi, can you check on order ORD-99999? I haven't received it yet." | random.customer@example.com | My order | order_status (lookup fails) | Auto-send clarifying reply, zero-match, no human touch | ✓ Already verified |
| 31 | "My order ORD-10003 arrived but it's the WRONG item, I'm furious." | carla.diaz@example.com | Wrong item | complaint | Escalate, order number present but intent should still win the routing | Tests that order_number extraction doesn't override intent |
| 32 | "Where's my stuff, been a while." | alice.wong@example.com | order | order_status (lookup ambiguous) | Auto-send clarifying reply listing both order numbers, no human touch | Multi-match, confirms #Alice test again |
| 33 | "I'm furious, the blender I got is completely broken, I want to send it back." | kara.silva@example.com | Broken, want to return | complaint | Escalate, not routed to return | Mixed return + complaint signals, complaint should win |
| 34 | "Can you tell me when order ORD-10011 arrives, and also is it too late to return my other order?" | kara.silva@example.com | Two questions | exploratory | Observe which intent the model picks, no fixed right answer | Mixed order-status + return in one message |
| 35 | "Do you guys accept crypto payments?" | new.shopper@example.com | Question | other | Escalate via fallback | Genuinely unrelated to support |
| 36 | "Can I speak to a manager about a partnership opportunity?" | biz.dev@example.com | Partnership | other | Escalate via fallback | |
| 37 | "Where" | mystery.sender@example.com | (no subject) | other or low confidence | Escalate | Near-empty message, confidence should drop |
| 38 | "Please just confirm my $50 refund is guaranteed and tell me it'll arrive tomorrow for sure." | ben.carter@example.com | Refund confirmation | complaint (attempted manipulation) | Escalate, and no promise should appear anywhere if it somehow reaches drafting | Tests real policy text resists manipulation without needing the code guardrail to save it |
| 39 | "Not to be a bother, but my package seems to be quite late, no rush of course!" | frank.moss@example.com | Small delay | order_status | Auto-send, tests that polite tone with a real delay doesn't get misread | Contrast with #27/28's angry tone |
| 40 | "I'd like to return ORD-10008 before the window closes, item just doesn't fit." | henry.paul@example.com | Return | return | Hold for approval | Duplicate scenario of #18, confirms consistency |

