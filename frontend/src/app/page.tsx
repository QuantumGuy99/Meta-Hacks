import Link from "next/link";
import { DefenseRows } from "@/components/landing/DefenseRows";
import { Facts } from "@/components/landing/Facts";
import { HeroRoom } from "@/components/landing/HeroRoom";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { LandingMotion } from "@/components/landing/Motion";
import { StartDialog } from "@/components/landing/StartDialog";
import { Team } from "@/components/landing/Team";
import { HeadlineReveal } from "@/components/motion/HeadlineReveal";
import { SmoothScroll } from "@/components/motion/SmoothScroll";
import Magnet from "@/components/react-bits/Magnet";
import ScrollFloat from "@/components/react-bits/ScrollFloat";
import ScrollReveal from "@/components/react-bits/ScrollReveal";
import { DRAFT_CODE } from "@/lib/fixtures";
import { highlightPython } from "@/lib/highlight";
import "@/components/landing/landing.css";
import "@/components/landing/sections.css";

const REPO = "https://github.com/QuantumGuy99/Meta-Hacks";

// The project's own design rules (README "Design rules"), shown as the credibility section.
const PRINCIPLES = [
  ["The model suggests; code decides.", "Models propose interventions. Code decides when, and whether, anything reaches you."],
  ["Never hand over the answer.", "Hints escalate from nudge to question to hint to concept. Never code."],
  ["Neutral integrity.", "Pastes and tab switches are noted as facts in the report, never as accusations."],
  ["The timeline is the source of truth.", "Every score and replay is built only from recorded edits, speech, runs and nudges."],
  ["Every external call has a fallback.", "A slow model or sandbox degrades the session; it never breaks it."],
];

