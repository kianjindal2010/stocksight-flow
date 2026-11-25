import { createRoot } from "react-dom/client";
import "./styles.css";

const releasesUrl = "https://github.com/kianjindal2010/stocksight-flow/releases";
const supportEmail = "kian.jindal2010@gmail.com";

function App() {
  return (
    <>
      <header className="wrap site-header">
        <a className="brand" href="./">StockSight Learner</a>
        <nav aria-label="Site navigation">
          <a href={releasesUrl}>Release notes</a>
          <a href="#install">Install</a>
        </nav>
      </header>

      <main className="wrap">
        <section className="intro" aria-labelledby="page-title">
          <h1 id="page-title">Learn about stocks.<br />Practice with paper trades.</h1>
          <p>StockSight Learner is a free Windows app for beginners. Follow stocks, place simulated orders, and review your trades without using real money.</p>
          <a className="download" href={releasesUrl + "/latest"}>Download for Windows</a>
          <a className="secondary" href="#install">Installation instructions</a>
        </section>

        <figure className="preview">
          <img src="/screenshots/dashboard.jpg" alt="StockSight dashboard showing the paper portfolio and market overview" />
          <figcaption>The StockSight dashboard in preview mode.</figcaption>
        </figure>

        <div className="details">
          <section>
            <h2>What you can do</h2>
            <ul>
              <li>Track stocks in a watchlist and practice buying and selling.</li>
              <li>Take short lessons and quizzes, or ask the AI Coach about market terms.</li>
              <li>Review your trade history, keep a journal, and try different position sizes in the Risk Lab.</li>
            </ul>
          </section>
          <section id="install">
            <h2>Install on Windows</h2>
            <ol>
              <li>Open the <a href={releasesUrl + "/latest"}>latest release</a> and download <strong>StockSightLearner-Updated.exe</strong> under Assets.</li>
              <li>Compare the file's SHA-256 checksum with the one shown for the installer. Windows may warn that the file is unsigned.</li>
              <li>Open the verified file from your Downloads folder.</li>
            </ol>
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
