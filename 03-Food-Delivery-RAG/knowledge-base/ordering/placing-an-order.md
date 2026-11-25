# How to Place an Order on CraveCart

_Last updated: 15 November 2026 · Applies to: Android app, iOS app and website · Owner: Consumer Product team_

## 1. Before you order

### 1.1 Account requirements

- You need a CraveCart account linked to an Indian mobile number verified by OTP.
- You must be 18 or older to create an account.
- One mobile number can be linked to only one CraveCart account.
- Email is optional, but you need it for invoices, Plus receipts and account recovery.

### 1.2 Setting the delivery location

1. Open the app. It asks for location permission so it can detect where you are.
2. Confirm or search for your address. **Drag the map pin to your exact building entrance.** The pin location, not the typed text, is what the delivery partner navigates to.
3. Add house or flat number, floor, building name and a landmark.
4. Save the address with a label (Home, Work, Other). You can save up to 20 addresses.

> **Tip:** most "delivery partner can't find my address" issues happen because the map pin is on the main road or in a neighbouring society. Always check the pin.

**Edge cases**

- **Address unserviceable (`CC-LOC-201`):** the address is outside every restaurant's delivery radius, or the area is temporarily paused (weather, curfew). Try a nearby serviceable address or check again later.
- **GPS denied (`CC-LOC-202`):** you can still type your address manually; live location detection won't work.
- **Gated communities and offices:** add gate number and security instructions in "Delivery instructions". Some campuses allow delivery only to the main gate.

## 2. Finding food

- **Home feed:** restaurants near you, sorted by relevance. Each card shows rating, estimated delivery time, distance and cost for two.
- **Search:** search by dish ("biryani"), cuisine ("South Indian"), or restaurant name.
- **Filters:** Pure Veg, rating 4.0+, delivery time under 30 minutes, offers, Plus partner, price range, and cuisines.
- **Veg and non-veg marking:** every item carries the green (veg) or brown/red (non-veg) symbol supplied by the restaurant. Items with egg are marked "Contains egg".
- **Allergens:** if a restaurant has provided allergen information, it appears under the item description. CraveCart cannot guarantee a dish is allergen-free. Customers with severe allergies should contact the restaurant through the "Call restaurant" option, where it is available.

## 3. Building your cart

1. Tap **Add** on an item. If it has options (size, spice level, add-ons), choose them and tap **Add item**.
2. Change quantities with + and −. The maximum is 20 units per item and an item total of ₹15,000 per order. Larger orders need CraveCart for Business or a bulk-order request.
3. A cart can contain items from **only one restaurant**. Adding an item from a different restaurant asks you to clear the current cart.
4. **Cooking instructions:** add a note for the restaurant (up to 150 characters), such as "less oil" or "no onion". The restaurant tries to follow it but it is not guaranteed. Notes asking for items not on the menu are ignored.
5. **Cutlery:** cutlery is off by default to reduce plastic waste. Turn on "Send cutlery" if you need it.

**Edge cases**

- **Item becomes unavailable while in the cart:** the app shows "Some items are no longer available" (`CC-CART-401`) and removes them. Review the cart before paying.
- **Restaurant closes while you are checking out:** the order cannot be placed. Your cart is saved for when the restaurant reopens.
- **Customisation price:** add-ons such as extra cheese are charged on top of the base item price and shown in the cart.

## 4. Checkout

On the checkout screen you can:

1. **Review the delivery address** and change it if needed.
2. **Add delivery instructions** for the delivery partner (up to 200 characters), such as "Leave at the door", "Don't ring the bell, baby sleeping" or "Call on arrival".
3. **Apply a coupon:** tap "Apply coupon" to see eligible coupons or enter a code. Only one coupon per order.
4. **See the ETA:** shown as a range, for example "30–35 min". The upper end is the **promised delivery time**, used for the Plus On-Time Promise and for free cancellation on very late orders.
5. **Add a tip** (optional).
6. **Check the bill:** tap "Bill details" to see the item total, packaging, delivery fee, platform fee, any high-demand, late-night or small cart fee, and GST. See `company/pricing-fees-and-membership.md`.
7. **Choose a payment method** and tap **Place order** (or **Pay ₹X**).

