# SMS Login

Phone-number login for terpenomics, using the Supabase Auth we already have. No
new backend code and no new dependency. Read "The two hurdles" and "The cannabis
problem" below before committing to a provider — the shipped code targets Twilio
Verify, which skips A2P 10DLC registration but not Twilio's own identity check,
and Twilio's policy on cannabis traffic is a live risk for this product.

## The two hurdles, which are not the same thing

There are two separate gates on US SMS, and it is easy to conflate them:

1. **A2P 10DLC brand + campaign registration** — the multi-week one, run through
   The Campaign Registry. Carriers block 100% of unregistered long-code traffic.
2. **Account-level KYC at your provider** — the aggregator confirming who you are.

Twilio Verify clears **(1)** and only (1). Verify sends from Twilio's own
pre-registered sender pool, and Twilio's docs are explicit that with Verify "you
do not need to worry about A2P registration (Brand or Campaign) or any other
aspect of sender provisioning."

It does **not** clear (2). A Trust Hub primary compliance profile — government ID
photo plus selfie verification, approved in about two days — is now part of
standard new-account setup. Sole proprietors can file an *individual* profile
rather than a business one, but it is still an ID check. Budget a day or two, not
weeks, and not zero.

Providers like Message Central's VerifyNow advertise no-paperwork signup with
free trial credits. That removes gate (2) as well, at an integration cost
described below.

## The cannabis problem

This matters more than the KYC question for a dispensary product.

Twilio's messaging policy forbids cannabis and CBD traffic in the US outright,
on the grounds that federal law still prohibits sale regardless of state
legality — and Twilio states there are **no exceptions**. Their definition is
broad: "any message which relates to the marketing or sale of a cannabis product,
regardless of whether or not those messages explicitly contain cannabis terms,
images, or links to cannabis websites." Twilio has previously cut off cannabis
industry customers, and error 30940 exists specifically to reject cannabis
campaigns.

A bare login code arguably is not marketing or sale, and a Verify message body
contains only the code and the service name. But the Trust Hub profile asks what
the business does, and an account identified as cannabis is exposed to
termination — which is a far worse outcome than a two-day ID check. Treat Twilio
as a risky long-term host for this particular product, independent of KYC.

Any alternative provider needs the same question asked of it before you invest
integration time: not "do you check ID" but **"will you carry a
cannabis-adjacent sender on your US route."**

## Why VerifyNow is not a drop-in swap

Supabase's native SMS providers are MessageBird, Twilio, Twilio Verify, Vonage
and TextLocal. VerifyNow is not among them, and the generic escape hatch does not
fit either:

- **Supabase's Send SMS Hook** hands your endpoint an OTP that *Supabase*
  generated and expects you to deliver it verbatim. You cannot substitute a
  provider-generated code.
- **VerifyNow owns the code.** `/verification/v3/send` generates and delivers the
  OTP and returns a `verificationId`; `/verification/v3/validateOtp` checks it.
  There is no "send this exact string" mode on the OTP product.

Those two contracts are incompatible. Using VerifyNow means taking phone login
out of Supabase Auth's OTP path entirely: backend endpoints that call
send/validate, then finding-or-creating the Supabase user by phone via the admin
API and minting a session server-side to hand back to the client. Workable, but
it is custom auth code that a solo maintainer owns forever.

The other Supabase-native providers do not rescue this: MessageBird and Vonage
send Supabase's generated code over an ordinary long code, which puts you back on
gate (1).

## Setup for Twilio Verify (~20 minutes of work, plus ~2 days for ID approval)

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
- [Twilio Trust Hub primary compliance profiles](https://www.twilio.com/docs/trust-hub/profiles/primary-compliance-profiles)
- [Twilio: can I send cannabis or CBD messaging traffic?](https://support.twilio.com/hc/en-us/articles/1260804628349-Can-I-send-cannabis-or-CBD-related-messaging-traffic-on-Twilio)
- [Twilio error 30940 — campaign rejected, cannabis content](https://www.twilio.com/docs/api/errors/30940)
- [Supabase Send SMS Hook](https://supabase.com/docs/guides/auth/auth-hooks/send-sms-hook)
- [Message Central VerifyNow API](https://www.messagecentral.com/product/verify-now/api)
- [OTP delivery without 10DLC registration (shared sender pools)](https://www.messagecentral.com/product/verify-now/overview/usa)
