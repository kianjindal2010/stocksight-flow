import { createRoot } from "react-dom/client";
import "./styles.css";

const releasesUrl = "https://github.com/kianjindal2010/stocksight-flow/releases";
const supportEmail = "kian.jindal2010@gmail.com";

const features = [
  {
    title: "Paper trading",
    copy: "Follow stocks on a watchlist, place simulated buy and sell orders, and see how they affect your portfolio. Use the trade journal to record why you made each trade.",
    image: "dashboard.jpg",
    alt: "StockSight dashboard with market and paper portfolio information",
  },
  {
    title: "Lessons and AI Coach",
    copy: "Work through lessons and quizzes on market basics. Ask the AI Coach to explain a term or help you review the thinking behind a paper trade.",
    image: "ai-chat-final.jpg",
    alt: "StockSight AI Coach conversation",
  },
  {
    title: "Risk Lab",
    copy: "Try different position sizes in a simulated portfolio and see how your exposure changes. Review trade history and portfolio performance as you practice.",
    image: "risk-lab.jpg",
    alt: "StockSight Risk Lab showing position sizing tools",
  },
];

function App() {
  return (
    <>
      <header className="wrap site-header">
        <a className="brand" href="./">StockSight Learner</a>
        <nav aria-label="Site navigation">
          <a href="#features">Features</a>
          <a href="#install">Install</a>
          <a href={releasesUrl}>Release notes</a>
        </nav>
      </header>

      <main className="wrap">
        <section className="intro" aria-labelledby="page-title">
          <h1 id="page-title">Learn about stocks.<br />Practice with paper trades.</h1>
          <p>StockSight Learner is a free Windows app for beginners. Follow stocks, place simulated orders, and review your trades without using real money.</p>
          <a className="download" href={releasesUrl + "/latest"}>Download for Windows</a>
          <a className="secondary" href="#features">Explore features</a>
        </section>

        <section id="features" className="features" aria-labelledby="features-title">
          <h2 id="features-title">Features</h2>
          {features.map(({ title, copy, image, alt }) => (
            <article className="feature" key={title}>
              <div>
                <h3>{title}</h3>
                <p>{copy}</p>
              </div>
              <img src={"/screenshots/" + image} alt={alt} loading={image === "dashboard.jpg" ? "eager" : "lazy"} />
            </article>
          ))}
          <article className="feature pro">
            <div>
              <h3>StockSight Pro</h3>
              <p>A separate research workspace with its own watchlist and saved research notes.</p>
            </div>
            <ul>
              <li>Look up company financials and SEC filings.</li>
              <li>Follow economic data, news, and upcoming company events.</li>
              <li>Generate research briefs that show the sources used and flag missing data.</li>
            </ul>
          </article>
        </section>

        <div className="details">
          <section id="install">
            <h2>Install on Windows</h2>
            <ol>
              <li>Open the <a href={releasesUrl + "/latest"}>latest release</a> and download <strong>StockSightLearner-Updated.exe</strong> under Assets.</li>
              <li>Compare the file's SHA-256 checksum with the one shown for the installer. Windows may warn that the file is unsigned.</li>
              <li>Open the verified file from your Downloads folder.</li>
            </ol>
          </section>
          <section id="support">
            <h2>Help</h2>
            <p>If you have trouble installing or using StockSight, <a href={"mailto:" + supportEmail}>email support</a> with a screenshot, your Windows version, and what happened.</p>
          </section>
        </div>
      </main>

      <footer className="wrap site-footer">
        <p>For education and paper trading only.</p>
        <a href={"mailto:" + supportEmail}>Email support</a>
      </footer>
    </>
  );
}

createRoot(document.getElementById("root")).render(<App />);