## 5. Payment methods

| Method | Notes |
|---|---|
| UPI (any UPI app, UPI intent or UPI ID) | Most common. A UPI collect request expires in 5 minutes (`CC-PAY-303`). |
| Credit and debit cards (Visa, Mastercard, RuPay, American Express) | Cards can be saved as tokens under RBI tokenisation rules; CraveCart never stores the full card number. |
| Net banking | All major Indian banks. |
| Wallets | Selected third-party wallets. |
| CraveCart Money | Can be combined with another method if the balance is not enough. |
| Pay Later | Through partner providers, subject to their eligibility checks. |
| Cash on Delivery (COD) | Available for orders up to ₹2,000. Not available for Scheduled Orders, Group Cart orders, or accounts with COD disabled (see below). |

**COD rules**

- Keep exact change where possible. Delivery partners may carry limited change.
- You can switch a COD order to online payment at any time before delivery with "Pay online now" on the tracking screen.
- COD is disabled for an account after **2 COD orders refused or unpaid at the door within 90 days**, or when the account has unpaid cancellation fees.

**Payment edge cases**

- **Payment failed but money debited (`CC-PAY-301`/`CC-PAY-302`):** if no order was created, the bank reverses the amount automatically, usually within 5 to 7 business days. If the order was created, you have not been charged twice. See `support/technical-support-procedures.md`.
- **Payment pending:** sometimes the bank confirms late. The app waits up to 15 minutes. If the payment is confirmed in that time, the order goes through. If not, the order is not placed and any debit is reversed.
- **Double charge:** if the same order was charged twice, the extra charge is refunded within 48 hours of reporting. See `policies/refund-policy.md`.

## 6. After you tap "Place order"

1. **60-second grace period:** for the first 60 seconds you can tap **Edit order** to change items, address or payment, or **Cancel** for a full refund. See `ordering/modifying-an-order.md` and `ordering/cancelling-an-order.md`.
2. **Restaurant acceptance:** the restaurant has 3 minutes to accept. If it doesn't, the order is cancelled automatically with a full refund and you are notified.
3. **Tracking:** follow the order on the tracking screen. See `ordering/order-tracking.md`.

## 7. Scheduled Orders

- Choose "Schedule for later" at checkout and pick a 15-minute delivery slot from **30 minutes to 2 days** ahead, within the restaurant's opening hours.
- Payment is taken when you place the order. COD is not available.
- The restaurant starts preparing about 40 minutes before the slot.
- Changes and cancellation are free until **60 minutes before the slot starts**. After that, standard cancellation rules apply. See `policies/cancellation-policy.md`.
- **Edge case:** if a restaurant later closes unexpectedly on the scheduled day, the order is cancelled with a full refund and you are notified at least 30 minutes before the slot where possible.

## 8. Group Cart

1. The host adds at least one item and taps **Share cart** to get a link.
2. Up to 10 people (each needs a CraveCart account) can open the link and add items under their own name.
3. The host locks the cart, reviews it and pays for the whole order. CraveCart does not split payments; participants settle with the host themselves.
4. Only the host can modify or cancel the order and contact support about it.
5. The cart link expires after 2 hours or when the order is placed.

## 9. Ordering for someone else

- Add the recipient's address and use "Receiver details" to add their name and phone number. The delivery partner then calls the recipient, not you.
- The person who placed the order remains responsible for payment, cancellation fees and support requests.
- For orders with an item total of **₹1,000 or more**, a 4-digit **delivery PIN** is sent to the account holder. Share it with the recipient so they can give it to the delivery partner.

## 10. Restrictions

- CraveCart does not deliver alcohol, tobacco, medicines or any item a restaurant is not licensed to sell.
- Orders may be blocked if fraud checks flag them, for example many high-value COD orders to new addresses within a short time.
- Orders over ₹15,000, or with more than 20 units of one item, need a bulk-order request through CraveCart for Business, placed at least 24 hours in advance.
