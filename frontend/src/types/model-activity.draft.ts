// DRAFT until PR #39 merges: `model.activity` for the Under the hood strip, copied from that PR's generated
// contracts.ts. When #39 is on main, delete this file and import ModelActivity / ModelActivityMsg from
// "@/types/contracts" instead (contracts.ts itself is generated and never edited by hand).

export interface ModelActivity {
  call_id: string;
  t: number;
  model_name: "Muse Spark" | "Muse Wonder" | "Muse Spark Open" | "Muse Voice" | "SAM 3.1" | "Muse Image";
  task: string;
  status: "started" | "done" | "fallback" | "cached" | "failed" | "stopped";
  latency_ms: number | null;
}

export interface ModelActivityMsg {
  type: "model.activity";
  activity: ModelActivity;
}

/** An activity as the room keeps it: `wall` is Date.now() when it arrived live (absent from history). */
export type ActivityEvent = ModelActivity & { wall?: number };

/** The timeline kind #39 records these under (for the replay). */
export const MODEL_ACTIVITY_KIND = "model_activity";
