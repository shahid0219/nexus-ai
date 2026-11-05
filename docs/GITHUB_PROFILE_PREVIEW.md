# Proposed GitHub profile changes — PENDING OWNER APPROVAL

Nothing in this document has been applied. The account is `shahid0219`
(created 2025-07-20, currently **0 public repositories**, no bio, no name set).
Every claim below is derived only from files and repositories that actually exist.

---

## 1. Public facts observed (evidence)

| Fact | Source |
|---|---|
| Python 248 KB, JavaScript 247 KB, CSS 14.6 KB, Batchfile 3.2 KB, HTML 295 B | `GET /repos/shahid0219/nexus-ai/languages` |
| TypeScript 598 KB, Shell 1.4 KB, CSS 877 B, JavaScript 227 B | `GET /repos/shahid0219/brokerops-lite/languages` |
| NEXUS AI is private, Python, built 2026-11-03 → 2026-11-04 | repo metadata |
| BrokerOps Lite is private, TypeScript, "Goa broker desk" | repo metadata |
| No public repos, 0 followers, no bio, no display name | `GET /user` |
| Local project `ai_business` exists (local-first research→product→marketing→sales pipeline) | local filesystem, not on GitHub |

**Deliberately excluded:** no degree, no employer, no years-of-experience claim, no
metrics, no follower/star counts, no contact details, no local paths.

---

## 2. Proposed repository descriptions and topics

### `shahid0219/nexus-ai` (stays **private** unless you say otherwise)

Description:
`Local-first autonomous growth platform — Python/FastAPI + React, local LLM routing, approval-gated publishing.`

Topics: `python` `fastapi` `react` `sqlite` `ollama` `local-first` `ai-agents`

### `shahid0219/brokerops-lite` (stays private)

Description: keep the existing accurate line
`BrokerOps Lite — Goa broker desk (Day-1 paste + follow-up spine)`

Topics: `typescript` `operations` `workflow`

---

## 3. Proposed profile README (`shahid0219/shahid0219`)

This repository does **not** exist yet. Creating it is a public action and needs
your approval. Proposed content:

```markdown
<!-- nexus-managed-profile -->

### Hi, I'm Shahid

Backend-leaning full-stack developer. I build local-first tools that run on your
own machine, keep your data local, and never pretend an integration works when it
does not.

**Working with:** Python (FastAPI, SQLite, stdlib), TypeScript/JavaScript, React,
FFmpeg, Batch/PowerShell for Windows automation.

**What I'm focused on**
- Local LLM routing — one provider interface with graceful degradation to
  deterministic, clearly-labelled output when no model is available.
- Approval-gated automation: any action that publishes, spends, deletes or
  messages a real person stops and asks first.
- Honest software: no fabricated analytics, no fake success states, no scraping.

**Currently building**
- **NEXUS AI** — a local-first growth platform: FastAPI backend, React dashboard,
  SQLite state, Ollama for inference, official-only platform APIs.
  *(private)*
- **BrokerOps Lite** — an operations desk for a Goa brokerage: day-one paste
  workflow and follow-up spine. *(private)*

**How I work**
`verify → measure → keep what works` — and document the limits instead of hiding
them.

<sub>Most of my current repositories are private while they stabilise. Public work
appears here as it is ready.</sub>
```

---

## 4. Proposed account-level changes

| Field | Current | Proposed |
|---|---|---|
| Bio | *(empty)* | `Local-first developer — Python, TypeScript, React. Building honest, approval-gated automation.` (98 chars) |
| Display name | *(empty)* | `Shahid` |
| Pinned repos | none | `shahid0219/shahid0219` (profile), and the two project repos **only if** you make them public |

**Permission note:** editing the *bio* and *display name* requires a token with
the `user` scope. Your current `gh` token has `gist, read:org, repo, workflow` —
it can create repos and edit repo metadata, but **not** the profile bio. Enabling
that needs `gh auth refresh -s user`, which re-authorises your account. I will not
run it without your explicit approval.

---

## 5. What I need from you

1. Approve creating the public `shahid0219/shahid0219` profile-README repo with the
   text above? (public action)
2. Approve setting the repository descriptions/topics listed in §2?
3. Do you want `nexus-ai` and/or `brokerops-lite` made public, or kept private?
4. Approve `gh auth refresh -s user` so the bio/display-name can be set?
   (skip if you prefer to leave the profile header untouched)

Until then, the only thing NEXUS will do is show this preview.
