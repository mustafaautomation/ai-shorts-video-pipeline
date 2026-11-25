export type StageName =
  | "scrape"
  | "dedupe"
  | "transcribe"
  | "script"
  | "scenes"
  | "voice"
  | "render"
  | "approval"
  | "publish";

export type StageState = {
  name: StageName;
  label: string;
  status: "waiting" | "running" | "done" | "skipped";
  detail: string;
};

export const STAGE_LABELS: { name: StageName; label: string }[] = [
  { name: "scrape", label: "Scrape" },
  { name: "dedupe", label: "Dedupe" },
  { name: "transcribe", label: "Transcribe" },
  { name: "script", label: "Script" },
  { name: "scenes", label: "Scenes" },
  { name: "voice", label: "Voice" },
  { name: "render", label: "Render" },
  { name: "approval", label: "Approval" },
  { name: "publish", label: "Publish" },
];

export type FixtureReel = {
  id: string;
  username: string;
  caption: string;
  views: number;
  likes: number;
  comments: number;
  transcript: string;
};

export const FIXTURES: FixtureReel[] = [
  {
    id: "reel_sample_alpha",
    username: "fieldnotes",
    caption: "One picture, then one action.",
    views: 180000,
    likes: 12400,
    comments: 860,
    transcript:
      "People remember a single picture. Show the messy desk, name the one thing to move, and ask them to try it before the next meeting.",
  },
  {
    id: "reel_sample_beta",
    username: "fieldnotes",
    caption: "A list of seven tips.",
    views: 42000,
    likes: 900,
    comments: 40,
    transcript: "Here are seven tips about focus that you will forget.",
  },
  {
    id: "reel_sample_gamma",
    username: "studio.north",
    caption: "Quiet walkthrough.",
    views: 96000,
    likes: 5100,
    comments: 210,
    transcript: "Walk the idea from the problem to the ask without a list.",
  },
];

export function rankFixtures(): FixtureReel[] {
  return [...FIXTURES].sort(
    (a, b) => (b.likes + b.comments) / b.views - (a.likes + a.comments) / a.views,
  );
}

const USED_KEY = "shorts-demo-used-ids";

export function usedIds(): string[] {
  if (typeof localStorage === "undefined") return [];
  try {
    const parsed = JSON.parse(localStorage.getItem(USED_KEY) || "[]") as unknown;
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : [];
  } catch {
    return [];
  }
}

export function claimId(id: string): boolean {
  const current = usedIds();
  if (current.includes(id)) return false;
  localStorage.setItem(USED_KEY, JSON.stringify([...current, id]));
  return true;
}

export function resetUsed(): void {
  localStorage.removeItem(USED_KEY);
}

export type SceneCard = { index: number; narration: string; prompt: string; seed: number };

export function scenesFromScript(hook: string, body: string[], cta: string, seed: number): SceneCard[] {
  return [hook, ...body, cta].slice(0, 6).map((narration, index) => ({
    index,
    narration,
    prompt: `Vertical still, no letters, one subject: ${narration}`,
    seed: seed + index,
  }));
}

export type PublishReceipt = {
  platform: string;
  request: Record<string, unknown>;
};

export function mockReceipts(hook: string, topic: string): PublishReceipt[] {
  const caption = `${hook}\n\n#shorts #reels #learnontiktok`;
  return [
    {
      platform: "instagram_reels",
      request: {
        steps: [
          {
            method: "POST",
            url: "https://graph.facebook.com/v21.0/{ig-user-id}/media",
            json: { media_type: "REELS", caption, share_to_feed: true, video_url: "blob://reel.mp4" },
          },
          {
            method: "GET",
            url: "https://graph.facebook.com/v21.0/{container-id}",
            query: { fields: "status_code" },
            until: { field: "status_code", equals: "FINISHED" },
          },
          {
            method: "POST",
            url: "https://graph.facebook.com/v21.0/{ig-user-id}/media_publish",
            json: { creation_id: "<id from step 1>" },
          },
        ],
        dry_run: true,
      },
    },
    {
      platform: "tiktok",
      request: {
        method: "POST",
        url: "https://open.tiktokapis.com/v2/post/publish/video/init/",
        json: {
          post_info: { title: hook.slice(0, 150), privacy_level: "SELF_ONLY" },
          source_info: { source: "FILE_UPLOAD" },
        },
        dry_run: true,
      },
    },
    {
      platform: "youtube_shorts",
      request: {
        method: "POST",
        url: "https://www.googleapis.com/upload/youtube/v3/videos?part=snippet,status",
        json: {
          snippet: { title: hook.slice(0, 100), description: `${caption}\n\n#Shorts`, categoryId: "22" },
          status: { privacyStatus: "private", selfDeclaredMadeForKids: false },
        },
        dry_run: true,
        topic,
      },
    },
  ];
}
