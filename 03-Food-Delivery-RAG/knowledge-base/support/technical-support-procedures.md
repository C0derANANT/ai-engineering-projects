# Technical Support Procedures

_Last updated: 15 November 2026 · Owner: Customer Experience (Tech Support pod) and Platform Engineering · Audience: support agents, L2 Tech Support and on-call engineers_

This document covers app and website problems customers face, the error codes they may see, troubleshooting steps, and how technical issues are escalated and managed internally.

## 1. Supported platforms

| Platform | Minimum supported version | Notes |
|---|---|---|
| Android app | Android 9.0 (Pie) | App version 12.0 or later required to place orders |
| iOS app | iOS 15 | App version 12.0 or later required to place orders |
| Website | Latest two versions of Chrome, Safari, Firefox and Edge | Mobile browsers supported; some features (Group Cart, live map) work best in the app |

Older app versions show a **"Please update CraveCart"** screen and can only view past orders. Forced updates are used only for security or payment fixes. Customers get 7 days' notice through an in-app banner.

## 2. Error code reference

Error codes appear in small text under the error message, for example "Something went wrong (CC-PAY-302)". Ask customers for the code: it identifies the problem quickly.

| Code | Meaning | What the customer should do | Agent action |
|---|---|---|---|
| `CC-AUTH-101` | Login OTP expired (OTPs are valid for 5 minutes) | Tap "Resend OTP" | None |
| `CC-AUTH-102` | Too many wrong OTP attempts (5); login locked for 30 minutes | Wait 30 minutes and try again | Can't unlock early. If an account takeover is suspected, escalate to L2 Account Security |
| `CC-AUTH-103` | OTP not delivered (SMS gateway or DND issue) | Wait 30 seconds, resend (maximum 3 per 15 minutes), or choose "Get OTP on call" | If widespread, check the status page and raise an incident |
| `CC-AUTH-104` | Account suspended or under review | Contact support | Check the account flags; escalate to L2 Account Security |
| `CC-LOC-201` | Address not serviceable | Try a nearby address or check later | Confirm on the serviceability map; pauses are shown in the Agent Console |
| `CC-LOC-202` | Location permission denied or GPS off | Allow location in phone settings, or type the address manually | Guide them through the permission settings for their OS |
| `CC-LOC-203` | Location detected far from the saved address | Confirm the address on the map before ordering | None. This is a warning, not a block |
| `CC-CART-401` | Restaurant closed or item unavailable | Remove the item or choose another restaurant | None |
| `CC-CART-402` | Coupon not applicable | Check the coupon terms (minimum order, restaurant, payment method) | Verify the terms; if it's a bug, compensate and log it (section 6) |
| `CC-CART-403` | Cart limit exceeded (more than 20 units of an item, or more than ₹15,000) | Reduce the quantity or use CraveCart for Business | None |
| `CC-PAY-301` | Payment declined by the bank or card issuer | Use another method or contact the bank | None. CraveCart can't see the bank's reason |
| `CC-PAY-302` | Payment pending or timed out | Wait up to 15 minutes. Don't pay again straight away | Check the gateway status; if captured with no order, refund |
| `CC-PAY-303` | UPI collect request expired (5 minutes) | Retry and approve in the UPI app within 5 minutes | None |
| `CC-PAY-304` | COD not available for this order or account | Pay online | Explain the reason (limit, scheduled order, or COD disabled) |
| `CC-PAY-305` | CraveCart Money balance insufficient or wallet limit reached | Add another payment method | None |
| `CC-ORD-501` | Order placement failed (server error) | Retry after 1 minute. Check whether an order was created before paying again | Check for a duplicate charge; log it if repeated |
| `CC-ORD-502` | Duplicate order detected (same cart within 2 minutes) | Confirm if you really want two orders | None |
| `CC-NET-601` | No internet connection or request timed out | Check the connection, switch between Wi-Fi and mobile data | None |
| `CC-APP-701` | App version not supported | Update the app from the Play Store or App Store | None |

