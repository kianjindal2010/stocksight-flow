import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { motion, useReducedMotion } from "motion/react";
import "./styles.css";

gsap.registerPlugin(ScrollTrigger);

const release = {
  url: import.meta.env.VITE_DOWNLOAD_URL?.trim() || "https://github.com/kianjindal2010/stocksight-flow/releases",
  version: import.meta.env.VITE_RELEASE_VERSION?.trim() || "v2.0.3",
  size: import.meta.env.VITE_FILE_SIZE?.trim() || "59.4 MB",
  checksum: import.meta.env.VITE_SHA256?.trim() || "54B04B7BD4D67A6B6FCDA7C8C383689ED734472B9A8D7E2A56DF23F720F5A6B2",
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
  { src: "/screenshots/ai-chat-final.jpg", alt: "StockSight Learner AI chat screen", title: "Ask better questions", body: "Explore market concepts in plain language and turn unfamiliar terms into a learning plan." },
  { src: "/screenshots/risk-lab.jpg", alt: "StockSight Learner risk lab screen", title: "See risk before acting", body: "Use guided tools to understand position size, uncertainty, and the trade-offs behind a decision." },
];

const proScreens = [
  { src: "/screenshots/pro-terminal-navigation.png", alt: "StockSight Pro dark terminal navigation", label: "Terminal navigation" },
  { src: "/screenshots/pro-global-media.png", alt: "StockSight Pro source-labelled global media panel", label: "Source-labelled context" },
  { src: "/screenshots/pro-ai-brief.png", alt: "StockSight Pro AI Research Brief", label: "AI research brief" },
];

function ProTerminalShowcase() {
  const reduceMotion = useReducedMotion();
  return <section className="pro-terminal-showcase" aria-labelledby="pro-terminal-title">
    <div className="pro-terminal-heading">
      <div><p className="eyebrow">Built like a research desk</p><h3 id="pro-terminal-title">A live workspace, not a long webpage.</h3></div>
      <p>Pro opens as a compact terminal: the shell appears immediately, then market intelligence fills each panel independently in the background.</p>
    </div>
    <div className="pro-terminal-cards">
      {proScreens.map((screen, index) => <motion.figure key={screen.src} className={`pro-terminal-card pro-terminal-card-${index + 1}`} initial={reduceMotion ? false : { opacity: 0, y: 28, rotateX: 5 }} whileInView={reduceMotion ? undefined : { opacity: 1, y: 0, rotateX: 0 }} whileHover={reduceMotion ? undefined : { y: -8, rotateY: index === 1 ? -2 : 2, scale: 1.015 }} viewport={{ once: true, amount: 0.25 }} transition={{ duration: 0.55, delay: index * 0.08, ease: [0.16, 1, 0.3, 1] }}>
        <div className="pro-terminal-bar"><span></span><span></span><span></span><b>{screen.label}</b></div>
        <img src={screen.src} alt={screen.alt} />
      </motion.figure>)}
    </div>
  </section>;
}

