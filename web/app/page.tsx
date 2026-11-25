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
            A daily reel pipeline: scrape what performed, skip ids already used, write an original script,
            and render a 1080×1920 MP4 in the browser. Nothing posts without Approve. This is not client work.
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
        The phone starts on a reel the Python CLI rendered with ffmpeg. Run the pipeline and it is replaced
        by an MP4 this browser encoded. The CLI path is the worker. This page is the free, keyless demo.
        Instagram, TikTok, and YouTube receipts are mock payloads.
      </p>
    </main>
  );
}
