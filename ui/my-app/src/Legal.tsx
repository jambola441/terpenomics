/* ============================================================================
   Legal — the Terms of Service (/terms) and Privacy Policy (/privacy).

   Sign-up links here (TERMS_URL / PRIVACY_URL on the API, served to both
   apps by GET /me). The version customers accept is TERMS_VERSION in
   services/consent.py: change either document materially and bump it there,
   and everyone is asked to accept again on their next visit. Keep EFFECTIVE
   below equal to it.

   The privacy policy describes what the code actually does. When a feature
   starts collecting something new or sending data to a new service, this page
   has to change with it.
   ========================================================================== */

import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { t, font } from './theme'

const EFFECTIVE = 'October 5, 2026'
const CONTACT = 'jambola441@gmail.com'

export function TermsPage() {
  return (
    <Page title="Terms of Service">
      <P>
        These terms govern your use of Terpenomics (the website, the customer portal and the
        mobile app, together the “Service”). By creating an account or using the Service you
        agree to them. If you do not agree, do not use the Service.
      </P>

      <H>1. Who can use Terpenomics</H>
      <P>
        You must be 21 or older. Reserving products is only available while you are in New
        York State. You must give accurate information when you sign up and keep your phone
        number current. One account per person; accounts are not transferable.
      </P>

      <H>2. What Terpenomics is, and is not</H>
      <P>
        Terpenomics shows menus from licensed New York dispensaries and lets you reserve
        products for pickup. We are not a dispensary and do not sell, hold or deliver
        cannabis. Every sale is made by the dispensary, in the store, under its own policies
        and New York law.
      </P>
      <UL>
        <li>
          <b>Reservations are not purchases.</b> Nothing is charged through the Service. You pay
          the dispensary at pickup. The total shown when you reserve is an estimate based on the
          menu at that time; the store's price at the counter applies.
        </li>
        <li>
          <b>The dispensary checks ID.</b> You must show valid government-issued ID at pickup.
          The store may refuse or cancel any reservation, including if it cannot verify your
          age or if a product is no longer available.
        </li>
        <li>
          <b>Product information may be wrong.</b> Menus, prices, stock, and terpene and
          cannabinoid figures come from dispensaries, brands and lab reports, and can be
          incomplete, out of date or mis-parsed. Check the package and ask the store.
        </li>
        <li>
          <b>Not medical advice.</b> Nothing in the Service is medical advice or a claim that a
          product treats any condition.
        </li>
      </UL>

      <H>3. Points</H>
      <P>
        You can earn Terpee points for eligible purchases at participating partner stores,
        matched automatically by phone number or from receipts you upload. Points have no cash
        value, cannot be sold or transferred, and are not property. Points become spendable
        after a short pending period so refunds can be accounted for; refunds and returns
        reverse the points they earned. We may correct points awarded in error and may change
        or end the points program, with notice in the Service. Points are forfeited if your
        account is deleted or closed for misuse.
      </P>

      <H>4. Receipts and other things you submit</H>
      <P>
        You may only upload receipts for purchases you made. Uploading someone else's
        receipt, an altered receipt or the same receipt twice is misuse. You give us permission
        to store and process what you submit to run the Service, including reading receipts
        automatically.
      </P>

      <H>5. Text messages</H>
      <P>
        Signing in sends a one-time code to your phone by text message. If you separately opt
        in to marketing texts, we will send deals and updates from Terpenomics, up to 4
        messages a month. Message and data rates may apply. Reply STOP to stop marketing texts
        and HELP for help. Opting in is never required to use the Service. Carriers are not
        liable for delayed or undelivered messages.
      </P>

      <H>6. Acceptable use</H>
      <P>
        Do not misuse the Service: no resale of reservations, no fake accounts, no automated
        access or scraping, no attempts to get around age or location checks, and nothing that
        breaks the law or interferes with the Service or its stores. We may suspend or close
        accounts that do.
      </P>

      <H>7. Ending your account</H>
      <P>
        You can delete your account at any time from your profile. See the{' '}
        <Link to="/privacy" style={{ color: t.accent }}>Privacy Policy</Link> for what deletion
        removes and what we keep. We may suspend or close an account that breaks these terms.
      </P>

      <H>8. Disclaimers and limits</H>
      <P>
        The Service is provided “as is” and “as available”, without warranties of any kind, to
        the fullest extent the law allows. We are not responsible for products sold by
        dispensaries or partner stores, for their prices, availability or conduct, or for
        decisions you make based on information in the Service. To the fullest extent the law
        allows, Terpenomics is not liable for indirect, incidental or consequential damages,
        and its total liability for any claim relating to the Service is limited to $100.
      </P>

      <H>9. Changes</H>
      <P>
        We may update these terms. If a change is material we will ask you to accept the new
        version in the app before you can keep reserving products.
      </P>

      <H>10. Law</H>
      <P>
        These terms are governed by the laws of the State of New York, without regard to its
        conflict-of-laws rules. Disputes will be heard in the state or federal courts located in
        New York County, New York.
      </P>

      <H>11. Contact</H>
      <P>Questions about these terms: <Mail /></P>
    </Page>
  )
}

