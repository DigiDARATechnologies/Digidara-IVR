# DigiDARA AI Voice Assistant — Landing Page Requirements

## 1. Purpose of this document

This document is the design and content brief for the DigiDARA public landing page. It can be shared directly with the designer or frontend developer responsible for creating the page.

The landing page should explain the product clearly, establish trust, and encourage prospective customers to request a demonstration. It should not expose internal architecture, credentials, customer information, or unapproved commercial claims.

## 2. Product summary

**DigiDARA** is an AI voice sales-calling platform designed primarily for education and training providers that need to contact and qualify large numbers of enquiries.

The platform can:

- Place outbound calls to real phone numbers.
- Conduct natural voice conversations in English and Tamil.
- Let the recipient choose English or Tamil at the beginning of the call.
- Run a bulk-calling campaign from a Google Sheet of leads.
- Record call outcomes and update campaign progress.
- Answer questions using an approved campaign knowledge base.
- Identify interested leads, callback requests, not-interested outcomes, and do-not-call requests.
- Store call recordings, transcripts, summaries, usage, and cost information for review.

DigiDARA is intended to handle the first stage of outbound qualification and help human counsellors focus on interested or qualified leads. It should not be presented as a replacement for the human sales team.

## 3. Current product status

DigiDARA is a working prototype with an exercised end-to-end calling flow. Live calls have been placed, recorded, billed, and analysed using the platform.

The current production call path uses:

- Plivo for telephony.
- OpenAI Realtime for live speech-to-speech conversations.
- Google Sheets for bulk lead input and campaign status updates.

This status is provided for the landing-page team’s understanding. Provider names do not need to appear prominently in public marketing copy unless approved by the product owner.

## 4. Target audience

### Primary audience

- Education and training institutes.
- Course and internship providers.
- Admissions and counselling teams.
- Teams managing leads from marketing forms, referrals, or spreadsheets.

### Possible future audience

- Small and medium-sized businesses with high-volume outbound calling needs.
- Telecalling and lead-generation teams.

The first version of the landing page should focus on education, admissions, training, and lead qualification. It should not describe DigiDARA as a general-purpose solution for every industry unless that positioning is approved later.

## 5. Landing-page objective

The primary conversion goal is to encourage a visitor to **book or request a product demo**.

Recommended calls to action:

- **Primary CTA:** Book a Demo
- **Secondary CTA:** See How It Works

If no booking system exists yet, the primary CTA can open a contact form or an approved email/contact channel.

## 6. Core value proposition

### Recommended headline

> Qualify more leads with natural AI voice conversations in English and Tamil.

### Recommended supporting copy

> DigiDARA helps education and training teams contact enquiries at scale, answer common questions, capture outcomes, and hand interested leads to human counsellors.

### Short alternative headline

> AI-powered voice calling for English and Tamil customer conversations.

All public copy should remain simple and outcome-oriented. Avoid leading with technical terms such as WebSockets, APIs, language models, or speech-to-speech architecture.

## 7. Required page structure

### 7.1 Header

Include:

- DigiDARA logo or wordmark.
- Navigation links to Features, How It Works, Use Cases, and Contact.
- A visible **Book a Demo** button.

The header may remain fixed while the visitor scrolls.

### 7.2 Hero section

Include:

- The primary headline.
- One short paragraph explaining the product.
- Primary and secondary CTA buttons.
- A product dashboard screenshot, product mockup, or voice-call illustration.

Suggested supporting labels:

- English and Tamil conversations.
- Bulk calling from Google Sheets.
- Campaign results and call insights.

Do not use a generic humanoid robot as the main visual. Prefer a real product interface, phone-call activity, conversational audio waves, or a campaign workflow illustration.

### 7.3 Problem section

Suggested heading:

> Your leads should not go cold while your team works through a spreadsheet.

Communicate these challenges:

- New enquiries need a quick first response.
- Human counsellors have limited time and calling capacity.
- Repetitive first-contact calls reduce time available for qualified prospects.
- Language preferences can affect engagement and understanding.
- Manual follow-up and status tracking can become inconsistent.

### 7.4 Solution section

Suggested heading:

> Let DigiDARA handle the first conversation.

Explain that DigiDARA contacts leads, speaks in the selected language, answers approved questions, captures the outcome, and helps the team decide what to do next.

Keep the role of human counsellors clear: DigiDARA qualifies and organizes leads; the human team handles high-value follow-up and closing.

### 7.5 How it works

Present this as a four-step workflow:

1. **Prepare the lead list** — Add customer details to the supported Google Sheet.
2. **Configure the campaign** — Provide the campaign instructions and approved course or service information.
3. **Start the calls** — DigiDARA contacts leads and conducts English or Tamil conversations.
4. **Review the outcomes** — View call status, recordings, transcripts, summaries, and follow-up information.

Avoid implying that any unimplemented third-party CRM integration is already available.

### 7.6 Key features

Use short feature cards for:

#### English and Tamil voice conversations

The recipient can select a preferred language at the beginning of the call.

#### Google Sheets bulk calling

Use an existing lead sheet to run calls sequentially and track campaign progress.

#### Approved knowledge grounding

The assistant answers campaign questions using approved information rather than inventing important details.

#### Campaign and call tracking

Review call progress, outcomes, recordings, transcripts, and summaries.

#### Lead qualification

Capture interest, callback requests, next actions, and other useful outcomes for the counselling team.

#### Do-not-call protection

Suppression checks help prevent further calls to numbers recorded as do-not-call.

### 7.7 Use cases

Recommended use cases:

- First contact for new course enquiries.
- Lead qualification before counsellor follow-up.
- Course, internship, or training-program introductions.
- Callback and follow-up identification.
- Appointment or counselling-session coordination, where supported by the campaign workflow.

Do not advertise payment collection, guaranteed appointment booking, or autonomous closing unless those capabilities are implemented and approved.

### 7.8 Product preview

Show approved, sanitized screenshots of relevant screens, such as:

- Campaign creation or campaign list.
- Google Sheet bulk-calling setup.
- Live or completed call status.
- Call history, transcript, summary, or analytics.

All screenshots must hide or replace:

- Customer names and phone numbers.
- Email addresses and other personal data.
- API keys, credentials, tokens, and internal URLs.
- Real campaign data that has not been approved for publication.

Use realistic fictional data instead of blurring large parts of the interface when possible.

### 7.9 Trust and responsible-use section

Suggested heading:

> Built for controlled, reviewable customer outreach.

Possible points:

- The assistant identifies itself as an AI voice assistant during its greeting.
- Campaign answers are based on approved information.
- Calls and outcomes can be reviewed by the operating team.
- Do-not-call requests are respected through suppression controls.

Only publish privacy, security, uptime, or compliance claims that have been reviewed and approved. Do not add certification badges unless the corresponding certification is current and verifiable.

### 7.10 Final CTA

Suggested heading:

> Ready to reach and qualify more enquiries?

Suggested copy:

> See how DigiDARA can support the first stage of your admissions or sales-calling workflow.

Button:

> Book a Demo

### 7.11 Footer

Include:

- DigiDARA name or logo.
- Contact information.
- Privacy Policy link, once available.
- Terms of Service link, once available.
- Copyright notice.
- Social links only if official profiles exist.

Do not publish placeholder legal links as if they are complete policies.

## 8. Demo/contact form requirements

Recommended fields:

- Full name.
- Work email.
- Phone number, if required for follow-up.
- Organization or institute name.
- Approximate number of leads or calls per month.
- Short message or use case.

Form requirements:

- Clearly identify required and optional fields.
- Validate inputs and show understandable error messages.
- Display a confirmation after successful submission.
- Include consent text appropriate to the intended follow-up method.
- Do not collect unnecessary sensitive information.
- Define where submissions are delivered before launching the page.

