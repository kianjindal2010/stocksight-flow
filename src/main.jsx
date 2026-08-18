import { useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const release = {
  url: import.meta.env.VITE_DOWNLOAD_URL?.trim() ?? "",
  version: import.meta.env.VITE_RELEASE_VERSION?.trim() || "Latest release",
  size: import.meta.env.VITE_FILE_SIZE?.trim() || "108 MB",
  checksum: import.meta.env.VITE_SHA256?.trim() ?? "",
};

function validDownloadUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && /(^|\.)gofile\.io$/i.test(url.hostname);
  } catch {
    return false;
  }
}

const canDownload = validDownloadUrl(release.url);
const hasChecksum = /^[a-fA-F0-9]{64}$/.test(release.checksum);

function DownloadButton({ className = "" }) {
  if (!canDownload) return null;
  return <a className={`button button-primary ${className}`} href={release.url} target="_blank" rel="noreferrer">Download for Windows <span aria-hidden="true">→</span></a>;
}

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
      <a href="#top" className="brand" aria-label="StockSight Learner home"><span className="brand-mark">↗</span> StockSight <em>Learner</em></a>
      <nav aria-label="Main navigation"><a href="#how-it-works">How it works</a><a href="#install">Install</a><a href="#support">Help</a></nav>
      <DownloadButton className="nav-download" />
    </header>

    <main id="top">
      <section className="hero wrap">
        <div className="hero-copy">
          <p className="eyebrow">A Windows desktop learning companion</p>
          <h1>Learn the market.<br /><span>Keep your footing.</span></h1>
          <p className="lede">StockSight Learner helps beginning investors explore market concepts, follow price movements, and build a more informed routine — at your own pace.</p>
          <div className="hero-actions"><DownloadButton /><a className="text-link" href="#how-it-works">See what’s inside <span aria-hidden="true">↓</span></a></div>
          <p className="platform-note">Built for Windows · {release.version} · {release.size}</p>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="orb orb-a" /><div className="orb orb-b" />
          <div className="terminal"><div className="terminal-top"><i /><i /><i /><b>stocksight / learning view</b></div><div className="chart"><div className="chart-line" /><div className="chart-axis" /><div className="chart-label label-a">Market pulse</div><div className="chart-label label-b">Learn by observing</div></div><div className="metrics"><span>Watchlist<br /><strong>6 assets</strong></span><span>Learning streak<br /><strong>7 days</strong></span></div></div>
        </div>
      </section>

      <section id="how-it-works" className="benefits wrap">
        <div className="section-intro"><p className="eyebrow">Start where you are</p><h2>Less noise. More context.</h2></div>
        <div className="benefit-grid">
          <article><span className="number">01</span><h3>Explore the basics</h3><p>Build familiarity with market terms and the ideas behind everyday investing decisions.</p></article>
          <article><span className="number">02</span><h3>Observe real movement</h3><p>Use price data and market views as a learning prompt, not a signal to rush into a trade.</p></article>
          <article><span className="number">03</span><h3>Practice your process</h3><p>Turn curiosity into a calmer, more consistent way to learn about the market.</p></article>
        </div>
      </section>

      <section id="install" className="install"><div className="wrap install-grid"><div><p className="eyebrow">Ready when you are</p><h2>Install in three easy steps.</h2><p className="install-copy">Download the Windows app, open the file, and follow the setup prompts. It is that simple.</p><DownloadButton /></div><ol><li><span>1</span><div><strong>Download the app</strong><p>Use the secure download button. Your browser may ask you to confirm the download.</p></div></li><li><span>2</span><div><strong>Open the downloaded file</strong><p>Find StockSight Learner in your Downloads folder and double-click it to start.</p></div></li><li><span>3</span><div><strong>Follow the setup prompts</strong><p>Windows may show a security notice for an unsigned app. Choose “More info” then “Run anyway” only after verifying the file below.</p></div></li></ol></div></section>

      <section className="verification wrap"><div><p className="eyebrow">Verify before you install</p><h2>Your download, checked.</h2><p>For extra reassurance, compare the file’s SHA-256 value with the release checksum.</p></div><div className="checksum-card">{hasChecksum ? <><code>{release.checksum}</code><button type="button" onClick={copyChecksum}>{copied ? "Copied" : "Copy checksum"}</button></> : <p>The verified checksum will appear here with the next published release.</p>}</div></section>

      <section id="support" className="support wrap"><div><p className="eyebrow">Need a hand?</p><h2>Simple help, without the runaround.</h2></div><div className="support-grid"><article><h3>The download button isn’t showing</h3><p>The current release link has not been published yet. Please check back shortly or contact support.</p></article><article><h3>Windows blocked the file</h3><p>Verify the checksum first. If it matches, select “More info” in the Windows notice and then “Run anyway.”</p></article><article><h3>Still stuck?</h3><p>Send a note to <a href="mailto:kian.jindal2010@gmail.com">kian.jindal2010@gmail.com</a> with a screenshot of the issue.</p></article></div></section>
    </main>

    <footer><div className="wrap footer-inner"><p className="brand"><span className="brand-mark">↗</span> StockSight <em>Learner</em></p><p>For educational purposes only. StockSight Learner does not provide investment advice, recommendations, or guarantees of performance. Investing involves risk.</p><a href="mailto:kian.jindal2010@gmail.com">Contact support</a></div></footer>
  </>;
}

createRoot(document.getElementById("root")).render(<App />);