export function PrivacyPage() {
  return (
    <Page title="Privacy Policy">
      <P>
        This policy explains what Terpenomics collects, why, who it is shared with, and the
        choices you have. It covers the website, the customer portal and the mobile app.
      </P>

      <H>What we collect</H>
      <UL>
        <li><b>Account details:</b> your phone number, first name and, if you give it, your last name.</li>
        <li>
          <b>Sign-up confirmations:</b> that you confirmed you are 21 or older, which version of
          the terms you accepted, and whether you opted in to marketing texts. For each we keep
          the wording you were shown, the time, and the IP address and device/browser type it
          came from, as a record of what you agreed to.
        </li>
        <li><b>Reservations:</b> the store, products, quantities and quoted totals, and their status.</li>
        <li>
          <b>Points activity:</b> purchases at partner stores that are matched to you, including
          the order totals and items the store's point-of-sale system reports, and receipt
          photos you upload along with what is read from them.
        </li>
        <li><b>Preferences:</b> the stores you follow and feedback you give on products.</li>
        <li>
          <b>Location:</b> when you reserve in the mobile app, your device's location is checked
          on the device to confirm you are in New York. It is not sent to us or stored.
        </li>
        <li>
          <b>Technical data:</b> IP address and request logs kept by our hosting provider, used
          for security and to limit abuse of sign-in.
        </li>
      </UL>
      <P>We do not ask for your date of birth, government ID or payment details.</P>

      <H>How we use it</H>
      <UL>
        <li>To sign you in and keep your account secure.</li>
        <li>To pass your reservation to the store you chose, which sees your name, phone number and order.</li>
        <li>To match partner-store purchases and receipts to you and award points.</li>
        <li>To build your home feed from the stores you follow.</li>
        <li>To send marketing texts, only if you opted in.</li>
        <li>To prevent fraud and abuse, and to meet legal obligations.</li>
      </UL>

      <H>Who we share it with</H>
      <P>We do not sell your personal information. We share it only as needed to run the Service:</P>
      <UL>
        <li><b>Dispensaries</b> you reserve with: your name, phone number and reservation.</li>
        <li>
          <b>Partner stores</b> where you earn points: we receive purchase data from their
          point-of-sale provider (such as Square), matched to you by phone number.
        </li>
        <li>
          <b>Service providers</b> that process data on our behalf: Supabase (accounts and
          database), Render (hosting), Message Central (sign-in text messages), Anthropic
          (reading uploaded receipts) and our map tile provider (map images, which receives
          your IP address when the map loads).
        </li>
        <li><b>Legal requirements:</b> when required by law or to protect rights and safety.</li>
      </UL>

      <H>How long we keep it</H>
      <P>
        We keep your account information while your account is open. Contact details on
        partner-store purchases that never match an account are deleted after a short claim
        window.
      </P>

      <H>Deleting your account</H>
      <P>You can delete your account from your profile in the app or portal. When you do:</P>
      <UL>
        <li>Your sign-in is deleted and you are signed out everywhere.</li>
        <li>Your name, phone number and email are erased from your account record.</li>
        <li>Receipt photos and notes are erased, and open reservations are cancelled.</li>
        <li>Links between you and partner-store purchases are removed, so new purchases can no longer be matched to you.</li>
        <li>Unspent points are forfeited.</li>
      </UL>
      <P>
        We keep records of past reservations, purchases and points that no longer identify you,
        because stores and our books depend on them. We also keep the records of what you agreed
        to, including any opt-out from marketing texts, as proof of consent and so a number is
        never texted on old consent.
      </P>

      <H>Your choices</H>
      <UL>
        <li>Turn marketing texts on or off in your profile, or reply STOP to any marketing text.</li>
        <li>Edit your name in your profile. To change your phone number, contact us.</li>
        <li>Ask us for a copy of your information, or to correct it, at <Mail />.</li>
      </UL>

      <H>Security</H>
      <P>
        Data is encrypted in transit. Sign-in codes are generated and checked by our text
        message provider and never stored by us. Access to the database is limited to the
        Service and its administrators. No system is perfectly secure; tell us at <Mail /> if
        you find a problem.
      </P>

      <H>Adults only</H>
      <P>
        The Service is for people 21 and older. We do not knowingly collect information from
        anyone younger. If you believe someone under 21 has an account, contact us and we will
        delete it.
      </P>

      <H>Changes</H>
      <P>
        We will update this policy when what we collect or how we use it changes. If a change is
        material we will ask you to review it in the app.
      </P>

      <H>Contact</H>
      <P>Privacy questions and requests: <Mail /></P>
    </Page>
  )
}