## 3. Troubleshooting guides

### 3.1 App crashes or freezes

1. Make sure the app is up to date.
2. Force close and reopen the app.
3. Restart the phone.
4. **Android:** Settings > Apps > CraveCart > Storage > **Clear cache** (not "Clear data", which logs the customer out).
   **iOS:** offload and reinstall the app (Settings > General > iPhone Storage > CraveCart > Offload App).
5. Check free storage. The app needs at least 300 MB free.
6. If it still crashes, collect: phone model, OS version, app version (Profile > About), the screen where it crashes, and the time. Raise a **Tech Bug** ticket (section 6).

### 3.2 OTP not received

1. Check the mobile number shown on the OTP screen.
2. Wait 30 seconds, then tap **Resend**. A maximum of 3 resends is allowed in 15 minutes.
3. Try **"Get OTP on call"**.
4. Check for SMS-blocking apps or DND settings. Transactional OTPs usually bypass DND, but some phones filter them into spam or promotions folders.
5. For international roaming, SMS may be delayed. Use OTP on call.
6. If many customers report this at the same time, check the **status page** and raise an incident (section 7).

### 3.3 Location is wrong

1. Turn on precise location (Android: "Use precise location"; iOS: "Precise Location" on).
2. Turn Wi-Fi on. It improves accuracy even if not connected.
3. Edit the saved address and **drag the pin** to the correct entrance.
4. Delete and re-add saved addresses that are old or inaccurate.

### 3.4 Payment problems

- **Debited but order not placed:** see `support/customer-support-procedures.md`, section 6.7. Customers should not retry many times. Each attempt may put a temporary hold on funds.
- **UPI app doesn't open:** check that a UPI app is installed and set as default. Try entering the UPI ID manually.
- **Card OTP page doesn't load:** turn off VPN, ad blockers or data-saver mode. Try another network.
- **Saved card missing:** card tokens expire when the card is reissued, and some banks remove tokens. Add the card again.

### 3.5 Live map not updating

1. Pull down to refresh the tracking screen.
2. Check the customer's internet connection.
3. Check partner location freshness in the Agent Console. If the last ping is older than 5 minutes, the problem is on the partner's side (network or GPS). Contact the partner through Fleet Ops chat.

### 3.6 Notifications not arriving

1. Check that phone notifications are on for CraveCart (system settings).
2. In the app: Profile > Settings > Notifications > "Order updates" on.
3. Turn off battery optimisation for CraveCart (Android).
4. Log out and back in. This refreshes the push token.

### 3.7 Coupon not showing or applying

1. Check eligibility: new-user coupons only on the first 3 orders, bank offers only with the named card or UPI handle, restaurant coupons only at that restaurant.
2. Check the minimum order value. It applies to the item total before fees and taxes.
3. Check whether the coupon has a per-user limit that has already been used.
4. If all conditions are met and the coupon still fails, it may be a bug. Log it (section 6) and compensate within the agent's limit.

### 3.8 Account deletion and data requests

- Customers can delete their account in Profile > Settings > Privacy > **Delete account**.
- There is a **30-day grace period**. Logging in during this period cancels the deletion.
- Before deleting, CraveCart Money refund balances must be withdrawn. Promotional balances are forfeited.
- Order records needed for tax and legal reasons are kept for 8 years in anonymised form, as required by law.
- **Data export:** Profile > Settings > Privacy > "Download my data". A link is emailed within 72 hours and is valid for 7 days.
- Requests under the Digital Personal Data Protection Act, 2023 (access, correction, erasure, grievance) can also be sent to `privacy@cravecart.example`. They are acknowledged within 72 hours.

## 4. Information to collect for any technical issue

Agents must capture all of these before escalating:

1. Customer ID or registered mobile number (last 4 digits only in notes)
2. Order ID, if related
3. Platform and version: Android, iOS or web; OS version; app version
4. Device model
5. Network type: Wi-Fi or mobile data, and operator
6. Exact error message and **error code**
7. Time of the problem (IST) and whether it is repeatable
8. Steps to reproduce
9. Screenshot or screen recording, if the customer can share one safely (make sure no OTPs or card details are visible)

