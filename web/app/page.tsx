import { Studio } from "./studio";

export default function HomePage() {
  return (
    <main className="page">
      <p className="eyebrow">
        Portfolio demo
        <a href="https://github.com/mustafaautomation/ai-shorts-video-pipeline">mustafaautomation</a>
      </p>
      <section className="hero">
        <div>
          <h1>A topic becomes a reel.</h1>
          <p className="lede">
            Write a 30–45 second short, hear it, and burn the words onto a vertical frame. Instagram,
            TikTok, and YouTube stay mocked until a real account is approved. This is not client work.
          </p>
        </div>
        <div className="phone">
          <video
            src="/demo-reel.mp4"
            controls
            playsInline
            preload="metadata"
            aria-label="Sample vertical reel rendered by the pipeline"
          />
        </div>
      </section>
      <Studio />
      <p className="note">
        Full rendering stays in the Python pipeline and in CI. This site only writes the script, then
        optionally speaks it with the browser. Publishing adapters record the payload they would send
        and do not call the platforms.
      </p>
    </main>
  );
}
