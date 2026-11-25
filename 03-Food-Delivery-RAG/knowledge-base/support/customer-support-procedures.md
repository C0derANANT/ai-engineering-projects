# Customer Support Procedures

_Last updated: 15 November 2026 · Owner: Customer Experience (CX) · Audience: support agents, team leads and anyone answering customer questions_

## 1. Support channels

| Channel | Availability | Who can use it | Target first response |
|---|---|---|---|
| In-app chat (Crave Assist bot, then a human agent) | 24x7 | All customers | Bot: instant. Human: under 60 seconds for live orders, under 3 minutes otherwise |
| Priority callback | 24x7 | CraveCart Plus members; all customers for safety issues | Callback within 10 minutes |
| Email (`support@cravecart.example`) | 24x7, worked 8 am–11 pm | All customers; for non-urgent, non-live-order issues | Within 24 hours |
| Grievance Officer (`grievance@cravecart.example`) | Business days | Unresolved complaints | Acknowledged within 48 hours; resolved within 1 month |
| Social media (official handles) | 9 am–11 pm | Public complaints | Within 1 hour; moved to a private channel |

**Languages:** English and Hindi 24x7. Tamil, Telugu, Kannada, Marathi, Bengali, Gujarati, Malayalam and Punjabi from 9 am to 11 pm. Customers pick their language in Help > Settings > Support language.

**CraveCart never:**

- asks for OTPs, UPI PINs, card numbers, CVVs or passwords,
- asks customers to install screen-sharing or remote-access apps,
- asks for money to process a refund,
- calls from personal mobile numbers.

Agents must remind customers of this whenever fraud is suspected.

## 2. Support tiers

| Tier | Team | Handles |
|---|---|---|
| **Tier 0** | Crave Assist (AI assistant) | Order status, ETA updates, simple cancellations, clear-cut refunds under ₹300, FAQs, address changes within policy |
| **L1** | Frontline chat and email agents | Live order issues, refunds up to their limit, account questions, coupon issues |
| **L2** | Specialist queues: Payments, Food Safety, Trust & Safety, Restaurant Escalations, Account Security | Complex refunds, payment reconciliation, food safety, harassment and safety, account takeovers |
| **L3** | Internal teams: Engineering on-call, Legal, Restaurant Operations, Fleet Operations | Bugs, legal notices, restaurant audits, partner investigations |

## 3. Ticket priorities and SLAs

| Priority | Examples | First response | Resolution target |
|---|---|---|---|
| **P1 – Critical** | Safety threat, accident, harassment, food poisoning, foreign object, account takeover, data leak | 5 minutes | Contain within 30 minutes; resolve within 24 hours |
| **P2 – High** | Live order problems: late, stuck, partner can't find address, wrong address | 2 minutes | 15 minutes, or before the order is delivered or cancelled |
| **P3 – Medium** | Post-delivery problems: missing, wrong or spilled items, quality, "not received" | 3 minutes in chat; 24 hours in email | 24 hours |
| **P4 – Low** | Payments and refund status, invoice requests, Plus questions, account changes, feedback | 24 hours | 72 hours |

SLA breaches are automatically escalated to the team lead on shift. P1 breaches page the CX duty manager.

## 4. The standard handling flow

Every contact follows the **VERIFY → UNDERSTAND → CHECK → RESOLVE → CONFIRM → DOCUMENT** flow.

### 4.1 Verify

- Customers in the app are already logged in. No extra verification is needed for order questions.
- **Email and social contacts:** ask for the order ID and the last 4 digits of the registered mobile number. Never ask for an OTP.
- **Account changes** (phone number, email, account deletion) need re-verification inside the app, which sends an OTP the customer enters **in the app**, not to the agent.

### 4.2 Understand

- Let the customer explain. Restate the problem in one sentence: "So the Butter Chicken was missing and the naan arrived cold, is that right?"
- Identify **all** issues before resolving any of them.

### 4.3 Check

Open the order in the **Agent Console** and review:

- the order timeline (placed, accepted, preparing, food ready, partner assigned, picked up, delivered),
- the promised delivery time (`promised_delivery_at`) and actual delivery time,
- partner GPS trail and delivery photo or PIN status,
- refund and claim history for the account (last 30 and 90 days),
- account flags (refund review, COD disabled, fraud watch).