function App() {
  const [copied, setCopied] = useState(false);
  const pageRef = useRef(null);

  useEffect(() => {
    if (!pageRef.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return undefined;

    const tiltCleanups = [];
    const context = gsap.context(() => {
      const media = gsap.matchMedia();
      media.add("(min-width: 821px)", () => {
        gsap.fromTo(".hero-shot", { autoAlpha: 0, y: 64, rotationX: 8, rotationY: -10, scale: 0.93 }, { autoAlpha: 1, y: 0, rotationX: 0, rotationY: 0, scale: 1, duration: 1.05, ease: "power3.out" });

        gsap.utils.toArray(".screen-row").forEach((row) => {
          const figure = row.querySelector("figure");
          const copy = row.querySelector(".screen-copy");
          const reverse = row.classList.contains("row-2");
          gsap.from(figure, { y: 70, rotationX: 5, rotationY: reverse ? 7 : -7, autoAlpha: 0, duration: 0.8, ease: "power3.out", scrollTrigger: { trigger: row, start: "top 76%", once: true } });
          gsap.from(copy, { x: reverse ? 42 : -42, autoAlpha: 0, duration: 0.65, ease: "power2.out", scrollTrigger: { trigger: row, start: "top 76%", once: true } });
        });

        const gallery = document.querySelector(".feature-gallery");
        const chat = document.querySelector(".gallery-chat");
        const dashboard = document.querySelector(".gallery-dashboard");
        const copy = document.querySelector(".gallery-copy");
        if (gallery && chat && dashboard && copy) {
          gsap.timeline({ scrollTrigger: { trigger: gallery, start: "top top", end: "+=760", pin: true, scrub: 0.8, anticipatePin: 1 } })
            .fromTo(chat, { x: -82, y: 54, rotationY: 16, rotationX: 5, scale: 0.92 }, { x: -12, y: 0, rotationY: 3, rotationX: 0, scale: 1, ease: "none" }, 0)
            .fromTo(dashboard, { x: 76, y: -38, rotationY: -16, rotationX: -4, scale: 0.91 }, { x: 20, y: 0, rotationY: -4, rotationX: 0, scale: 1, ease: "none" }, 0)
            .fromTo(copy, { y: 34, rotationX: 5, autoAlpha: 0.4 }, { y: 0, rotationX: 0, autoAlpha: 1, ease: "none" }, 0.12);
        }

        gsap.utils.toArray(".interactive-shot").forEach((element) => {
          const rotateX = gsap.quickTo(element, "rotationX", { duration: 0.45, ease: "power3.out" });
          const rotateY = gsap.quickTo(element, "rotationY", { duration: 0.45, ease: "power3.out" });
          const onMove = (event) => {
            const bounds = element.getBoundingClientRect();
            rotateY(((event.clientX - bounds.left) / bounds.width - 0.5) * 7);
            rotateX(((event.clientY - bounds.top) / bounds.height - 0.5) * -7);
          };
          const onLeave = () => { rotateX(0); rotateY(0); };
          element.addEventListener("pointermove", onMove);
          element.addEventListener("pointerleave", onLeave);
          tiltCleanups.push(() => {
            element.removeEventListener("pointermove", onMove);
            element.removeEventListener("pointerleave", onLeave);
          });
        });
      });
      return () => media.revert();
    }, pageRef);

    return () => {
      tiltCleanups.forEach((cleanup) => cleanup());
      context.revert();
    };
  }, []);
  const copyChecksum = async () => {
    if (!hasChecksum) return;
    await navigator.clipboard.writeText(release.checksum);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  return <>
    <header className="nav wrap">
      <a href="#top" className="brand" aria-label="StockSight Learner home"><img className="brand-mark" src="/stocksight-logo.png" alt="" /> StockSight <em>Learner</em></a>
      <nav aria-label="Main navigation"><a href="#inside">Inside the app</a><a href="#pro-research">StockSight Pro</a><a href="#features">Features</a><a href="#install">Install</a><a href="#safe-install">Install safely</a><a href="#support">Help</a></nav>
      <DownloadButton className="nav-download" />
    </header>

    <main id="top" ref={pageRef}>
      <section className="hero wrap">
        <div className="hero-copy">
          <p className="eyebrow">A Windows desktop learning companion</p>
          <h1>Build market knowledge.<br /><span>Keep your footing.</span></h1>
          <p className="lede">StockSight Learner gives beginning investors a focused place to learn how markets move, practice with paper trading, and make sense of the terms behind every decision.</p>
          <div className="hero-actions"><DownloadButton /><a className="text-link" href="#inside">Explore the app <span aria-hidden="true">↓</span></a></div>
          <div className="hero-meta"><span><b>Windows</b> desktop app</span><span><b>{release.version}</b> current release</span><span><b>Flow + Pro</b> workspaces</span><span><b>{release.size}</b> download</span></div>
        </div>
        <figure className="hero-shot interactive-shot"><img src="/screenshots/dashboard.jpg" alt="StockSight Learner dashboard" /><figcaption>Real app screen · Preview Mode</figcaption></figure>
      </section>

      <section className="trust-strip"><div className="wrap"><span>Designed for learning</span><span>Paper-trading workspace</span><span>Source-labelled Pro research</span><span>Free GitHub releases</span></div></section>

      <section id="inside" className="screens wrap">
        <div className="section-heading"><div><p className="eyebrow">Inside StockSight Learner</p><h2>One workspace for your learning loop.</h2></div><p>Not another stream of noise. Each area of the app gives you context, a place to practice, and a clearer next question.</p></div>
        <div className="screen-list">{screenshots.map((screen, index) => <article className={`screen-row row-${index + 1}`} key={screen.src}><div className="screen-copy"><span className="number">0{index + 1}</span><h3>{screen.title}</h3><p>{screen.body}</p></div><figure className="interactive-shot"><img src={screen.src} alt={screen.alt} /></figure></article>)}</div>
      </section>

      <section id="how-it-works" className="benefits"><div className="wrap"><div className="benefit-heading"><div><p className="eyebrow">A calmer way to learn</p><h2>Start with context, not a hot take.</h2></div><p>Every part of StockSight is designed to help you pause, understand the moving pieces, and practise before making a real decision.</p></div><div className="benefit-stage"><div className="benefit-grid"><article><span className="number">01</span><h3>Learn the language</h3><p>Use guided modules, quizzes, and plain-language explanations to build a strong foundation.</p></article><article><span className="number">02</span><h3>Practice without pressure</h3><p>Explore paper-trading tools and observe what changes before putting real money at risk.</p></article><article><span className="number">03</span><h3>Review your thinking</h3><p>Use journals, portfolio insights, and risk tools to turn each session into a useful lesson.</p></article></div><figure className="benefit-shot"><img src="/screenshots/risk-lab.jpg" alt="StockSight Learner Risk Lab with risk score and diversification guidance" /><figcaption>Risk Lab · See the trade-offs before you act</figcaption></figure></div></div></section>

      <section id="features" className="feature-detail wrap"><div className="section-heading"><div><p className="eyebrow">More than a chart</p><h2>Tools that connect the dots.</h2></div><p>Every feature is built to help you slow down, understand what you are looking at, and build your own process over time.</p></div><div className="feature-gallery"><figure className="gallery-chat"><img src="/screenshots/ai-chat-final.jpg" alt="StockSight Learner AI Trading Coach Chat" /></figure><div className="gallery-copy"><p className="eyebrow">Ask, review, repeat</p><h3>A learning workspace that stays connected.</h3><p>Move from a market question to a paper trade, then use your notes and risk tools to review what you learned.</p></div><figure className="gallery-dashboard"><img src="/screenshots/dashboard.jpg" alt="StockSight Learner paper-trading dashboard" /></figure></div><div className="feature-grid"><article><span>◌</span><h3>Market workspace</h3><p>Follow a selected market, keep a watchlist, review quotes, and see a high-level picture before going deeper.</p><ul><li>Market overview</li><li>Watchlists and quotes</li><li>Portfolio snapshots</li></ul></article><article><span>↗</span><h3>Paper-trading practice</h3><p>Test ideas in a simulated environment and understand the mechanics of a trade without claiming real-world outcomes.</p><ul><li>Buy and sell practice</li><li>Trade history</li><li>Investment journal</li></ul></article><article><span>✦</span><h3>Learning and insight</h3><p>Use short modules, quizzes, risk tools, AI chat, and progress views to make each session more useful.</p><ul><li>Learning modules</li><li>Risk Lab and scenarios</li><li>AI learning conversations</li></ul></article><article><span>◎</span><h3>Reflect and improve</h3><p>Review your decisions, study portfolio insights, and set learning-oriented goals that fit your pace.</p><ul><li>Trade analytics</li><li>Portfolio insights</li><li>Weekly summary</li></ul></article></div></section>

      <section id="pro-research" className="pro-research"><div className="wrap"><div className="pro-research-heading"><div><p className="eyebrow">New in {release.version}</p><h2>StockSight Pro.<br /><span>Research with receipts.</span></h2></div><p>Pro is a separate workspace for deeper paper-trading research. It shares your account and portfolio with Flow, while keeping saved Pro notes, watchlists, and research records separate.</p></div><ProTerminalShowcase /><div className="pro-source-grid"><article><span className="pro-source-number">01</span><h3>Official company record</h3><p>SEC filings and Company Facts build a longer view of revenue, earnings, operating cash flow, debt, assets, liabilities, diluted EPS, and share count for supported US issuers.</p><small>SEC EDGAR · official source</small></article><article><span className="pro-source-number">02</span><h3>Market &amp; fundamentals</h3><p>Price history, 52-week positioning, corporate actions, valuation context, earnings history, and symbol-specific news help frame the research workspace.</p><small>Yahoo Finance + Alpha Vantage</small></article><article><span className="pro-source-number">03</span><h3>Macro &amp; labour context</h3><p>Fed funds, CPI, unemployment, Treasury yields, yield curve, and payroll context help place a company inside the broader economic environment.</p><small>FRED + US Bureau of Labor Statistics</small></article><article><span className="pro-source-number">04</span><h3>Broader attention, separated</h3><p>GDELT global-media links and, once approved, Reddit Community Pulse are visibly separate from verified evidence. They add context—not proof.</p><small>GDELT · Reddit pending approval</small></article></div><div className="pro-ai-story"><div><p className="eyebrow">Pro AI Copilot</p><h3>A decision that shows its homework.</h3><p>The AI Research Brief considers the available market, financial, filings, macro, news, portfolio, trade-history, journal, and saved-thesis data together. It then shows the evidence categories considered, missing data, bull and bear cases, catalysts, risks, and a paper-trade guardrail plan.</p></div><ol><li><b>Source-labelled inputs</b><span>Every supplied source reports its freshness or unavailable state.</span></li><li><b>Evidence-weighted stance</b><span>Official filings and company facts carry more weight than media attention.</span></li><li><b>Educational paper-trade plan</b><span>Entry trigger, size guardrail, invalidation, and review date—not a promise or real-money instruction.</span></li></ol></div><p className="pro-disclaimer"><b>Important:</b> StockSight Pro is educational and paper-trading focused. AI analysis is a research aid, not financial advice. Unverified community or media attention cannot independently change an AI stance.</p></div></section>

      <section className="audience"><div className="wrap audience-grid"><div><p className="eyebrow">Built for the beginning</p><h2>Useful if you are curious, new, or rebuilding your basics.</h2><figure className="audience-shot"><img src="/screenshots/dashboard.jpg" alt="StockSight Learner dashboard showing paper-trading progress" /></figure></div><div className="audience-list"><p><b>You are new to markets.</b> Learn the vocabulary and see how common ideas connect.</p><p><b>You want to practice first.</b> Explore paper-trading tools before treating anything as a real decision.</p><p><b>You want a routine.</b> Use progress, notes, and review tools to make learning feel more intentional.</p></div></div></section>

      <section id="install" className="install"><div className="wrap install-grid"><div><p className="eyebrow">Ready when you are</p><h2>Install in three simple steps.</h2><p className="install-copy">The official download always lives on GitHub Releases, making it easy to find the newest version and confirm the file you are opening.</p><DownloadButton /></div><ol><li><span>1</span><div><strong>Open GitHub Releases</strong><p>Choose the latest StockSight Learner release and download the Windows `.exe` file.</p></div></li><li><span>2</span><div><strong>Open the downloaded file</strong><p>Find it in your Downloads folder and double-click to start the app.</p></div></li><li><span>3</span><div><strong>Follow the setup prompts</strong><p>Windows may show a security notice for an unsigned app. Verify the checksum below before choosing “More info” then “Run anyway.”</p></div></li></ol></div></section>

      <section id="safe-install" className="safe-install"><div className="wrap"><div className="safe-heading"><div><p className="eyebrow">Downloading &amp; installing safely</p><h2>Know what you are opening.</h2></div><p>StockSight Learner is shared through its official GitHub Releases page. Follow these quick checks before opening any download.</p></div><div className="safe-steps"><article><span>01</span><h3>Open the official release</h3><p>Use the Download for Windows button on this page. It always opens the official StockSight GitHub Releases page.</p></article><article><span>02</span><h3>Choose the newest EXE</h3><p>Select the top release marked Latest, then download <code>StockSightLearner-Updated.exe</code>.</p></article><article><span>03</span><h3>Check the file</h3><p>Compare the file’s SHA-256 value with the checksum shown below and on the matching GitHub release.</p></article><article><span>04</span><h3>Handle the Windows notice</h3><p>Current releases are unsigned, so Windows may show “Windows protected your PC.” Only after the filename and checksum match, choose <b>More info</b>, then <b>Run anyway</b>.</p></article></div><aside className="smart-screen-note"><div aria-hidden="true">!</div><p><b>Why does Windows show this?</b> Microsoft SmartScreen is cautious with new or unsigned downloads. A future signed release will show StockSight’s verified publisher name; until then, always download only from this site or the official GitHub Releases page.</p></aside></div></section>

      <section className="verification wrap"><div><p className="eyebrow">Verify before you install</p><h2>Your download, checked.</h2><p>For extra reassurance, compare the file’s SHA-256 value with the official release checksum.</p><a className="text-link" href="https://github.com/kianjindal2010/stocksight-flow/releases" target="_blank" rel="noreferrer">Open GitHub Releases <span aria-hidden="true">↗</span></a></div><div className="checksum-card">{hasChecksum ? <><code>{release.checksum}</code><button type="button" onClick={copyChecksum}>{copied ? "Copied" : "Copy checksum"}</button></> : <p>The verified checksum is published on the GitHub Release page.</p>}</div></section>

      <section className="updates"><div className="wrap updates-grid"><div><p className="eyebrow">Updates made simple</p><h2>Always know where the newest app lives.</h2><p>Every official version is published on GitHub Releases. Check the release notes, download the newest Windows file, and keep the version that works best for you.</p></div><div className="release-card"><img src="/screenshots/ai-chat-final.jpg" alt="StockSight Learner AI chat screen" /><div><span className="number">CURRENT RELEASE</span><strong>{release.version}</strong><p>Windows · {release.size}</p><a href="https://github.com/kianjindal2010/stocksight-flow/releases" target="_blank" rel="noreferrer">View release notes <span aria-hidden="true">↗</span></a></div></div></div></section>

      <section id="support" className="support wrap"><div><p className="eyebrow">Need a hand?</p><h2>Simple help, without the runaround.</h2></div><div className="support-grid"><article><h3>Can’t find the download?</h3><p>Open the GitHub Releases page and choose the topmost release marked “Latest.”</p></article><article><h3>Windows blocked the file</h3><p>Check the SHA-256 value first. If it matches the release page, choose “More info” then “Run anyway.”</p></article><article><h3>Still stuck?</h3><p>Send a note to <a href="mailto:kian.jindal2010@gmail.com">kian.jindal2010@gmail.com</a> with a screenshot of the issue.</p></article></div></section>
    </main>

    <footer><div className="wrap footer-inner"><p className="brand"><img className="brand-mark" src="/stocksight-logo.png" alt="" /> StockSight <em>Learner</em></p><p>For educational purposes only. StockSight Learner does not provide investment advice, recommendations, or guarantees of performance. Investing involves risk.</p><a href="https://github.com/kianjindal2010/stocksight-flow/releases" target="_blank" rel="noreferrer">GitHub Releases</a></div></footer>
  </>;
}

createRoot(document.getElementById("root")).render(<App />);
