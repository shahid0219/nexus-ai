"""Deterministic offline fallbacks for every AI call.

These produce genuinely useful, structured content from the inputs alone — no invented
facts, no fabricated data. Every result is labelled generated_by='fallback' so the UI
can show it honestly. Ollama replaces these when it is running.
"""
import re
import textwrap


def general(prompt: str) -> str:
    p = (prompt or "").strip()
    topic = p[:120] if p else "your request"
    return (
        f"[offline fallback — Ollama not running]\n\n"
        f"Analysis of: {topic}\n\n"
        f"1. Restate the goal in one sentence.\n"
        f"2. List the 3 constraints that matter most.\n"
        f"3. Draft a first version using only facts already provided.\n"
        f"4. Identify what must be verified externally before publishing.\n\n"
        f"Start Ollama (ollama serve) and pull a small model for full generation, e.g.\n"
        f"  ollama pull qwen2.5:3b"
    )


def _topic(prompt: str, default: str = "the topic") -> str:
    m = re.search(r"(?:topic|about|for|on)\s+[:\-]?\s*(.+)", prompt or "", re.I)
    if m:
        return m.group(1).strip().strip(".\"'")[:80]
    line = (prompt or "").strip().splitlines()[0] if prompt else ""
    return (line[:80] or default)


def captions(topic: str, count: int = 3, tone: str = "engaging") -> list[dict]:
    hooks = [
        f"Most people get {topic} wrong from day one.",
        f"Here is the {topic} shortcut nobody hands you.",
        f"I wish someone had told me this about {topic} earlier.",
        f"Three things I learned the hard way about {topic}.",
        f"Stop scrolling if {topic} is on your list this year.",
    ]
    ctas = [
        "Save this for later and send it to someone who needs it.",
        "Follow for more no-fluff breakdowns every week.",
        "Comment your biggest {t} question — I read every one.".format(t=topic),
        "Share this with a teammate still doing it the hard way.",
        "Turn on notifications so you don't miss the next part.",
    ]
    out = []
    for i in range(max(1, min(count, 10))):
        hook = hooks[i % len(hooks)]
        body = (f"A practical {tone} take on {topic}:\n"
                f"- Start with the smallest version that works\n"
                f"- Measure one number, not ten\n"
                f"- Repeat what works before adding anything new")
        hashtags = ["#" + re.sub(r"\W+", "", w).lower()
                    for w in topic.split()[:4] if len(w) > 2]
        hashtags += ["#learn", "#growth"]
        out.append({"caption": f"{hook}\n\n{body}\n\n{ctas[i % len(ctas)]}",
                    "hashtags": hashtags[:8], "tone": tone})
    return out


def reels(topic: str, count: int = 3) -> list[dict]:
    out = []
    for i in range(max(1, min(count, 8))):
        n = i + 1
        out.append({
            "hook": f"The {topic} rule I break on purpose (part {n})",
            "beats": [
                f"0-2s: show the end result of {topic}",
                "3-7s: state the common mistake in one line",
                "8-20s: demonstrate the fix step by step",
                "21-27s: show the before/after difference",
                "28-30s: one-line recap + CTA",
            ],
            "cta": f"Follow for the full {topic} breakdown",
            "duration_s": 30,
        })
    return out


def script(topic: str, kind: str = "short") -> str:
    if kind == "short":
        return textwrap.dedent(f"""\
            SCRIPT — SHORT ({topic})
            ============================================
            HOOK (0-3s):    Watch this before you touch {topic} again.
            SETUP (4-8s):   Most tutorials skip the step that actually matters.
            BODY (9-22s):   Do it in three moves: prepare, execute, review.
                            Each move takes under a minute to learn.
            PAYOFF (23-27s): That is the whole {topic} loop — no tools, no fluff.
            CTA (28-30s):   Follow for part 2 where we go one level deeper.
            """)
    return textwrap.dedent(f"""\
        SCRIPT — LONG FORM ({topic})
        ============================================
        INTRO (0:00-0:20)
          - Cold open: the result first, no preamble.
          - One sentence on why {topic} matters right now.

        PROBLEM (0:20-1:30)
          - The default approach people take and where it breaks.
          - Concrete cost of doing it wrong (time, money, rework).

        METHOD (1:30-6:00)
          - Step 1: define the smallest working version.
          - Step 2: build it against one real example.
          - Step 3: measure one metric and iterate.
          - Step 4: remove everything that did not move the metric.

        PROOF (6:00-7:30)
          - Walk through the before/after with the actual numbers you have.
          - State clearly what is verified and what is estimated.

        RECAP (7:30-8:00)
          - Three-line summary, CTA to the next video, end screen.
        """)