### 4.4 Resolve

Apply the relevant policy:

- Cancellations: `policies/cancellation-policy.md`
- Refunds: `policies/refund-policy.md`
- Delays: `ordering/delivery-times.md`
- Changes: `ordering/modifying-an-order.md`

Offer the customer a choice where policy allows (for example, "a refund to CraveCart Money right now, or to your UPI account in 1–3 business days").

### 4.5 Confirm

- Say exactly what was done, the amount, where it goes and when: "I've refunded ₹283.50 to your UPI account. You'll see it within 1–3 business days. Your refund reference will be in the order page within 48 hours."
- Ask: "Is there anything else I can help with?"

### 4.6 Document

- Tag the ticket with the **issue category**, **root cause** (restaurant, partner, customer, CraveCart tech, external) and **resolution**.
- Add an internal note for anything unusual.
- Tickets are closed automatically 24 hours after the last agent reply if the customer doesn't respond. A CSAT survey is sent on closure.

## 5. Refund authority limits

| Role | Refund limit per order without approval | Goodwill credit limit |
|---|---|---|
| Crave Assist | ₹300 (clear-cut cases only) | ₹0 |
| L1 agent | ₹500 | ₹100 CraveCart Money |
| L1 senior agent | ₹1,000 | ₹200 |
| L2 specialist | ₹2,000 | ₹300 |
| Team lead | ₹5,000 | ₹500 |
| CX duty manager | Above ₹5,000; medical reimbursements | Case by case |

- An agent who reaches their limit raises an approval request in the Agent Console. The approver must respond within 15 minutes for P2 and 2 hours for P3.
- Goodwill credits are promotional CraveCart Money (non-withdrawable, 30-day expiry).

## 6. Handling common scenarios

### 6.1 Order is late

1. Check the live ETA and the reason (kitchen delay, no partner, traffic).
2. Give an honest update with a specific time: "The restaurant is finishing your biryani. Our partner is already waiting there. Expected arrival is 8:52 pm."
3. If the order is more than 30 minutes past the promised time, tell the customer about **free cancellation**.
4. Plus members: confirm the On-Time Promise credit will be applied automatically if they are eligible.
5. Do not blame the delivery partner or the restaurant by name.

### 6.2 Delivery partner can't find the address

1. Check the pin location against the typed address.
2. Call the customer through the masked bridge, or chat to get landmarks.
3. Share the corrected directions with the partner through the partner chat.
4. If the pin was wrong because of the customer, explain politely. The order is still delivered, and no fee is charged if it is completed.

### 6.3 Missing or wrong item

1. Ask for a photo of the bill and items if the claim is over ₹300 or the account has 2 or more claims in 30 days.
2. Offer a replacement ("Send the missing item") if eligible, otherwise a refund.
3. Tag the root cause as Restaurant. A strike is applied to the restaurant automatically.

### 6.4 "Marked delivered but not received"

1. Check the GPS trail: did the partner reach within 100 m of the pin?
2. Check the delivery PIN or delivery photo.
3. Contact the partner through Fleet Ops chat to ask who received it.
4. Ask the customer to check with family, neighbours and security.
5. If the evidence doesn't show successful delivery, give a **full refund**. If the evidence shows delivery (PIN entered, or a photo at the customer's door), escalate to L2 Trust & Safety. Do not refuse on the call; say it is under review with a 24-hour update.

### 6.5 Food safety complaint (foreign object, illness, tampered seal)

1. Treat as **P1**. Express concern first: "I'm really sorry. Your safety matters most to us."
2. Ask for a photo. Ask the customer to keep the remaining food and packaging if possible.
3. Issue a **full refund** immediately (no approval needed for food safety).
4. Raise a Food Safety ticket. The Food Safety team contacts the customer within 24 hours.
5. If the customer reports serious illness, advise seeking medical care (and **112** in an emergency). Collect contact details for the Food Safety team.

### 6.6 Safety incident or harassment

