import { useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const release = {
  url: import.meta.env.VITE_DOWNLOAD_URL?.trim() || "https://github.com/kianjindal2010/stocksight-flow/releases",
  version: import.meta.env.VITE_RELEASE_VERSION?.trim() || "v1.0.2",
  size: import.meta.env.VITE_FILE_SIZE?.trim() || "58.4 MB",
  checksum: import.meta.env.VITE_SHA256?.trim() || "",
};

function isGithubReleasesUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "github.com" && /\/releases(?:\/|$)/.test(url.pathname);
  } catch {
    return false;
  }
}

const canDownload = isGithubReleasesUrl(release.url);
const hasChecksum = /^[a-fA-F0-9]{64}$/.test(release.checksum);

function DownloadButton({ className = "" }) {
  if (!canDownload) return <a className={`button button-primary ${className}`} href="https://github.com/kianjindal2010/stocksight-flow/releases" target="_blank" rel="noreferrer">Download on GitHub <span aria-hidden="true">↗</span></a>;
  return <a className={`button button-primary ${className}`} href={release.url} target="_blank" rel="noreferrer">Download for Windows <span aria-hidden="true">↗</span></a>;
}

const screenshots = [
  { src: "/screenshots/dashboard.jpg", alt: "StockSight Learner dashboard with paper-trading portfolio data", title: "Your learning dashboard", body: "A single workspace for market context, paper-trading progress, goals, and your portfolio." },
  { src: "/screenshots/ai-chat.jpg", alt: "StockSight Learner AI chat screen", title: "Ask better questions", body: "Explore market concepts in plain language and turn unfamiliar terms into a learning plan." },
  { src: "/screenshots/risk-lab.jpg", alt: "StockSight Learner risk lab screen", title: "See risk before acting", body: "Use guided tools to understand position size, uncertainty, and the trade-offs behind a decision." },
];