def profile_analysis(profile_text: str) -> dict:
    text = profile_text or ""
    words = len(text.split())
    has_links = bool(re.search(r"https?://", text))
    has_metrics = bool(re.search(r"\d+%|\d+x|\b\d{3,}\b", text))
    lines = [l for l in text.splitlines() if l.strip()]
    return {
        "summary": (f"Profile analysed locally ({words} words, {len(lines)} lines). "
                    f"Ollama is offline, so this is a structural pass, not a deep critique."),
        "strengths": [
            "Content is present and can be parsed" if words > 10 else "Profile has some content to work with",
            "Contains a measurable claim" if has_metrics else "No numbers yet — add one real result",
            "Includes links" if has_links else "No links found — add one destination link",
        ],
        "gaps": [
            "State who it is for in the first line" if words > 5 and not re.search(r"for (founders|creators|devs|marketers)", text, re.I) else "Audience is defined",
            "Add a single clear call to action" if not re.search(r"(follow|dm|subscribe|download|book|link)", text, re.I) else "CTA present",
            "Lead with an outcome, not a job title" if re.search(r"^(developer|engineer|manager|student)\b", text, re.I) else "Opening line leads with value",
        ],
        "actions": [
            "Rewrite line 1 as: who you help + the outcome you deliver",
            "Add one verifiable number (projects shipped, users served, years)",
            "Pin one link that captures traffic",
            "Keep a 3-2-1 content rhythm: 3 practical posts, 2 stories, 1 offer per week",
        ],
        "structural": {"words": words, "lines": len(lines), "has_links": has_links,
                       "has_metrics": has_metrics},
    }


def niche_research(niche: str) -> dict:
    return {
        "tag": "hypothesis",
        "disclaimer": ("Hypothesis generated from local reasoning only — no live market data "
                       "was measured. Verify before investing."),
        "niche": niche,
        "audience_segments": [
            {"segment": f"Beginners entering {niche}", "pain": "Overwhelm, fear of wasting time",
             "content_angle": "One-result tutorials"},
            {"segment": f"Practitioners in {niche}", "pain": "Keeping up with tool changes",
             "content_angle": "Comparison + teardown posts"},
            {"segment": f"Buyers evaluating {niche}", "pain": "Trust and proof",
             "content_angle": "Case studies with real numbers"},
        ],
        "content_pillars": [f"Fundamentals of {niche}", f"Tools & workflows for {niche}",
                            f"Proof: real results in {niche}"],
        "differentiation_levers": [
            "Show the process, not only the result",
            "Publish verification steps others skip",
            "Own one narrow sub-topic before expanding",
        ],
        "first_30_days": ["Map 20 questions your audience actually asks",
                          "Publish 12 short pieces answering them",
                          "Run 1 long case study with measurable proof"],
    }


def topics(niche: str, count: int = 8) -> list[dict]:
    templates = [
        ("The beginner mistake that quietly costs you months in {n}", "mistake"),
        ("I tested 5 popular {n} workflows — here is what survived", "experiment"),
        ("{n} in 60 seconds: the one loop that works", "short"),
        ("Why most {n} advice fails for solo builders", "opinion"),
        ("The free {n} stack I would start with today", "stack"),
        ("A realistic {n} timeline: week 1 vs month 3", "timeline"),
        ("{n} checklist: 7 things to verify before you publish", "checklist"),
        ("How I review {n} results without fooling myself", "process"),
        ("3 {n} tools I stopped using (and what replaced them)", "tools"),
        ("The {n} question I get asked most — answered honestly", "qa"),
    ]
    return [{"title": t.format(n=niche or "this niche"), "format": f,
             "angle": f"Ground it in one concrete example from your own {niche or 'work'}."}
            for t, f in templates[:max(1, min(count, 10))]]