## 9. Visual and brand direction

The page should feel:

- Professional and trustworthy.
- Modern but not overly futuristic.
- Clear and easy to scan.
- Suitable for education and business decision-makers.
- Consistent across desktop, tablet, and mobile.

Recommended visual language:

- Clean SaaS-style layout.
- Strong headline typography.
- Generous spacing and short content blocks.
- Voice waveforms, call states, campaign flows, or dashboard UI.
- Subtle English and Tamil language cues.
- Accessible color contrast and visible keyboard focus states.

The final colors, fonts, and logo treatment should follow approved DigiDARA brand assets. If no brand system exists, the designer should first propose a small design system containing colors, typography, buttons, form fields, cards, spacing, and icon style.

## 10. Functional requirements

The completed page should:

- Work on current desktop and mobile browsers.
- Use responsive layouts without horizontal scrolling.
- Provide working navigation and CTA links.
- Use semantic headings and accessible form labels.
- Support keyboard navigation.
- Provide useful image alternative text.
- Avoid autoplaying audio.
- Load optimized images and avoid unnecessary large animations.
- Include page title, meta description, social sharing image, and favicon.
- Include basic analytics only after the tool and privacy requirements are approved.

## 11. Content and claims guardrails

The landing page must not include:

- Guaranteed revenue, conversion, or sales-growth claims.
- Invented accuracy, response-rate, or cost-saving percentages.
- Unapproved customer names, logos, quotes, or testimonials.
- Claims of replacing all human sales or counselling staff.
- Claims that DigiDARA supports languages other than English and Tamil today.
- Claims of integrations that are not currently implemented.
- Unverified statements such as “fully production-ready,” “enterprise-ready,” or “100% secure.”
- Provider logos without confirming that their trademark guidelines permit the intended use.

Any pricing, trial offer, customer result, security claim, or legal/compliance statement must be approved by the product owner before publication.

## 12. Assets required from the product owner

Before final design, request:

- Approved DigiDARA logo files, preferably SVG and transparent PNG.
- Brand colors and fonts, if already defined.
- Sanitized product screenshots.
- Official demo-booking or contact destination.
- Official contact email and phone number.
- Approved company/legal name.
- Privacy Policy and Terms of Service URLs, if available.
- Approved testimonials or customer logos, if available.
- Final domain name and social sharing details.

Missing assets should be marked as `TODO` in the design. They must not be invented.

## 13. Expected deliverables

The landing-page owner should provide:

1. A desktop and mobile wireframe.
2. A final high-fidelity design or implemented responsive page.
3. Reusable components for the header, buttons, feature cards, CTA, form, and footer.
4. Optimized image and icon assets with clear usage rights.
5. Working CTA and contact-form behavior.
6. Basic accessibility, responsive-layout, and browser checks.
7. A list of unresolved content or asset dependencies.

## 14. Acceptance checklist

The landing page is ready for review when:

- [ ] The value proposition is understandable without technical knowledge.
- [ ] English/Tamil calling and Google Sheets bulk calling are presented accurately.
- [ ] Education and training lead qualification is the main positioning.
- [ ] The primary **Book a Demo** action is visible and works.
- [ ] Desktop and mobile layouts are complete.
- [ ] All navigation links and forms work.
- [ ] No private customer data or secrets appear in screenshots or source files.
- [ ] No unsupported statistics, testimonials, integrations, or certifications appear.
- [ ] Images are optimized and have appropriate alternative text.
- [ ] Keyboard navigation and color contrast have been checked.
- [ ] Legal links and contact details are either valid or clearly held back from launch.
- [ ] Final copy and visuals have been approved by the product owner.

## 15. Recommended first milestone

Create a low-fidelity wireframe for desktop and mobile using the structure in this document. Review the messaging, CTA, and section order before investing time in detailed visual design or implementation.

