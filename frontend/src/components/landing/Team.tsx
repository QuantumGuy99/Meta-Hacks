import Image from "next/image";

// Who builds Ares and what each person owns (plan/README.md). Photos are square crops centred on
// the body, wide enough to show the suit. Members without a photo yet get
// their initials in the same circular frame, so every tile carries the same weight.
type Member = {
  name: string;
  role: string;
  owns: string;
  photo?: string;
};

const TEAM: Member[] = [
  {
    name: "Srinithin Ganesh",
    role: "Interviewer engine",
    owns: "Built the live interviewer at the heart of Ares: it follows every edit, knows when to step in, and replays the session",
    photo: "/team/srinithin-ganesh-team.jpg",
  },
  {
    name: "Shreyas Sahoo",
    role: "Defense and infrastructure",
    owns: "Built the defense lab that audits your app, breaks it under load in a sandbox, and proves your fix, plus the runner behind it",
    photo: "/team/shreyas-sahoo-team.jpg",
  },
  {
    name: "Likhil Gudipati",
    role: "Frontend and design",
    owns: "Designed and built every screen of Ares, from the live interview room to the defense lab and replay",
    photo: "/team/likhil-gudipati-team.jpg",
  },
  {
    name: "Sharvil Talware",
    role: "Data and evals",
    owns: "Wrote the original problem bank and the sample apps the chaos lab attacks, plus the evals that keep the interviewer honest",
  },
];

const initials = (name: string) =>
  name
    .split(" ")
    .map((part) => part[0])
    .join("");

export function Team() {
  return (
    <ul className="team-grid">
      {TEAM.map((m) => (
        <li key={m.name} className="team-member" data-reveal>
          <div className="team-photo">
            {m.photo ? (
              <Image
                src={m.photo}
                alt={m.name}
                fill
                sizes="160px"
                className="team-img"
              />
            ) : (
              <span className="team-initials" aria-hidden>
                {initials(m.name)}
              </span>
            )}
          </div>
          <p className="team-role">{m.role}</p>
          <p className="team-name" translate="no">
            {m.name}
          </p>
          <p className="team-owns">{m.owns}</p>
        </li>
      ))}
    </ul>
  );
}
