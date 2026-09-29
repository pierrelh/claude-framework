---
name: fw-brief
description: Elicit and write the product brief (docs/product/brief.md) — a structured interview when the user has a precise need, or a short exploratory framing with explicit assumptions for a POC or vague idea. Use during /fw-init or when the product direction changes.
argument-hint: "[optional: the need in the user's words]"
---

# /fw-brief — define the need

Input: `$ARGUMENTS` plus whatever the user already said. Output: `docs/product/brief.md`
built from `framework/templates/brief.template.md`, in `docs_language`, approved by the user.

## 1. Choose the depth with the user
Ask (AskUserQuestion):
- **Precise** — "I know what I want": structured interview, the result is predictable.
- **Exploratory / POC** — "I have an idea, surprise me": few questions, you make explicit
  assumptions. Warn honestly: *the less we specify, the more the result is my interpretation.*
If the opening message is already detailed, propose *Precise* and pre-fill from it.

## 2a. Precise — interview in rounds (max 3 rounds, 3–5 questions each)
Skip what is already known; offer options with a recommendation when you can.
1. **Problem & users** — what problem, for whom (personas), how do they cope today?
2. **Goals & success** — what changes for them; measurable success criteria (numbers,
   deadlines, thresholds).
3. **Scope** — must-have features for the first release; nice-to-have; explicitly out.
4. **Constraints** — imposed stack/hosting, deadline, budget, integrations (APIs, SSO,
   payment), data (existing data to migrate? personal data → GDPR), languages/i18n,
   accessibility, expected load.
5. **Non-functional** — security level, performance, availability, compliance.
6. **Risks & open questions** — what could make this fail; what nobody knows yet.

## 2b. Exploratory / POC — three questions only
1. The idea in one or two sentences.
2. Who is it for / who will see the demo?
3. What must the POC prove (the one thing that makes it a success)?
Then **you** fill the rest with explicit, labelled assumptions (personas, scope, stack
suggestion, a single milestone "POC", a time box in hours). Every assumption goes in the
*Assumptions* section so the user can overrule it.

## 2c. Adopt mode (existing codebase)
Document the product as it is (from the code exploration), then run 2a or 2b on
**what comes next** (the user's request). The brief has two parts: *Current product* and
*Next increment*.

## 3. Write and validate
- Fill the template completely; remove sections that truly don't apply rather than leaving
  them empty. Numbers over adjectives ("< 2 s" not "fast").
- Show a short summary (not the whole file) and ask for approval or changes. Iterate.
- Record `fw config set brief_mode precise|exploratory`.
- The brief is the reference for the backlog: every Must feature must be traceable to a
  goal of the brief.