## 5. Workarounds catalogue (current known issues)

| Known issue ID | Description | Affected | Workaround | Status |
|---|---|---|---|---|
| KI-2026-041 | Group Cart link opens the home page on some Android 9 devices | Android 9, app 12.4 | Open the link in a browser, then tap "Open in app" | Fix in app 12.6 |
| KI-2026-047 | Apple Pay sheet doesn't appear for some cards | iOS website (Safari) | Use UPI or card entry | Investigating |
| KI-2026-052 | Invoice download shows a blank PDF for orders with more than 25 items | All | Agent emails the invoice from the Agent Console | Fix scheduled for 2 December 2026 |

The catalogue is maintained by L2 Tech Support and reviewed every Monday.

## 6. Logging a tech bug

1. In the Agent Console, click **Raise Tech Bug** on the ticket.
2. Choose a component: Login, Location, Search, Cart, Payments, Tracking, Notifications, Plus, Wallet, Website, or Other.
3. Fill in the details from section 4.
4. Choose an impact:
   - **Single user:** goes to the L2 Tech Support queue, reviewed within 1 business day.
   - **Multiple users (5 or more reports in 30 minutes):** L2 Tech Support checks within 30 minutes and may raise an incident.
5. Link duplicate customer tickets to the same bug so the impact is counted correctly.
6. Tell the customer: "I've reported this to our technical team. Here's what you can do in the meantime: …" Never promise a fix date unless one is published in the known-issues catalogue.

## 7. Incident management (internal)

### 7.1 Severity levels

| Severity | Definition | Examples | Response |
|---|---|---|---|
| **SEV1** | Ordering or payments down, or a security breach, in multiple cities | App can't place orders; payment gateway outage; data exposure | On-call paged immediately; incident commander within 5 minutes; status page updated within 15 minutes; updates every 30 minutes |
| **SEV2** | Major feature broken, or one city badly affected | Live tracking down; OTP failures for one telecom operator; Delhi NCR dispatch failure | On-call paged; acknowledged within 15 minutes; updates every hour |
| **SEV3** | Partial degradation, with a workaround | Coupons failing for one bank; slow search | Ticket to the owning team; fix within 2 business days |
| **SEV4** | Cosmetic or low impact | Typo, icon misaligned | Backlog |

### 7.2 Incident roles

- **Incident Commander (IC):** coordinates the response and decides on rollbacks.
- **Communications Lead:** updates the status page, the CX team and leadership.
- **CX Liaison:** sends saved replies to agents, enables bulk compensation, and tracks ticket volume.
- **Subject-matter engineers:** investigate and fix.

### 7.3 Customer impact handling during incidents

- The CX Liaison publishes an **incident saved reply** within 15 minutes of a SEV1 or SEV2.
- For order-blocking SEV1 incidents longer than 30 minutes, CX leadership can approve **bulk goodwill credits** for affected customers.
- Orders that failed because of an incident are refunded automatically through a bulk job, run within 24 hours of resolution.

### 7.4 After the incident

- A **blameless postmortem** within 5 business days for every SEV1 and SEV2, covering the timeline, root cause, customer impact (orders affected, refunds issued), what went well, and action items with owners and dates.
- Action items are tracked weekly by the Platform Reliability team.

## 8. Security-related technical issues

- **Suspected account takeover** (unknown orders, changed phone number or email, unknown device logins): P1. Escalate to L2 Account Security, which can log out all sessions, freeze the wallet and restore the account within 24 hours.
- **Phishing reports** (fake CraveCart sites, SMS, calls asking for OTPs): collect the URL, number or screenshot and forward it to `security@cravecart.example`. Reassure the customer that CraveCart never asks for OTPs.
- **Vulnerability reports from researchers:** direct them to the responsible disclosure programme at `security@cravecart.example`. Agents must not discuss technical details.