1. **P1.** Move it to the Trust & Safety queue immediately. Don't investigate yourself.
2. If the customer is in danger, tell them to call **112**.
3. Never share the partner's personal details with the customer, or the other way round.
4. Trust & Safety may deactivate the partner pending investigation, and contacts the customer within 30 minutes.

### 6.7 Payment debited but no order

1. Ask for the UPI transaction ID or the bank reference.
2. Check the payment gateway status in the Agent Console:
   - **Captured with no order:** refund immediately to source.
   - **Pending or failed:** tell the customer the bank will reverse it automatically within 5–7 business days, and give them the reference.
3. If not reversed after 7 business days, escalate to L2 Payments.

### 6.8 Coupon not applied or didn't work

1. Check the coupon's terms: minimum order, eligible restaurants, payment method and validity.
2. If the coupon should have applied but didn't because of a bug, credit the difference as CraveCart Money (within the agent's limit) and log a tech bug. See `support/technical-support-procedures.md`.
3. If the customer didn't meet the terms, explain which condition wasn't met.

### 6.9 Account suspended or refund restricted

- L1 agents cannot lift restrictions. Explain that the account is under review, give the 48-hour timeline, and escalate to L2 Account Security.
- Do not disclose the fraud signals used.

## 7. Communication guidelines

- **Tone:** warm, clear and human. Use the customer's name. Apologise once and sincerely, then focus on fixing the problem.
- **Avoid:** jargon ("the order is in the dispatch queue"), blaming ("the rider made a mistake"), and vague promises ("it'll come soon").
- **Prefer:** specific times and amounts ("₹150 is being refunded to your UPI account; you'll see it within 1–3 business days").
- **Saved replies:** agents use approved saved replies but must personalise them. Sending a saved reply unchanged twice in a row is flagged by QA.

**Example: good versus poor**

- Poor: "Sorry for the inconvenience. Your issue has been noted. We will look into it."
- Good: "I'm sorry your Mutton Korma was missing, Priya. I've refunded ₹283.50 to your UPI account. You'll see it in 1–3 business days. I've also flagged it to the restaurant so it doesn't happen again."

## 8. Difficult conversations

- **Abusive customers:** give one warning: "I want to help you, but I need us to keep this conversation respectful." If the abuse continues, the agent may end the chat with the approved closing message and tag it "Abusive". Repeated abuse is reviewed by Trust & Safety.
- **Threats to post on social media:** resolve by policy, the same as for any customer. Never offer extra compensation because of a threat.
- **Requests to speak to a manager:** a team lead takes over within 10 minutes during business hours, or a callback is scheduled within 4 hours otherwise.
- **Legal threats or notices:** don't comment on liability. Tag the ticket "Legal" and escalate to L3 Legal.

## 9. Quality assurance

- 5% of tickets per agent are reviewed each week against a 20-point QA scorecard: accuracy, policy adherence, tone, documentation and security.
- Targets: QA score of 90% or higher, CSAT of 4.3/5 or higher, first-contact resolution of 80% or higher.
- **Critical errors** (automatic QA failure): asking for an OTP or card details, sharing personal data with the wrong party, giving a refund outside policy without approval, or closing a P1 without escalating it.

## 10. Grievance redressal (Consumer Protection (E-Commerce) Rules, 2020)

- **Grievance Officer:** Neha Kulkarni, `grievance@cravecart.example`.
- Every grievance is acknowledged within **48 hours** and resolved within **one month** of receipt.
- The officer's name and contact are listed in the app (Help > Legal > Grievance Officer) and on the website.
- Customers who are still unsatisfied can approach the National Consumer Helpline or the relevant consumer commission.

## 11. Shift operations (internal)

- Support runs in three shifts: 7 am–3 pm, 3 pm–11 pm and 11 pm–7 am.
- Peak staffing is from 7 pm to 11 pm and during known events (rain alerts, festivals, cricket matches). Workforce Management publishes rosters 2 weeks ahead.
- At shift handover, open P1 and P2 tickets are handed over **verbally** to the next shift lead, not only through ticket notes.
- **Rain mode:** when 3 or more cities issue rain alerts, CX switches to rain mode. Proactive delay messages are sent, goodwill limits rise by 50% for 24 hours, and email agents move to chat.
