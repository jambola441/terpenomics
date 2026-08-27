# SMS Login

Phone-number login for terpenomics, built on Message Central's VerifyNow for
delivery and Supabase for the resulting session. No A2P 10DLC brand or campaign
registration, and no identity check to get started.

The sections below record why that combination, and what it costs — the choice
is less obvious than it looks, and the reasoning matters more than the wiring.

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

Those two contracts are incompatible, so phone login sits outside Supabase Auth's
OTP path: our backend calls send/validate, then finds-or-creates the Supabase
user and mints the session itself. That is what is implemented here. It is real
custom auth code that a solo maintainer owns forever — the honest price of
skipping both gates.

The other Supabase-native providers do not rescue this: MessageBird and Vonage
send Supabase's generated code over an ordinary long code, which puts you back on
gate (1).

**Before spending more on this vendor**, confirm with Message Central that they
will carry a cannabis-adjacent sender on their US route. Their signup does not
ask, which is convenient right up until an account review.

## How it works

```
browser                    our API                     VerifyNow        Supabase
   |  POST /auth/sms/start    |                            |               |
   |------------------------->| send(phone) -------------->|               |
   |<-- challenge_id ---------| (stores challenge)         |  ~~ SMS ~~>   |
   |                          |                            |               |
   |  POST /auth/sms/verify   |                            |               |
   |------------------------->| validateOtp(ref, code) --->|               |
   |                          | find/create user ---------------------->   |
   |                          | rotate password, get session ---------->   |
   |<-- access + refresh -----|                            |               |
   |  supabase.auth.setSession()                                           |
```

The provider owns the code end to end; we only ever hold a reference to it. Once
it confirms, we exchange that for an ordinary Supabase session, so every existing
route keeps verifying ordinary Supabase JWTs through JWKS — `auth.py`,
`/me/link-customer` and the admin guards are all untouched.

## Setup

1. **Sign up at Message Central** and create a VerifyNow application. Signup
   grants free trial credits; there is no ID check and nothing to wait for.
2. Copy your **customer ID** and **key** from the console. The key is the
   base-64 encoded password, not the plaintext one.
3. **Supabase service-role key**: dashboard → Project Settings → API. This grants
   full admin over your auth users — backend only, never in the browser bundle.
4. Fill in `.env` from `.env.example`: `VERIFYNOW_CUSTOMER_ID`, `VERIFYNOW_KEY`,
   `VERIFYNOW_EMAIL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`.
5. Leave the Supabase dashboard's **Phone provider switched off**. We do not use
   Supabase's own SMS, and the session exchange falls back to an email grant so
   it works either way.
6. Restart the API. `create_db_and_tables()` adds `phone_auth_challenges` and
   `phone_auth_identities` on startup.

## What's in the code

**Backend**

- `services/sms_otp.py` — the provider boundary. `SmsOtpProvider` is a two-method
  protocol (`send`, `check`); `VerifyNowProvider` implements it, caches the auth
  token and refreshes it once on a 401. Swapping vendors means a new class and a
  branch in `get_provider()`; nothing above this module changes.
- `services/supabase_admin.py` — finds or creates the user and mints the session.
  The password it exchanges is generated server-side, never returned to the
  client, and rotated on every login, so a leaked one is stale by the next
  sign-in.
- `services/phone.py` — E.164 normalization, mirroring the frontend's.
- `routes/auth_sms.py` — `POST /auth/sms/start` and `POST /auth/sms/verify`, plus
  the challenge lifecycle and rate limits.
- `models.py` — `PhoneAuthChallenge` (one outstanding code request; the code
  itself never touches our database) and `PhoneAuthIdentity` (E.164 → Supabase
  user, so repeat logins never search Supabase's user list).

**Frontend**

- `ui/my-app/src/Login.jsx` — one page, tabbed **Text message** (default) and
  **Email**. Email still uses Supabase's own OTP; SMS calls our endpoints and
  then `supabase.auth.setSession()`. Resend cooldown follows the server's
  `Retry-After` rather than a hardcoded guess, and `autocomplete="one-time-code"`
  lets phones autofill from the notification.
- `ui/my-app/src/utils/phone.ts` — E.164 normalization and as-you-type
  formatting.

## Abuse limits

Every send costs money, and an unprotected OTP endpoint is a standing invitation
to toll fraud. Defaults, all tunable from `.env`:

| Limit | Default | Env |
| --- | --- | --- |
| Resend cooldown per number | 60s | `SMS_OTP_RESEND_SECONDS` |
| Sends per number per hour | 5 | `SMS_OTP_MAX_PER_PHONE_PER_HOUR` |
| Sends per IP per hour | 20 | `SMS_OTP_MAX_PER_IP_PER_HOUR` |
| Guesses per challenge | 5 | `SMS_OTP_MAX_ATTEMPTS` |
| Challenge lifetime | 300s | `SMS_OTP_TTL_SECONDS` |

`/auth/sms/verify` returns one generic message for every failure — wrong code,
expired, unknown id, already used — so it cannot be used to probe which numbers
or challenges exist. A challenge is burned before any session is minted, so a
replayed request cannot yield a second session.

The IP limit reads `X-Forwarded-For`, which only means anything behind a trusted
proxy. It is a speed bump, not an authorization check.

## Routing after sign-in

Admins carry `role="admin"` on the JWT (see `routes/admin/auth.py`) and land on
`/admin`. Anyone else signing in by text lands on `/portal`; email sign-in still
goes to `/admin`, preserving the previous behaviour. `CustomerPortal` already
calls `/me/link-customer` on mount, so the `Customer` row gets created and linked
on first portal visit — no extra call from the login page.

## Tests

```
pytest tests/ -m "not live"
```

- `tests/test_phone.py` — normalization, including the junk it must reject.
- `tests/test_sms_otp_provider.py` — the VerifyNow wire contract (parameter
  names, `authToken` header, every `responseCode` branch, token refresh). This
  contract came from the vendor's docs, so this is where a vendor change should
  break first.
- `tests/test_sms_login_routes.py` — challenge lifecycle with the provider and
  Supabase stubbed: cooldowns, hourly caps, wrong codes, attempt lockout,
  expiry, replay, and returning users keeping one Supabase identity.

## Caveats

- **Custom auth is custom risk.** This is the part of the system where a bug
  means account takeover rather than a broken page. It has tests; it has not had
  a second pair of eyes.
- **Vendor concentration.** Message Central is a smaller vendor than Twilio, and
  a shared sender pool you do not control can be throttled or flagged by
  something another customer did. The provider boundary in `services/sms_otp.py`
  exists so that swapping is a day, not a rewrite.
- **Phone numbers get recycled.** A number that belonged to customer A can be
  reassigned to customer B, who then inherits the account. Worth a second factor
  before anything sensitive is exposed.
- **`Customer.phone` is not E.164.** Existing rows were hand-entered, so
  `/me/link-customer` matching a JWT phone claim can miss and create a duplicate
  customer. A backfill is the natural follow-up.
- **International is deliberately shallow.** `to_e164` handles `+`-prefixed
  numbers from anywhere and bare national numbers for the configured default,
  and `split_e164` knows a fixed list of country codes (`SMS_COUNTRY_CODES`). If
  you go multi-country in earnest, swap in `phonenumbers` and
  `libphonenumber-js`.

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
