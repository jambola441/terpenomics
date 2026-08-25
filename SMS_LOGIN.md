# SMS Login

Phone-number login for terpenomics, using the Supabase Auth we already have. No
new backend code, no new dependency, and **no A2P 10DLC brand/campaign
registration** — so you can be sending real codes the same day.

## Why this route

US carriers block 100% of unregistered application-to-person traffic on ordinary
long codes; since Feb 2025 there is no grey area. Registering a brand + campaign
through The Campaign Registry (or getting a short code) is the multi-week process
you want to avoid.

The exemption: **OTP-only verification services that send from the provider's own
pre-registered sender pool.** Twilio Verify is the one that plugs straight into
Supabase — Twilio's docs state that with Verify "you do not need to worry about
A2P registration (Brand or Campaign) or any other aspect of sender
provisioning." You never own or provision a number.

Alternatives with the same shape, if Twilio pricing stops working: Vonage Verify,
Sinch Verify, MessageCentral VerifyNow. All are drop-in at the "OTP as a service"
layer; only Twilio and Twilio Verify are first-class Supabase providers today.

The thing to *not* do is buy a Twilio number and use Programmable Messaging —
that's the path that needs 10DLC.

## Setup (~20 minutes, mostly waiting on Twilio signup)

1. **Twilio account.** Sign up at twilio.com. Trial accounts can send to numbers
   you've verified on the console; upgrade (add a card) to text anyone.
2. **Create a Verify service.** Console → Verify → Services → Create. Name it —
   the name shows up in the message body ("Your Terpenomics code is 123456"). Copy
   the **Verify Service SID** (starts `VA`).
3. Copy your **Account SID** (`AC…`) and **Auth Token** from the Twilio console
   home.
4. **Supabase dashboard** → Authentication → Sign In / Providers → **Phone**:
   - Enable phone provider
   - SMS provider: **Twilio Verify**
   - Paste Account SID, Auth Token, Verify Service SID
   - Leave "Enable phone confirmations" on
5. **Rate limits** (Authentication → Rate Limits): lower the SMS limit to
   something sane for the MVP. Every send costs money and toll fraud is real.
6. **Turn on CAPTCHA** (Authentication → Attack Protection) before the login page
   is publicly reachable.

That's it. Nothing to deploy.

## What's in the code

- `ui/my-app/src/Login.jsx` — one login page, tabbed between **Text message**
  (default) and **Email**. SMS path calls `signInWithOtp({ phone })` then
  `verifyOtp({ phone, token, type: 'sms' })`. Includes a 60s resend cooldown
  matching Supabase's per-recipient window, and `autocomplete="one-time-code"` so
  iOS/Android offer the code from the notification.
- `ui/my-app/src/utils/phone.ts` — E.164 normalization. Supabase and Twilio only
  accept `+15551234567`; users type `(555) 123-4567`. Default country code comes
  from `VITE_DEFAULT_COUNTRY_CODE`.
- **Backend: unchanged.** `auth.py` already verifies Supabase RS256 JWTs via JWKS
  and reads the `phone` claim, and `/me/link-customer` already falls back to
  `user.phone` when linking a `Customer` row. A phone-issued JWT works everywhere
  an email-issued one does.

## Routing after sign-in

Admins carry `role="admin"` on the JWT (see `routes/admin/auth.py`) and land on
`/admin`. Anyone else signing in by text lands on `/portal`; email sign-in still
goes to `/admin`, preserving the previous behaviour. `CustomerPortal` already
calls `/me/link-customer` on mount, so the `Customer` row gets created/linked on
first portal visit — no extra call from the login page.

## Costs and caveats

- Twilio Verify bills per verification attempt plus carrier fees — budget roughly
  $0.05 per verification in the US; a plain 10DLC OTP segment is ~$0.013–0.018,
  so you are paying a premium to skip registration. At MVP volume that premium is
  a rounding error; at 100k logins/month, revisit and register 10DLC properly.
- Phone numbers get recycled. A number that once belonged to customer A can be
  reassigned to customer B, who then inherits the account. Worth an email or ID
  step before anything sensitive is exposed.
- The `Customer.phone` column is a free-text unique field. Existing rows were
  entered by hand and are probably *not* E.164, so `link-customer` matching
  against a JWT phone claim can miss and create a duplicate customer. Backfilling
  those to E.164 is the natural follow-up.
- International: `toE164` handles a `+`-prefixed number from any country and
  bare national numbers for the configured default. It is deliberately not a full
  libphonenumber; if you go multi-country, swap it for `libphonenumber-js`.

## Sources

- [Twilio Verify vs A2P 10DLC registration](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc)
- [Twilio A2P 10DLC quickstart](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/quickstart)
- [Supabase Phone Login](https://supabase.com/docs/guides/auth/phone-login)
- [Supabase Twilio provider setup](https://supabase.com/docs/guides/auth/phone-login/twilio)
- [OTP delivery without 10DLC registration (shared sender pools)](https://www.messagecentral.com/product/verify-now/overview/usa)
