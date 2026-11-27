(() => {
    const root = document.getElementById("stockReport");
    const indicators = window.StockSightIndicators;
    if (!root || !indicators) return;

    const find = (selector) => root.querySelector(selector);
    const number = indicators.finite;
    const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 });
    const money = (value, currency = "") => number(value) === null ? "—" :
        [currency, Number(value).toLocaleString("en", { maximumFractionDigits: 2 })].filter(Boolean).join(" ");
    const short = (value) => number(value) === null ? "—" : compact.format(Number(value));
    const text = (tag, value) => {
        const node = document.createElement(tag);
        node.textContent = value == null ? "" : String(value);
        return node;
    };
    const pairs = (target, rows) => {
        target.replaceChildren();
        rows.forEach(([label, value]) => {
            const row = text("div");
            row.append(text("dt", label), text("dd", value));
            target.append(row);
        });
    };
    const sectionLabels = { overview: "Quote & chart", technicals: "Indicators", ratios: "Fundamentals",
        events: "Events", evidence: "Evidence", notes: "Portfolio", score: "AI & score" };
    const statuses = {};
    const setStatus = (key, state, label) => {
        const node = find('[data-section-state="' + key + '"]');
        if (!node) return;
        node.textContent = label || state;
        node.parentElement.dataset.state = state;
        statuses[key] = state;
        const ready = Object.values(statuses).filter((value) => value === "available" || value === "partial").length;
        const loading = Object.values(statuses).filter((value) => value === "loading").length;
        find("[data-report-coverage]").textContent = ready + " of 7 sections have usable content" +
            (loading ? " · " + loading + " loading" : "") + ".";
    };
    Object.keys(sectionLabels).forEach((key) => setStatus(key, "loading", "Loading"));

    let quote = {};
    let history = {};
    let studyData = null;
    let period = 260;
    let chartMode = "line";
    const active = new Set(["sma20", "sma50", "volume"]);
    let plotlyReady = Boolean(window.Plotly);
    const last = (values) => values?.length ? number(values.at(-1)) : null;
    const fmt = (value, suffix = "") => number(value) === null ? "—" :
        Number(value).toLocaleString("en", { maximumFractionDigits: 2 }) + suffix;

    const reportStudies = () => {
        const closes = indicators.series(history.close);
        if (!closes.length) {
            find("[data-study-status]").textContent = "No daily history returned for this symbol.";
            find("[data-indicator-readouts]").replaceChildren();
            setStatus("technicals", "unavailable", "Unavailable");
            return;
        }
        studyData = indicators.calculate(history);
        const available = closes.filter((value) => value !== null).length;
        setStatus("technicals", available >= 14 ? "available" : "partial", available >= 14 ? "Ready" : "Short history");
        const latest = [
            ["SMA 20", last(studyData.sma20), "", "20 sessions"],
            ["SMA 50", last(studyData.sma50), "", "50 sessions"],
            ["SMA 200", last(studyData.sma200), "", "200 sessions"],
            ["EMA 12", last(studyData.ema12), "", "12 sessions"],
            ["EMA 26", last(studyData.ema26), "", "26 sessions"],
            ["Bollinger upper", last(studyData.bands.upper), "", "20 sessions"],
            ["Bollinger lower", last(studyData.bands.lower), "", "20 sessions"],
            ["RSI 14", last(studyData.rsi), "", "15 closes"],
            ["MACD", last(studyData.macd.line), "", "26 sessions"],
            ["MACD signal", last(studyData.macd.signal), "", "34 sessions"],
            ["ATR 14", last(studyData.atr), "", "14 sessions"],
        ];
        const grid = find("[data-indicator-readouts]");
        grid.replaceChildren();
        latest.forEach(([label, value, unit, minimum]) => {
            const card = text("div");
            card.append(text("small", label), text("strong", fmt(value, unit)), text("small", value === null ? "Needs " + minimum : "Latest session"));
            grid.append(card);
        });
        find("[data-study-status]").textContent = available + " daily closes available · indicators use the full history before the visible range is selected.";
    };

    const colors = () => {
        const css = getComputedStyle(root);
        return { ink: css.getPropertyValue("--desk-ink").trim() || "#e6eeeb",
            muted: css.getPropertyValue("--desk-muted").trim() || "#a8b9b3",
            line: css.getPropertyValue("--desk-line").trim() || "#344641",
            accent: css.getPropertyValue("--desk-accent").trim() || "#91d9bf" };
    };
    const plot = (target, traces, layout) => window.Plotly.react(target, traces, layout,
        { displayModeBar: false, responsive: true, scrollZoom: false });
    const redraw = () => {
        for (const key of ["rsi", "macd", "atr"]) {
            const pane = find('[data-study-pane="' + key + '"]');
            pane.hidden = !active.has(key);
            if (!pane.hidden && !plotlyReady) pane.querySelector("[data-study-chart]").textContent = "Interactive study chart unavailable; latest value is shown above.";
        }
        if (!studyData || !plotlyReady || !window.Plotly || !history.dates?.length) return;
        const count = Math.min(history.dates.length, history.close?.length || 0);
        if (!count) return;
        const start = Math.max(0, count - period);
        const dates = history.dates.slice(start, count);
        const selected = (values) => (values || []).slice(start, count);
        const c = colors();
        const base = chartMode === "candle" && ["open", "high", "low", "close"].every((key) => history[key]?.length >= count) ?
            { type: "candlestick", x: dates, open: selected(history.open), high: selected(history.high), low: selected(history.low), close: selected(history.close), name: "OHLC", increasing: { line: { color: "#72caa2" } }, decreasing: { line: { color: "#e98787" } } } :
            { type: "scatter", mode: "lines", x: dates, y: selected(history.close), name: "Close", line: { color: c.accent, width: 2.4 } };
        const traces = [base];
        const addLine = (key, label, color, dash = "solid") => {
            if (!active.has(key)) return;
            traces.push({ type: "scatter", mode: "lines", x: dates, y: selected(studyData[key]), name: label,
                line: { color, width: 1.55, dash }, connectgaps: false });
        };
        addLine("sma20", "SMA 20", "#f2ba70");
        addLine("sma50", "SMA 50", "#83baf0");
        addLine("sma200", "SMA 200", "#d7a3eb");
        addLine("ema12", "EMA 12", "#d8e38a", "dot");
        addLine("ema26", "EMA 26", "#e89f8c", "dot");
        if (active.has("bands")) {
            traces.push({ type: "scatter", mode: "lines", x: dates, y: selected(studyData.bands.upper), name: "Bollinger upper", line: { color: "#a29bed", width: 1, dash: "dash" }, connectgaps: false });
            traces.push({ type: "scatter", mode: "lines", x: dates, y: selected(studyData.bands.lower), name: "Bollinger lower", line: { color: "#a29bed", width: 1, dash: "dash" }, connectgaps: false });
        }
        if (active.has("volume") && history.volume?.length) traces.push({ type: "bar", x: dates, y: selected(history.volume), yaxis: "y2", name: "Volume", marker: { color: "rgba(129,199,171,.35)" }, opacity: .8 });
        const useVolume = active.has("volume") && history.volume?.length;
        const layout = { height: 410, margin: { l: 58, r: 24, t: 12, b: 42 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
            font: { color: c.muted, size: 11 }, hovermode: "x unified", showlegend: true,
            legend: { orientation: "h", x: 0, y: 1.13 },
            xaxis: { type: "date", showgrid: false, rangeslider: { visible: false } },
            yaxis: { domain: useVolume ? [.27, 1] : [0, 1], gridcolor: c.line, zeroline: false, title: quote.currency || "Price" },
            yaxis2: { domain: [0, .19], showgrid: false, zeroline: false, rangemode: "tozero", visible: Boolean(useVolume) } };
        const main = find("[data-advanced-chart]");
        main.hidden = false;
        Promise.resolve(plot(main, traces, layout)).then(() => {
            find("[data-chart-fallback]").hidden = true;
            find("[data-chart-caption]").textContent = "Drag to inspect a range; double-click to reset. Studies are calculated from full daily history.";
        }).catch(() => { main.hidden = true; find("[data-chart-fallback]").hidden = false; });
        for (const key of ["rsi", "macd", "atr"]) {
            const pane = find('[data-study-pane="' + key + '"]');
            pane.hidden = !active.has(key);
            if (pane.hidden) continue;
            const target = pane.querySelector("[data-study-chart]");
            const line = (values, name, color) => ({ type: "scatter", mode: "lines", x: dates, y: selected(values), name, line: { color, width: 1.8 }, connectgaps: false });
            let rows;
            if (key === "rsi") rows = [line(studyData.rsi, "RSI 14", "#d7a3eb")];
            else if (key === "atr") rows = [line(studyData.atr, "ATR 14", "#e89f8c")];
            else rows = [line(studyData.macd.line, "MACD", "#83baf0"), line(studyData.macd.signal, "Signal", "#f2ba70"),
                { type: "bar", x: dates, y: selected(studyData.macd.histogram), name: "Histogram", marker: { color: "#72caa280" } }];
            plot(target, rows, { height: 180, margin: { l: 48, r: 18, t: 8, b: 28 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
                font: { color: c.muted, size: 10 }, showlegend: key === "macd", legend: { orientation: "h", x: 0, y: 1.23 },
                xaxis: { type: "date", showgrid: false }, yaxis: { gridcolor: c.line, range: key === "rsi" ? [0, 100] : undefined } });
        }
    };
    const loadPlotly = () => {
        if (plotlyReady) return;
        const script = document.createElement("script");
        script.src = "https://cdn.plot.ly/plotly-2.32.0.min.js";
        script.async = true;
        script.onload = () => { plotlyReady = true; redraw(); };
        script.onerror = () => { find("[data-chart-caption]").textContent = "Interactive chart unavailable; daily close and volume remain visible below."; };
        document.head.append(script);
    };
    loadPlotly();

    root.querySelectorAll("[data-study]").forEach((button) => button.addEventListener("click", () => {
        if (active.has(button.dataset.study)) active.delete(button.dataset.study);
        else active.add(button.dataset.study);
        button.setAttribute("aria-pressed", String(active.has(button.dataset.study)));
        redraw();
    }));
    root.querySelectorAll("[data-chart-mode]").forEach((button) => button.addEventListener("click", () => {
        chartMode = button.dataset.chartMode;
        root.querySelectorAll("[data-chart-mode]").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
        redraw();
    }));
    root.querySelectorAll("[data-range]").forEach((button) => button.addEventListener("click", () => {
        period = Number(button.dataset.range);
        find("[data-chart-window]").textContent = "Showing up to " + button.textContent.trim() + " of daily history";
        redraw();
    }));

    const updateMarket = (data) => {
        if (data.quote) quote = { ...quote, ...data.quote, price: number(data.quote.price) > 0 ? data.quote.price : quote.price };
        if (data.history?.close?.length) history = data.history;
        const price = number(quote.price);
        const currency = quote.currency || "";
        find("[data-company-meta]").textContent = [quote.sector, quote.financial_currency ? "Reporting in " + quote.financial_currency : ""].filter(Boolean).join(" · ") || "Company details unavailable.";
        find("[data-company-summary]").textContent = quote.summary || "No company profile returned by the source.";
        pairs(find("[data-hero-stats]"), [
            ["Day range", number(quote.day_low) !== null && number(quote.day_high) !== null ? money(quote.day_low, currency) + " – " + money(quote.day_high, currency) : "—"],
            ["52-week range", number(quote.fifty_two_week_low) !== null && number(quote.fifty_two_week_high) !== null ? money(quote.fifty_two_week_low, currency) + " – " + money(quote.fifty_two_week_high, currency) : "—"],
            ["Market cap", number(quote.market_cap) === null ? "—" : currency + " " + short(quote.market_cap)],
            ["Volume", short(quote.volume)],
        ]);
        const low = number(quote.fifty_two_week_low), high = number(quote.fifty_two_week_high);
        if (price !== null && price > 0 && low !== null && high !== null && high > low) {
            const position = Math.max(0, Math.min(100, (price - low) / (high - low) * 100));
            find("[data-range-fill]").style.width = position.toFixed(1) + "%";
            find("[data-range-label]").textContent = "Price sits " + position.toFixed(0) + "% of the way from the 52-week low to high.";
        }
        setStatus("overview", price > 0 || history.close?.length ? "available" : "unavailable", price > 0 || history.close?.length ? "Ready" : "Unavailable");
        if (history.close?.length) { reportStudies(); redraw(); }
        else if (!studyData) reportStudies();
        const risk = data.risk || {};
        const forecast = data.forecast || {};
        const benchmark = data.benchmark || {};
        const mood = data.market_mood || {};
        pairs(find("[data-context-stats]"), [
            ["Risk", risk.volatility_level || (number(risk.risk_score) !== null ? "Score " + risk.risk_score + "/100" : "—")],
            ["Trend forecast", forecast.direction || "—"],
            ["Benchmark", [benchmark.label || benchmark.name || benchmark.symbol, number(benchmark.change_pct) === null ? "" : fmt(benchmark.change_pct, "%")].filter(Boolean).join(" · ") || "—"],
            ["Market mood", mood.classification || "—"],
        ]);
        find("[data-context-note]").textContent = [forecast.simple_reason, risk.max_loss_warning].filter(Boolean).join(" · ") || "Further context appears when research sources load.";
    };
    const updateResearch = (data) => {
        const hasRatios = Boolean(Object.keys(data.resolved_ratios || {}).length || Object.keys(data.quote?.ratios || {}).length);
        const hasFinancials = Boolean(data.company_facts?.metrics?.length || data.provider_financials?.length || Object.keys(data.fundamentals || {}).length);
        setStatus("ratios", hasRatios || hasFinancials ? "available" : "partial", hasRatios || hasFinancials ? "Ready" : "Limited data");
        const hasEvents = Boolean(data.earnings?.upcoming?.length || data.actions?.dividends?.length || data.actions?.splits?.length || data.ownership?.insiders?.length);
        setStatus("events", hasEvents ? "available" : "partial", hasEvents ? "Ready" : "Limited data");
        const hasEvidence = Boolean(data.filings?.length || data.news?.length || data.macro?.fred?.length || data.macro?.bls?.length);
        setStatus("evidence", hasEvidence ? "available" : "partial", hasEvidence ? "Ready" : "Limited data");
        const hasPosition = Boolean(data.personal_context?.position);
        setStatus("notes", hasPosition ? "available" : "partial", hasPosition ? "Position loaded" : "Notes ready");
        setStatus("score", "partial", "Actions ready");
    };
    const searchInput = find("#proReportSearch");
    const searchResults = find("[data-search-results]");
    let searchTimer;
    let matches = [];
    searchInput.addEventListener("input", () => {
        clearTimeout(searchTimer);
        searchResults.hidden = true;
        matches = [];
        const query = searchInput.value.trim();
        if (query.length < 2) return;
        searchTimer = setTimeout(async () => {
            try {
                const response = await fetch("/api/search?q=" + encodeURIComponent(query) + "&limit=6", { credentials: "include" });
                if (!response.ok) return;
                const data = await response.json();
                if (searchInput.value.trim() !== query) return;
                matches = data.results || [];
                searchResults.replaceChildren();
                matches.forEach((row) => {
                    if (!row.symbol) return;
                    const link = text("a");
                    link.href = "/pro/stocks/" + encodeURIComponent(row.symbol);
                    link.append(text("strong", row.symbol), text("small", row.name || ""));
                    searchResults.append(link);
                });
                searchResults.hidden = !searchResults.children.length;
            } catch { searchResults.hidden = true; }
        }, 250);
    });
    document.addEventListener("click", (event) => { if (!find("[data-pro-search-form]").contains(event.target) && !searchResults.contains(event.target)) searchResults.hidden = true; });
    if ("IntersectionObserver" in window) {
        const observer = new IntersectionObserver((entries) => {
            const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
            if (!visible) return;
            root.querySelectorAll("[data-section-link]").forEach((link) => {
                if (link.dataset.sectionLink === visible.target.id) link.setAttribute("aria-current", "location");
                else link.removeAttribute("aria-current");
            });
        }, { rootMargin: "-80px 0px -55% 0px", threshold: [0, .25, .5] });
        Object.keys(sectionLabels).forEach((key) => { const section = find("#" + key); if (section) observer.observe(section); });
    }
    window.StockSightProAdvanced = { market: updateMarket, research: updateResearch, setStatus };
})();