function Page({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div style={{ minHeight: '100dvh', background: t.bg, padding: '40px 16px 64px', boxSizing: 'border-box' }}>
      <article style={{ maxWidth: 680, margin: '0 auto', color: t.text2, fontSize: font.size.body, lineHeight: 1.65 }}>
        <Link to="/" style={{ color: t.accent, fontWeight: font.weight.heavy, fontSize: font.size.heading, textDecoration: 'none' }}>
          terpenomics
        </Link>
        <h1 style={{ color: t.text1, fontSize: 30, fontWeight: font.weight.heavy, margin: '24px 0 4px', letterSpacing: '-0.01em' }}>
          {title}
        </h1>
        <div style={{ color: t.text3, fontSize: font.size.small, marginBottom: 24 }}>Effective {EFFECTIVE}</div>
        {children}
        <div style={{ marginTop: 40, color: t.text3, fontSize: font.size.small, display: 'flex', gap: 16 }}>
          <Link to="/terms" style={{ color: t.text3 }}>Terms of Service</Link>
          <Link to="/privacy" style={{ color: t.text3 }}>Privacy Policy</Link>
        </div>
      </article>
    </div>
  )
}

function H({ children }: { children: ReactNode }) {
  return <h2 style={{ color: t.text1, fontSize: font.size.heading, fontWeight: font.weight.bold, margin: '28px 0 8px' }}>{children}</h2>
}

function P({ children }: { children: ReactNode }) {
  return <p style={{ margin: '0 0 12px' }}>{children}</p>
}

function UL({ children }: { children: ReactNode }) {
  return <ul style={{ margin: '0 0 12px', paddingLeft: 20, display: 'flex', flexDirection: 'column', gap: 6 }}>{children}</ul>
}

function Mail() {
  return <a href={`mailto:${CONTACT}`} style={{ color: t.accent }}>{CONTACT}</a>
}
