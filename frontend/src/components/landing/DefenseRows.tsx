"use client";

import NumberFlow from "@number-flow/react";
import { useState } from "react";
import { toast } from "sonner";
import { LiveLoadChart } from "@/components/defense/LiveLoadChart";
import { ActivityIcon } from "@/components/ui/activity";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const count = new Intl.NumberFormat("en-US");

// One finding from the bank-transfer sample app, shown in the three states the chaos lab moves it through.
function FindingHead() {
  return (
    <div className="fr-head">
      <span className="sev">High</span>
      <strong>
        Race condition in <code translate="no">POST /transfer</code>
      </strong>
      <span className="fr-file" translate="no">
        app/routes/transfer.py:41–58
      </span>
    </div>
  );
}

export function DefenseRows() {
  const [fixed, setFixed] = useState(false);

  return (
    <div className="fr-stack">
      <div className="fr-group" data-reveal>
        <p className="fr-state">Found</p>
        <div data-ui className="fr">
          <FindingHead />
          <p className="fr-line">
            Balances are read, changed and written back without a lock. Two transfers from the same
            account can both pass the balance check.
          </p>
          <div className="fr-foot">
            <span>Audit · Muse Wonder 1.0</span>
            <span>Attack queued: 200 concurrent, 30 s</span>
          </div>
        </div>
      </div>

      <div className="fr-group" data-reveal>
        <p className="fr-state">{fixed ? "Held" : "Broke"}</p>
        <div data-ui className={fixed ? "fr fr-held" : "fr fr-broke fr-hover"}>
          <FindingHead />
          {fixed ? (
            <p className="fr-line" aria-live="polite">
              Re-ran the same attack on your fix: 500 of 500 transfers applied, balances still sum to
              {usd.format(10_000)}.
            </p>
          ) : (
            <p className="fr-line" aria-live="polite">
              Under {count.format(200)} concurrent transfers, 37 of {count.format(500)} were lost and{" "}
              <b>{usd.format(1_240)} disappeared</b>.
            </p>
          )}
          <div className="fr-live">
            <span className="fr-live-label">
              <ActivityIcon size={14} aria-hidden /> Live p95 latency, 200 concurrent
            </span>
            <LiveLoadChart mode={fixed ? "held" : "broke"} height={96} />
          </div>
          <dl className="fr-metrics">
            <div>
              <dt>Lost transfers</dt>
              <dd className={fixed ? "is-ok" : "is-bad"}>
                <NumberFlow value={fixed ? 0 : 37} />
              </dd>
            </div>
            <div>
              <dt>Missing</dt>
              <dd className={fixed ? "is-ok" : "is-bad"}>
                <NumberFlow value={fixed ? 0 : 1240} format={{ style: "currency", currency: "USD", maximumFractionDigits: 0 }} />
              </dd>
            </div>
            <div>
              <dt>p95</dt>
              <dd>
                <NumberFlow value={fixed ? 38 : 412} suffix=" ms" />
              </dd>
            </div>
          </dl>
          <div className="fr-foot">
            {fixed ? (
              <span className="gate">Merge gate: pass</span>
            ) : (
              <span>Invariant broken: sum of balances</span>
            )}
            <span className="fr-actions">
              <button
                type="button"
                className="ui-btn ui-btn-primary"
                onClick={() => {
                  const next = !fixed;
                  setFixed(next);
                  if (next) toast.success("Attack re-run: the fix held", { description: "500 of 500 transfers applied." });
                }}
              >
                {fixed ? "Show the Failing Run" : "Apply Fix & Re-run"}
              </button>
            </span>
          </div>
        </div>
      </div>

      <div className="fr-group" data-reveal>
        <p className="fr-state">Defended</p>
        <div data-ui className="fr fr-held">
          <FindingHead />
          <p className="fr-line">
            &ldquo;Both requests read 400 before either wrote. I wrapped the debit and credit in one
            transaction with a row lock.&rdquo;
          </p>
          <div className="fr-foot">
            <span>Grill · 8 of 10 · hit 3 of 3 expected points</span>
            <span className="gate">Fix verified</span>
          </div>
        </div>
      </div>
    </div>
  );
}