def audience(niche: str) -> dict:
    return {
        "tag": "hypothesis",
        "disclaimer": "Persona hypotheses from local reasoning — validate with your own audience data.",
        "personas": [
            {"name": "The Career Switcher", "goal": f"Get productive in {niche} fast",
             "fears": "Falling behind, choosing the wrong path",
             "where_they_hang": "YouTube searches, Reddit threads, Discord servers",
             "content_that_works": "Roadmaps, honest timelines, portfolio reviews"},
            {"name": "The Solo Builder", "goal": f"Ship something real with {niche}",
             "fears": "Scope creep, wasted tooling spend",
             "where_they_hang": "X/Twitter, niche newsletters, GitHub",
             "content_that_works": "Build logs, teardowns, cost breakdowns"},
            {"name": "The Team Lead", "goal": f"Adopt {niche} without chaos",
             "fears": "Team resistance, unclear ROI",
             "where_they_hang": "LinkedIn, industry Slack groups",
             "content_that_works": "Playbooks, before/after metrics, templates"},
        ],
        "validation_questions": [
            f"What almost stopped you from starting {niche}?",
            "Which of your current tools would you replace first?",
            "What result would make you pay for a solution today?",
        ],
    }


def platform_content(topic: str, platform: str) -> str:
    p = platform.lower()
    if "instagram" in p:
        return (f"{topic} — the short version.\n\n"
                f"1) Start with the result, not the intro.\n"
                f"2) Show one step anyone can copy today.\n"
                f"3) End with a question people can answer in one line.\n\n"
                f"Save it, then try it this week.")
    if "youtube" in p:
        return (f"Title: {topic}: What Actually Works\n\n"
                f"Description: In this video we break down {topic} with one real example, "
                f"the mistake most people make, and a 3-step fix you can apply today. "
                f"Timestamps below.\n\n0:00 Result first\n0:20 The problem\n"
                f"1:00 The 3-step fix\n2:30 Recap and next video")
    if "linkedin" in p:
        return (f"{topic} — three lessons I will not unlearn:\n\n"
                f"- Start smaller than feels useful.\n"
                f"- Measure one number and defend it.\n"
                f"- Delete what does not move it.\n\n"
                f"The unglamorous part is the part that works. Agree or disagree?")
    if "x" in p or "twitter" in p:
        return (f"Thread: {topic}\n\n1/ Most advice on {topic} is written for teams with budget.\n"
                f"2/ Here is the solo version: one tool, one metric, one weekly review.\n"
                f"3/ Step 1 — pick the smallest deliverable you can ship in a day.\n"
                f"4/ Step 2 — track one number. Ignore the rest for a month.\n"
                f"5/ Step 3 — cut anything that did not move it. That is the whole loop.")
    return f"{topic}\n\n- Practical angle\n- One real example\n- Clear next step"


def cover_letter(profile: dict, job: dict, skills_matched: list[str]) -> str:
    name = profile.get("name") or "Your name"
    company = (job or {}).get("company") or "the team"
    position = (job or {}).get("title") or "the position"
    skills = ", ".join(skills_matched[:6]) if skills_matched else "the core skills listed"
    exp_lines = []
    for e in (profile.get("experience") or [])[:3]:
        exp_lines.append(f"- {e.get('role', 'role')} at {e.get('company', 'company')} "
                         f"({e.get('dates', 'dates not provided')})")
    exp_block = "\n".join(exp_lines) if exp_lines else "- Experience details: [not provided]"
    return (f"Dear {company} hiring team,\n\n"
            f"I am applying for {position}. My background includes {skills}.\n\n"
            f"Relevant experience (from my profile, unedited facts):\n{exp_block}\n\n"
            f"I would welcome the chance to walk through how this maps to your requirements. "
            f"I have attached my CV, which contains only verified details from my profile.\n\n"
            f"Regards,\n{name}\n\n"
            f"[Draft only — review before sending; sending requires owner approval.]")
