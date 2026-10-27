import Link from "next/link";
import { DefenseRows } from "@/components/landing/DefenseRows";
import { HeroRoom } from "@/components/landing/HeroRoom";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { RevealObserver } from "@/components/landing/Motion";
import { StartDialog } from "@/components/landing/StartDialog";
import { highlightPython } from "@/lib/highlight";
import "@/components/landing/landing.css";

const TOUR_CODE = `for right, t in enumerate(temps):
    while lows and temps[lows[-1]] >= t:
        lows.pop()
    lows.append(right)
    while highs and temps[highs[-1]] <= t:
        highs.pop()
    highs.append(right)
    while temps[highs[0]] - temps[lows[0]] > k:
        left += 1`;

const REPO = "https://github.com/QuantumGuy99/Meta-Hacks";

// From README "Meta models we use".
const MODELS: { group: string; rows: { name: string; use: string; tone: string }[] }[] = [
  {
    group: "Live interviewer",
    rows: [
      { name: "Muse Spark 1.3", use: "Analyzer, replies", tone: "accent" },
      { name: "Muse Voice Transcribe", use: "Think-aloud speech", tone: "accent" },
    ],
  },
  {
    group: "Audit and reports",
    rows: [{ name: "Muse Wonder 1.0", use: "Project audit, reports", tone: "ink" }],
  },
  {
    group: "Chaos lab",
    rows: [
      { name: "Muse Glimmer", use: "Attack scripts", tone: "ink" },
      { name: "Muse Spark Open", use: "Failover, problem drafts", tone: "muted" },
    ],
  },
  {
    group: "Extras",
    rows: [
      { name: "Muse Image", use: "Problem illustrations", tone: "muted" },
      { name: "SAM 3.1", use: "Paper sketches, stretch", tone: "muted" },
    ],
  },
];

export default async function Home() {
  const tourCodeHtml = await highlightPython(TOUR_CODE);
  return (
    <div className="lp">
      <RevealObserver />
      <header className="lp-nav">
        <Link href="/" className="lp-wordmark" translate="no">
          Crucible
        </Link>
        <nav aria-label="Main">
          <a href="#coding">Coding Interview</a>
          <a href="#defense">Project Defense</a>
          <a href="#models">Models</a>
          <a href={REPO}>GitHub</a>
        </nav>
      </header>

      <main id="main" tabIndex={-1}>
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <h1 id="hero-title" className="lines">
              <span className="line">
                <span data-line style={{ "--i": 0 } as React.CSSProperties}>
                  Interviews That
                </span>
              </span>
              <span className="line">
                <span data-line style={{ "--i": 1 } as React.CSSProperties}>
                  Watch You Code
                </span>
              </span>
            </h1>
            <div className="hero-aside">
              <p className="hero-sub">
                Crucible is an AI technical interviewer. It follows every edit and every word, nudges
                you when you skip a step, and grades how you got there.
              </p>
              <div className="hero-actions">
                <Link href="/coding" className="ui-btn ui-btn-primary ui-btn-lg">
                  Start a Coding Interview
                </Link>
                <Link href="/defense" className="lp-link">
                  Or Defend a Project
                </Link>
              </div>
            </div>
          </div>
          <div className="hero-stage">
            <HeroRoom />
          </div>
        </section>

        <section id="defense" className="sec sec-defense" aria-labelledby="defense-title">
          <h2 id="defense-title" data-reveal>
            Break It, Then Defend It
          </h2>
          <p className="sec-lead" data-reveal>
            Bring a small Python web app. Crucible audits it, attacks it in a sandbox, asks you why it
            broke, and re-runs the same attack on your fix.
          </p>
          <DefenseRows />
        </section>

        <section id="coding" className="sec sec-how" aria-labelledby="how-title">
          <h2 id="how-title" data-reveal>
            One Coding Interview
          </h2>
          <HowItWorks codeHtml={tourCodeHtml} />
        </section>

        <section id="models" className="sec sec-models" aria-labelledby="models-title">
          <div className="models-col">
            <h2 id="models-title" data-reveal>
              Built on Meta Models
            </h2>
            {MODELS.map((g) => (
              <div key={g.group} className="mgroup" data-reveal>
                <p className="mgroup-name">{g.group}</p>
                <ul>
                  {g.rows.map((r) => (
                    <li key={r.name}>
                      <span className={`mdot mdot-${r.tone}`} aria-hidden />
                      <span className="mname" translate="no">
                        {r.name}
                      </span>
                      <span className="muse">{r.use}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <p className="models-note" data-reveal>
            The model suggests; code decides. Every intervention passes cooldowns, a hint ladder and a
            leak guard before it reaches you, so the interviewer never hands over the answer.
          </p>
        </section>

        <section className="cta" aria-labelledby="cta-title">
          <div className="cta-copy">
            <h2 id="cta-title">
              Start the
              <br />
              Interview
            </h2>
            <p>
              You get an original problem, a Python editor and an interviewer who is already listening.
              No account needed.
            </p>
          </div>
          <div className="cta-dialog">
            <StartDialog />
          </div>
        </section>
      </main>

      <footer className="tiles">
        <div className="tile tile-word" aria-hidden translate="no">
          Crucible
        </div>
      </footer>
    </div>
  );
}
