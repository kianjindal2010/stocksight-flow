import { createRoot } from "react-dom/client";
import "./styles.css";

const releasesUrl = "https://github.com/kianjindal2010/stocksight-flow/releases";
const latestReleaseUrl = `${releasesUrl}/latest`;

function DownloadButton({ className = "" }) {
  return <a className={`button button-primary ${className}`} href={latestReleaseUrl} target="_blank" rel="noreferrer">Download for Windows <span aria-hidden="true">↗</span></a>;
}

const screenshots = [
  { src: "/screenshots/dashboard.jpg", alt: "StockSight Learner dashboard with paper-trading portfolio data", title: "Dashboard", body: "See your watchlist, portfolio, and learning progress." },
  { src: "/screenshots/ai-chat.jpg", alt: "StockSight Learner AI chat screen", title: "AI Coach", body: "Ask about market terms and paper trades." },
  { src: "/screenshots/risk-lab.jpg", alt: "StockSight Learner risk lab screen", title: "Risk Lab", body: "See how position size affects the risk of a simulated trade." },
];

function App() {
  return <>
    <header className="nav wrap">
      <a href="#top" className="brand" aria-label="StockSight Learner home"><img className="brand-mark" src="/stocksight-logo.png" alt="" /> StockSight <em>Learner</em></a>
      <nav aria-label="Main navigation"><a href="#inside">Inside the app</a><a href="#features">Features</a><a href="#install">Install</a><a href="#support">Help</a></nav>
      <DownloadButton className="nav-download" />
    </header>

    <main id="top">
      <section className="hero wrap">
        <div className="hero-copy">
          <h1>Learn about stocks and practice trading</h1>
          <p className="lede">StockSight Learner is a Windows app with market lessons, a simulated portfolio, and tools for reviewing your trades.</p>
          <div className="hero-actions"><DownloadButton /><a className="text-link" href="#inside">Explore the app <span aria-hidden="true">↓</span></a></div>
        </div>
        <figure className="hero-shot"><img src="/screenshots/dashboard.jpg" alt="StockSight Learner dashboard" /><figcaption>Dashboard in preview mode</figcaption></figure>
      </section>

      <section id="inside" className="screens wrap">
        <div className="section-heading"><h2>Inside the app</h2></div>
        <div className="screen-list">{screenshots.map((screen, index) => <article className={`screen-row row-${index + 1}`} key={screen.src}><div className="screen-copy"><h3>{screen.title}</h3><p>{screen.body}</p></div><figure><img src={screen.src} alt={screen.alt} /></figure></article>)}</div>
      </section>

      <section id="features" className="feature-detail wrap">
        <div className="section-heading"><h2>Features</h2></div>
        <div className="feature-grid">
          <article><h3>Markets</h3><p>Check quotes, follow stocks on a watchlist, and review your portfolio.</p></article>
          <article><h3>Paper trading</h3><p>Place simulated orders and record what you learned in a trade journal.</p></article>
          <article><h3>Lessons and risk</h3><p>Take quizzes, ask the AI Coach about market terms, and explore position sizing in the Risk Lab.</p></article>
          <article><h3>Progress</h3><p>Review your trade history, portfolio performance, and weekly summary.</p></article>
        </div>
      </section>

      <section id="install" className="install">
        <div className="wrap install-grid">
          <div><h2>Install on Windows</h2><DownloadButton /></div>
          <ol>
            <li><span>1</span><div><strong>Download the installer</strong><p>Open the latest GitHub release and download StockSightLearner-Updated.exe under Assets.</p></div></li>
            <li><span>2</span><div><strong>Check the download</strong><p>Compare the file's SHA-256 checksum with the checksum GitHub lists for the installer. Windows may warn that the installer is unsigned.</p></div></li>
            <li><span>3</span><div><strong>Start StockSight</strong><p>Open the verified file from your Downloads folder.</p></div></li>
          </ol>
        </div>
      </section>

      <section id="support" className="support wrap">
        <div><h2>Help</h2></div>
        <p>Email <a href="mailto:kian.jindal2010@gmail.com">kian.jindal2010@gmail.com</a> with a screenshot, your Windows version, and what you were doing when the issue occurred.</p>
      </section>
    </main>

    <footer><div className="wrap footer-inner"><p className="brand"><img className="brand-mark" src="/stocksight-logo.png" alt="" /> StockSight <em>Learner</em></p><p>For educational purposes only. StockSight Learner does not provide investment advice, recommendations, or guarantees of performance. Investing involves risk.</p><a href="https://github.com/kianjindal2010/stocksight-flow/releases" target="_blank" rel="noreferrer">GitHub Releases</a></div></footer>
  </>;
}

createRoot(document.getElementById("root")).render(<App />);
