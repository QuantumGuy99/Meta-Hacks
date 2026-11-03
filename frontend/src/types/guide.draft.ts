// DRAFT until PR #51 merges: the guide's request and reply (POST /api/guide), copied from that PR's generated
// contracts.ts. When #51 is on main, delete this file and import these from "@/types/contracts" instead
// (contracts.ts itself is generated and never edited by hand).

import type { Difficulty } from "./contracts";

export interface GuideTurn {
  role: "user" | "guide";
  text: string;
}

export interface GuideAsk {
  question: string;
  page: "home" | "coding_setup" | "defense_picker" | "room" | "report" | "other";
  in_session: boolean;
  /** At most 6 earlier turns. */
  history?: GuideTurn[];
}

export interface GuideAction {
  kind: "none" | "open_page" | "start_coding" | "start_defense";
  page: ("home" | "coding" | "defense" | "report") | null;
  difficulty: Difficulty | null;
  project_id: string | null;
}

export interface GuideReply {
  reply: string;
  action: GuideAction;
  source: "model" | "fallback";
}