function App() {
  const [copied, setCopied] = useState(false);
  const copyChecksum = async () => {
    if (!hasChecksum) return;
    await navigator.clipboard.writeText(release.checksum);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  return <>
    <header className="nav wrap">
      <a href="#top" className="brand" aria-label="StockSight Learner home"><img className="brand-mark" src="/stocksight-logo.png" alt="" /> StockSight <em>Learner</em></a>
      <nav aria-label="Main navigation"><a href="#inside">Inside the app</a><a href="#features">Features</a><a href="#install">Install</a><a href="#support">Help</a></nav>
      <DownloadButton className="nav-download" />
    </header>

    <main id="top">
      <section className="hero wrap">
        <div className="hero-copy">
          <p className="eyebrow">A Windows desktop learning companion</p>
          <h1>Build market knowledge.<br /><span>Keep your footing.</span></h1>
          <p className="lede">StockSight Learner gives beginning investors a focused place to learn how markets move, practice with paper trading, and make sense of the terms behind every decision.</p>
          <div className="hero-actions"><DownloadButton /><a className="text-link" href="#inside">Explore the app <span aria-hidden="true">↓</span></a></div>
          <div className="hero-meta"><span><b>Windows</b> desktop app</span><span><b>{release.version}</b> current release</span><span><b>{release.size}</b> download</span></div>
        </div>
        <figure className="hero-shot"><img src="/screenshots/dashboard.jpg" alt="StockSight Learner dashboard" /><figcaption>Real app screen · Preview Mode</figcaption></figure>
      </section>

      <section className="trust-strip"><div className="wrap"><span>Designed for learning</span><span>Paper-trading workspace</span><span>Built for Windows</span><span>Free GitHub releases</span></div></section>

      <section id="inside" className="screens wrap">
        <div className="section-heading"><div><p className="eyebrow">Inside StockSight Learner</p><h2>One workspace for your learning loop.</h2></div><p>Not another stream of noise. Each area of the app gives you context, a place to practice, and a clearer next question.</p></div>
        <div className="screen-list">{screenshots.map((screen, index) => <article className={`screen-row row-${index + 1}`} key={screen.src}><div className="screen-copy"><span className="number">0{index + 1}</span><h3>{screen.title}</h3><p>{screen.body}</p></div><figure><img src={screen.src} alt={screen.alt} /></figure></article>)}</div>
      </section>

      <section id="how-it-works" className="benefits"><div className="wrap"><p className="eyebrow">A calmer way to learn</p><h2>Start with context, not a hot take.</h2><div className="benefit-grid"><article><span className="number">01</span><h3>Learn the language</h3><p>Use guided modules, quizzes, and plain-language explanations to build a strong foundation.</p></article><article><span className="number">02</span><h3>Practice without pressure</h3><p>Explore paper-trading tools and observe what changes before putting real money at risk.</p></article><article><span className="number">03</span><h3>Review your thinking</h3><p>Use journals, portfolio insights, and risk tools to turn each session into a useful lesson.</p></article></div></div></section>

      <section id="features" className="feature-detail wrap"><div className="section-heading"><div><p className="eyebrow">More than a chart</p><h2>Tools that connect the dots.</h2></div><p>Every feature is built to help you slow down, understand what you are looking at, and build your own process over time.</p></div><div className="feature-grid"><article><span>◌</span><h3>Market workspace</h3><p>Follow a selected market, keep a watchlist, review quotes, and see a high-level picture before going deeper.</p><ul><li>Market overview</li><li>Watchlists and quotes</li><li>Portfolio snapshots</li></ul></article><article><span>↗</span><h3>Paper-trading practice</h3><p>Test ideas in a simulated environment and understand the mechanics of a trade without claiming real-world outcomes.</p><ul><li>Buy and sell practice</li><li>Trade history</li><li>Investment journal</li></ul></article><article><span>✦</span><h3>Learning and insight</h3><p>Use short modules, quizzes, risk tools, AI chat, and progress views to make each session more useful.</p><ul><li>Learning modules</li><li>Risk Lab and scenarios</li><li>AI learning conversations</li></ul></article><article><span>◎</span><h3>Reflect and improve</h3><p>Review your decisions, study portfolio insights, and set learning-oriented goals that fit your pace.</p><ul><li>Trade analytics</li><li>Portfolio insights</li><li>Weekly summary</li></ul></article></div></section>

      <section className="audience"><div className="wrap audience-grid"><div><p className="eyebrow">Built for the beginning</p><h2>Useful if you are curious, new, or rebuilding your basics.</h2></div><div className="audience-list"><p><b>You are new to markets.</b> Learn the vocabulary and see how common ideas connect.</p><p><b>You want to practice first.</b> Explore paper-trading tools before treating anything as a real decision.</p><p><b>You want a routine.</b> Use progress, notes, and review tools to make learning feel more intentional.</p></div></div></section>

      <section id="install" className="install"><div className="wrap install-grid"><div><p className="eyebrow">Ready when you are</p><h2>Install in three simple steps.</h2><p className="install-copy">The official download always lives on GitHub Releases, making it easy to find the newest version and confirm the file you are opening.</p><DownloadButton /></div><ol><li><span>1</span><div><strong>Open GitHub Releases</strong><p>Choose the latest StockSight Learner release and download the Windows `.exe` file.</p></div></li><li><span>2</span><div><strong>Open the downloaded file</strong><p>Find it in your Downloads folder and double-click to start the app.</p></div></li><li><span>3</span><div><strong>Follow the setup prompts</strong><p>Windows may show a security notice for an unsigned app. Verify the checksum below before choosing “More info” then “Run anyway.”</p></div></li></ol></div></section>

      <section className="verification wrap"><div><p className="eyebrow">Verify before you install</p><h2>Your download, checked.</h2><p>For extra reassurance, compare the file’s SHA-256 value with the official release checksum.</p><a className="text-link" href="https://github.com/kianjindal2010/stocksight-flow/releases" target="_blank" rel="noreferrer">Open GitHub Releases <span aria-hidden="true">↗</span></a></div><div className="checksum-card">{hasChecksum ? <><code>{release.checksum}</code><button type="button" onClick={copyChecksum}>{copied ? "Copied" : "Copy checksum"}</button></> : <p>The verified checksum is published on the GitHub Release page.</p>}</div></section>

      <section className="updates"><div className="wrap updates-grid"><div><p className="eyebrow">Updates made simple</p><h2>Always know where the newest app lives.</h2><p>Every official version is published on GitHub Releases. Check the release notes, download the newest Windows file, and keep the version that works best for you.</p></div><div className="release-card"><span className="number">CURRENT RELEASE</span><strong>{release.version}</strong><p>Windows · {release.size}</p><a href="https://github.com/kianjindal2010/stocksight-flow/releases" target="_blank" rel="noreferrer">View release notes <span aria-hidden="true">↗</span></a></div></div></section>

      <section id="support" className="support wrap"><div><p className="eyebrow">Need a hand?</p><h2>Simple help, without the runaround.</h2></div><div className="support-grid"><article><h3>Can’t find the download?</h3><p>Open the GitHub Releases page and choose the topmost release marked “Latest.”</p></article><article><h3>Windows blocked the file</h3><p>Check the SHA-256 value first. If it matches the release page, choose “More info” then “Run anyway.”</p></article><article><h3>Still stuck?</h3><p>Send a note to <a href="mailto:kian.jindal2010@gmail.com">kian.jindal2010@gmail.com</a> with a screenshot of the issue.</p></article></div></section>
    </main>

    <footer><div className="wrap footer-inner"><p className="brand"><img className="brand-mark" src="/stocksight-logo.png" alt="" /> StockSight <em>Learner</em></p><p>For educational purposes only. StockSight Learner does not provide investment advice, recommendations, or guarantees of performance. Investing involves risk.</p><a href="https://github.com/kianjindal2010/stocksight-flow/releases" target="_blank" rel="noreferrer">GitHub Releases</a></div></footer>
  </>;
}

createRoot(document.getElementById("root")).render(<App />);