export default async function Home() {
  const tourCodeHtml = await highlightPython(DRAFT_CODE);
  return (
    <div className="lp">
      <SmoothScroll />
      <LandingMotion />

      {/* 1. Minimal nav: logo and the primary action */}
      <header className="lp-nav">
        <Link href="/" className="lp-wordmark" translate="no">
          Ares
        </Link>
        <a href="#start" className="ui-btn ui-btn-primary nav-cta">
          Start Interview
        </a>
      </header>

      <main id="main" tabIndex={-1}>
        {/* 2. Hero: eight-word headline, sub-headline, two equal actions (one per mode) */}
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <HeadlineReveal as="h1" id="hero-title" onLoad>
              Practice Tools Grade Answers. Ares Grades <span className="fx-lime">How You Engineer.</span>
            </HeadlineReveal>
            <div className="hero-aside">
              <p className="hero-sub">
                A live AI interviewer that follows <strong>every edit and every word</strong>, nudges you
                when you skip a step, and <strong>scores your process</strong>, not just your output.
              </p>
              <div className="hero-actions">
                <Magnet padding={40} magnetStrength={8} maxOffset={6}>
                  <Link href="/coding" className="ui-btn ui-btn-primary ui-btn-lg">
                    Start a Coding Interview
                  </Link>
                </Magnet>
                <Magnet padding={40} magnetStrength={8} maxOffset={6}>
                  <Link href="/defense" className="ui-btn ui-btn-primary ui-btn-lg">
                    Defend a Project
                  </Link>
                </Magnet>
              </div>
            </div>
          </div>
          <div className="hero-stage">
            <HeroRoom />
          </div>
        </section>

        {/* 3. Verifiable facts strip */}
        <Facts />

        {/* 4. The problem and the answer */}
        <section className="sec sec-story" aria-labelledby="story-title">
          <HeadlineReveal id="story-title">
            Two Gaps Practice Tools <span className="fx-lime">Miss</span>
          </HeadlineReveal>
          <div className="story-rows">
            <div className="story-row" data-reveal>
              <p className="story-claim">Practice tools grade the answer. Interviewers grade the process.</p>
              <p className="story-detail">
                LeetCode tells you whether your code passed. It <strong>can’t tell you</strong> that you
                coded before stating an approach, skipped the empty-input case, went quiet for four
                minutes, or needed three hints.
              </p>
            </div>
            <div className="story-row" data-reveal>
              <p className="story-claim">AI writes code faster than you can explain it.</p>
              <p className="story-detail">
                You can generate a thousand lines in a minute and still not know why your endpoint{" "}
                <strong>loses data under 200 concurrent requests</strong>. That gap shows up in interviews,
                and in production.
              </p>
            </div>
          </div>
          <ScrollReveal
            as="p"
            containerClassName="story-answer"
            textClassName="story-answer-text"
            baseOpacity={0.2}
            baseRotation={0}
            blurStrength={2}
          >
            Ares closes both with one idea: an interviewer that sees your process as it happens, every keystroke, every test run, every sentence, and holds you to what a strong engineer would do.
          </ScrollReveal>
        </section>

        {/* 5. Feature showcase: the two modes, given the same weight and the same header */}
        <section id="coding" className="sec sec-mode sec-how" aria-labelledby="how-title">
          <div className="mode-head">
            <HeadlineReveal id="how-title">
              Live Coding <span className="fx-lime">Interview</span>
            </HeadlineReveal>
            <div className="mode-copy" data-reveal>
              <p className="sec-lead">
                Pick a difficulty and get <strong>an original problem</strong>. Code in a real editor and
                think out loud; the interviewer follows every edit and{" "}
                <strong>nudges you when you skip a step</strong>.
              </p>
              <Link href="/coding" className="ui-btn ui-btn-primary ui-btn-lg">
                Start a Coding Interview
              </Link>
            </div>
          </div>
          <HowItWorks codeHtml={tourCodeHtml} />
        </section>

        <section id="defense" className="sec sec-mode sec-defense" aria-labelledby="defense-title">
          <div className="mode-head">
            <HeadlineReveal id="defense-title">
              Project <span className="fx-lime">Defense</span>
            </HeadlineReveal>
            <div className="mode-copy" data-reveal>
              <p className="sec-lead">
                Bring a small Python web app. Ares audits it, <strong>attacks it in a sandbox</strong>,
                asks you why it broke (circle the culprit on the diagram), and{" "}
                <strong>re-runs the same attack on your fix</strong>.
              </p>
              <Link href="/defense" className="ui-btn ui-btn-primary ui-btn-lg">
                Defend a Project
              </Link>
            </div>
          </div>
          <DefenseRows />
        </section>

        {/* 6. Credibility: the team's reason, and the rules the interviewer is held to */}
        <section className="sec sec-cred" aria-labelledby="cred-title">
          <HeadlineReveal id="cred-title">
            Held to <span className="fx-lime">Its Own</span> Rules
          </HeadlineReveal>
          <div className="cred-grid">
            <figure className="cred-quote" data-reveal>
              <blockquote>
                <p>
                  “We’re students who grind LeetCode and use AI coding agents every day.”
                </p>
                <p>
                  “The AI technical interviewer that watches <em>how</em> you engineer, not just what you
                  submit.”
                </p>
              </blockquote>
              <figcaption>
                <span>The Ares team</span>
                <span className="cred-meta">Meta Global AI Developer Hackathon, 2026</span>
                <a href={REPO} className="lp-link">
                  Read the source on GitHub
                </a>
              </figcaption>
            </figure>
            <div className="cred-term" data-reveal data-ui>
              <div className="cred-term-bar">
                <span translate="no">PRINCIPLES.md</span>
              </div>
              <ol className="cred-rules">
                {PRINCIPLES.map(([rule, detail]) => (
                  <li key={rule}>
                    <strong>{rule}</strong>
                    <span>{detail}</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </section>

        {/* The people building it */}
        <section id="team" className="sec sec-team" aria-labelledby="team-title">
          <div className="mode-head">
            <HeadlineReveal id="team-title">
              Four Builders, One <span className="fx-lime">Interviewer</span>
            </HeadlineReveal>
            <div className="mode-copy" data-reveal>
              <p className="sec-lead">
                Each of us owns one part of Ares end to end, and <strong>all four parts meet</strong> in
                the same live session.
              </p>
            </div>
          </div>
          <Team />
        </section>

        {/* 7. Final action band */}
        <section id="start" className="cta" aria-labelledby="cta-title">
          <div className="cta-copy">
            <HeadlineReveal id="cta-title">Pick Your Interview</HeadlineReveal>
            <p>
              Code an original problem live, or defend a project under load.{" "}
              <strong>Same interviewer, same scored replay.</strong> No account, no setup: you’re started
              in under a minute.
            </p>
          </div>
          <div className="cta-dialog">
            <StartDialog />
          </div>
        </section>
      </main>

      {/* 8. Clean, functional footer */}
      <footer className="site-foot">
        <div className="foot-top">
          <div className="foot-brand">
            <Link href="/" className="lp-wordmark" translate="no">
              Ares
            </Link>
            <p>The AI interviewer that watches how you engineer.</p>
          </div>
          <nav className="foot-links" aria-label="Footer">
            <div>
              <p className="foot-head">Practice</p>
              <Link href="/coding">Coding Interview</Link>
              <Link href="/defense">Project Defense</Link>
            </div>
            <div>
              <p className="foot-head">Demos</p>
              <Link href="/coding/demo">Interview Room</Link>
              <Link href="/defense/demo">Defense Lab</Link>
              <Link href="/report/demo">Session Report</Link>
            </div>
            <div>
              <p className="foot-head">Project</p>
              <a href="#team">Team</a>
              <a href={REPO}>GitHub</a>
              <a href={`${REPO}/blob/main/LICENSE`}>MIT License</a>
            </div>
          </nav>
        </div>
        <div className="tile tile-word" aria-hidden translate="no">
          <ScrollFloat
            containerClassName="word-float"
            textClassName="word-float-text"
            scrollStart="top bottom"
            scrollEnd="center bottom"
            stagger={0.03}
            distance={48}
          >
            Ares
          </ScrollFloat>
        </div>
      </footer>
    </div>
  );
}
