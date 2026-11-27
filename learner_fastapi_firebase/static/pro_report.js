(() => {
    const report = document.getElementById("stockReport");
    if (!report) return;
    const endpoint = "/api/pro/stocks/" + encodeURIComponent(report.dataset.symbol);
    const find = (selector) => report.querySelector(selector);
    const formatDate = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
    const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 });
    const date = (value) => {
        const match = String(value || "").match(/^\d{4}-\d{2}-\d{2}/);
        if (!match) return value || "";
        const parsed = new Date(match[0] + "T00:00:00Z");
        return Number.isNaN(+parsed) ? value : formatDate.format(parsed);
    };
    const number = (value) => {
        if (typeof value !== "number" && (typeof value !== "string" || !value.trim())) return null;
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
    };
    const valueText = (value, unit = "") => value === null ? "-" : value.toLocaleString("en", { maximumFractionDigits: 2, minimumFractionDigits: 2 }) + unit;
    const element = (tag, text) => {
        const node = document.createElement(tag);
        if (text != null) node.textContent = text;
        return node;
    };
    const svgElement = (tag, attrs, text) => {
        const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
        for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
        if (text != null) node.textContent = text;
        return node;
    };
    const pairs = (target, entries) => {
        target.replaceChildren();
        for (const [label, value] of entries) {
            const row = element("div");
            row.append(element("dt", label), element("dd", value));
            target.append(row);
        }
    };
    const safeLink = (url) => typeof url === "string" && /^https?:\/\//i.test(url);
    const evidence = (key, rows, empty = "No data returned by the source.") => {
        const list = find('[data-evidence="' + key + '"]');
        list.replaceChildren();
        for (const [title, detail, url] of rows) {
            if (!title) continue;
            const item = element("li");
            if (safeLink(url)) {
                const link = element("a", title);
                link.href = url;
                link.target = "_blank";
                link.rel = "noopener";
                item.append(link);
            } else {
                item.append(element("span", title));
            }
            if (detail) item.append(element("small", detail));
            list.append(item);
        }
        if (!list.children.length) list.append(element("li", empty));
    };

    function chart(key, rows, { bars = false, unit = "" } = {}) {
        const figure = find('[data-chart="' + key + '"]');
        const svg = figure.querySelector("svg");
        const note = figure.querySelector("[data-chart-note]");
        const dates = figure.querySelector("[data-chart-dates]");
        const points = rows.map(([label, value], index) => ({ label, value: number(value), index }));
        const valid = points.filter((point) => point.value !== null);
        svg.replaceChildren();
        dates.replaceChildren();
        svg.toggleAttribute("hidden", !valid.length);
        if (!valid.length) {
            note.textContent = "Unavailable for this symbol.";
            return;
        }
        const nums = valid.map((point) => point.value);
        let low = Math.min(...nums, ...(bars ? [0] : []));
        let high = Math.max(...nums, ...(bars ? [0] : []));
        if (low === high) { low -= 1; high += 1; }
        const width = 451;
        const start = 59;
        const top = 14;
        const height = 136;
        const y = (value) => top + (high - value) * height / (high - low);
        const x = (index) => bars ? start + (index + 0.5) * width / points.length :
            start + (points.length === 1 ? width / 2 : index * width / (points.length - 1));
        const axis = (value) => compact.format(value);
        for (const value of [high, (high + low) / 2, low]) {
            svg.append(svgElement("line", { x1: start, x2: start + width, y1: y(value), y2: y(value), class: "report-grid-line" }));
            svg.append(svgElement("text", { x: start - 8, y: y(value) + 4, "text-anchor": "end" }, axis(value)));
        }
        if (bars) {
            const barWidth = Math.min(42, Math.max(1, width / points.length * 0.73));
            for (const point of valid) {
                const bar = svgElement("rect", { x: x(point.index) - barWidth / 2,
                    y: Math.min(y(0), y(point.value)), width: barWidth, height: Math.max(0.7, Math.abs(y(point.value) - y(0))), class: "report-bar" });
                bar.append(svgElement("title", {}, [point.label, valueText(point.value), unit].filter(Boolean).join(" ")));
                svg.append(bar);
            }
        } else {
            let path = "";
            let contiguous = false;
            for (const point of points) {
                if (point.value === null) { contiguous = false; continue; }
                path += (contiguous ? "L" : "M") + x(point.index) + "," + y(point.value);
                contiguous = true;
            }
            svg.append(svgElement("path", { d: path, class: "report-line", fill: "none", "vector-effect": "non-scaling-stroke" }));
            const end = valid.at(-1);
            svg.append(svgElement("circle", { cx: x(end.index), cy: y(end.value), r: 3, class: "report-bar" }));
        }
        const latest = valid.at(-1);
        note.textContent = [latest.label, valueText(latest.value), unit].filter(Boolean).join(" · ");
        const labels = points.length <= 6 ? points.map((row) => row.label) : [points[0].label, points.at(-1).label];
        dates.append(...labels.map((label) => element("span", label)));
    }

    let period = 260;
    let history = {};
    let quote = {};
    let resolvedRatios = {};
    let providerFundamentals = {};
    const charts = () => {
        const closes = history.close || [];
        const provision = (values) => closes.map((_, index) => [date(history.dates?.[index]), values[index]]).slice(-period);
        chart("price", provision(closes), { unit: quote.currency || "" });
        chart("volume", provision(history.volume || []), { bars: true, unit: "shares" });
        const selected = provision(closes);
        const first = number(selected.find(([, close]) => number(close) > 0)?.[1]);
        let peak = 0;
        chart("returns", selected.map(([day, close]) =>
            [day, first > 0 && number(close) > 0 ? (close / first - 1) * 100 : null]), { unit: "%" });
        chart("drawdown", selected.map(([day, close]) => {
            if (!(number(close) > 0)) return [day, null];
            peak = Math.max(peak, close);
            return [day, (close / peak - 1) * 100];
        }), { unit: "%" });
    };
    const ratioGroups = [
        ["Valuation", [["Trailing P/E", "trailing_pe", "×", "TrailingPE"], ["Annual-earnings P/E", "annual_pe", "×"], ["Forward P/E", "forward_pe", "×", "ForwardPE"], ["Price / book", "price_book", "×", "PriceToBookRatio"], ["Price / sales", "price_sales", "×", "PriceToSalesRatioTTM"], ["PEG", "peg", "×", "PEGRatio"], ["EV / EBITDA", "ev_ebitda", "×", "EVToEBITDA"], ["EV / revenue", "ev_revenue", "×", "EVToRevenue"]]],
        ["Profitability", [["Gross margin", "gross_margin", "%"], ["Operating margin", "operating_margin", "%", "OperatingMarginTTM", 100], ["Net margin", "profit_margin", "%", "ProfitMargin", 100], ["Return on equity", "roe", "%", "ReturnOnEquityTTM", 100], ["Return on assets", "roa", "%", "ReturnOnAssetsTTM", 100]]],
        ["Balance sheet & growth", [["Current ratio", "current_ratio", "×"], ["Quick ratio", "quick_ratio", "×"], ["Debt / equity", "debt_equity", "×"], ["Revenue growth", "revenue_growth", "%", "QuarterlyRevenueGrowthYOY", 100], ["Earnings growth", "earnings_growth", "%", "QuarterlyEarningsGrowthYOY", 100], ["Dividend yield", "dividend_yield_pct", "%", "DividendYield", 100]]],
    ];
    function ratios() {
        const root = find("[data-ratios]");
        root.replaceChildren();
        let filled = 0;
        for (const [heading, group] of ratioGroups) {
            const block = element("section");
            const table = element("dl");
            block.append(element("h4", heading), table);
            pairs(table, group.map(([label, key, unit, fallback, scale = 1]) => {
                const reported = resolvedRatios[key];
                const raw = number(reported?.value ?? quote.ratios?.[key] ?? quote[key]);
                const alternative = number(providerFundamentals[fallback]);
                const result = raw ?? (alternative === null ? null : alternative * scale);
                if (result !== null) filled++;
                const source = reported?.source || (raw !== null ? "Yahoo Finance" : "Alpha Vantage");
                return [label, result === null ? "-" : valueText(result, unit) + " · " + source];
            }));
            root.append(block);
        }
        find("[data-ratio-status]").textContent = filled ? "" : "No ratio inputs returned. A price quote can arrive before company financial data.";
    }
    function market(data) {
        if (data.quote) quote = { ...quote, ...data.quote, price: number(data.quote.price) > 0 ? data.quote.price : quote.price,
            ratios: { ...quote.ratios, ...data.quote.ratios } };
        resolvedRatios = { ...resolvedRatios, ...data.resolved_ratios };
        providerFundamentals = { ...providerFundamentals, ...data.fundamentals };
        if (data.history?.close?.length) history = data.history;
        const price = number(quote.price);
        const change = price > 0 ? number(quote.change_pct) : null;
        find("[data-company]").textContent = quote.name || "";
        find("[data-price]").textContent = price > 0 ? [quote.currency, valueText(price)].filter(Boolean).join(" ") : "Quote unavailable";
        find("[data-change]").textContent = change === null ? "" : (change > 0 ? "+" : "") + valueText(change, "%");
        find("[data-change]").className = change === null || change === 0 ? "" : change > 0 ? "performance-up" : "performance-down";
        find("[data-quote-note]").textContent = price > 0 ? "Yahoo Finance · latest available session" : "";
        pairs(find("[data-quote-stats]"), [
            ["Market cap", number(quote.market_cap) === null ? "-" : [quote.currency, compact.format(quote.market_cap)].filter(Boolean).join(" ")],
            ["Session volume", number(quote.volume) === null ? "-" : compact.format(quote.volume)],
            ["52-week low", valueText(number(quote.fifty_two_week_low))], ["52-week high", valueText(number(quote.fifty_two_week_high))],
            ["Sector", quote.sector || "-"], ["Beta", valueText(number(quote.beta))],
        ]);
        charts();
        ratios();
        window.StockSightProAdvanced?.market(data);
    }

    function financials(data) {
        const official = data.company_facts?.metrics || [];
        const fallback = data.provider_financials || [];
        const series = new Map(fallback.map((metric) => [metric.label, { ...metric, source: "Yahoo Finance" }]));
        for (const metric of official) series.set(metric.label, { ...metric, source: "SEC Company Facts" });
        const earnings = data.earnings?.annual || [];
        if (!series.has("Diluted EPS") && earnings.length) {
            series.set("Reported EPS", { label: "Reported EPS", unit: "per share", source: "Alpha Vantage", points: earnings.map((row) => ({
                end: row.fiscalDateEnding, value: row.reportedEPS,
            })).sort((a, b) => String(a.end).localeCompare(String(b.end))) });
        }
        const eps = series.get("Diluted EPS") || series.get("Reported EPS");
        find('[data-chart="eps"] figcaption').textContent = eps?.label === "Reported EPS" ? "Reported earnings per share" : "Diluted earnings per share";
        for (const [key, metric] of [["revenue", series.get("Revenue")], ["income", series.get("Net income")], ["cash", series.get("Operating cash flow")], ["eps", eps]]) {
            chart(key, (metric?.points || []).slice(-6).map((point) => [date(point.end || point.period), point.value]), { bars: true, unit: metric?.unit || "" });
        }
        find("[data-financial-source]").textContent = [
            ...new Set([...series.values()].map((metric) => metric.source)),
        ].filter(Boolean).join(" · ") || "Annual company figures are unavailable for this symbol.";
        const target = find("[data-financial-table]");
        target.replaceChildren();
        if (!series.size) return;
        const table = element("table");
        table.className = "table";
        const head = element("thead");
        const row = element("tr");
        for (const label of ["Reported figure", "Period end", "Value", "Unit", "Source"]) row.append(element("th", label));
        head.append(row);
        const body = element("tbody");
        for (const metric of series.values()) {
            const point = metric.points?.at(-1);
            if (!point) continue;
            const line = element("tr");
            for (const field of [metric.label, date(point.end || point.period), valueText(number(point.value)), metric.unit, metric.source]) line.append(element("td", field));
            body.append(line);
        }
        table.append(head, body);
        target.append(table);
    }

    async function fillMissingFinancials(data) {
        const available = new Set((data.company_facts?.metrics || []).map((metric) => metric.label));
        if (["Revenue", "Net income", "Operating cash flow", "Diluted EPS"].every((key) => available.has(key)) &&
            ["profit_margin", "current_ratio", "debt_equity"].every((key) => resolvedRatios[key])) return;
        const status = find("[data-financial-source]");
        const original = status.textContent;
        status.textContent = "Checking Yahoo Finance for missing annual figures.";
        try {
            const result = await read(endpoint + "/snapshot?view=financials");
            financials({ ...data, provider_financials: result.metrics || [] });
            resolvedRatios = { ...result.resolved_ratios, ...resolvedRatios };
            ratios();
        } catch {
            status.textContent = original;
        }
    }

    function research(data) {
        financials(data);
        const meta = (...items) => items.filter(Boolean).join(" · ");
        evidence("filings", (data.filings || []).slice(0, 8).map((row) => [row.title || row.form, meta(row.form, date(row.filed_at)), row.url]));
        evidence("news", (data.news || []).slice(0, 8).map((row) => [row.title, meta(row.source, date(row.published)), row.link]));
        evidence("events", [
            ...(data.earnings?.upcoming || []).map((row) => ["Expected earnings", date(row.date)]),
            ...(data.actions?.dividends || []).slice(0, 4).map((row) => ["Dividend", meta(date(row.date), valueText(number(row.amount)) + " per share")]),
            ...(data.actions?.splits || []).slice(0, 4).map((row) => ["Stock split", meta(date(row.date), String(row.ratio || ""))]),
        ]);
        const analysts = data.analyst_context || {};
        const target = analysts.price_target || {};
        evidence("analysts", [
            [target.targetLow != null && target.targetHigh != null ? "Price target range" : "", meta(valueText(number(target.targetLow)), valueText(number(target.targetHigh)))],
            [analysts.peers?.length ? "Peer tickers" : "", analysts.peers?.slice(0, 10).join(", ")],
        ]);
        evidence("ownership", [
            ...(data.ownership?.official_filings || []).slice(0, 4).map((row) => [row.title || row.form, date(row.filed_at), row.url]),
            ...(data.ownership?.insiders || []).slice(0, 4).map((row) => [row.name || row.type, meta(row.type, date(row.date))]),
        ]);
        evidence("macro", ["fred", "bls", "treasury"].flatMap((key) => (data.macro?.[key] || []).slice(0, 3)
            .map((row) => [row.label, meta(row.value, row.unit, date(row.date || row.period), { fred: "FRED", bls: "BLS", treasury: "US Treasury" }[key])])));
        evidence("context", [
            ...(data.global_media?.articles || []).slice(0, 5).map((row) => [row.title, meta(row.domain, date(row.published_at)), row.url]),
            ...(data.community?.posts || []).slice(0, 5).map((row) => [row.title, "Community discussion (unverified)", row.url]),
        ]);
        evidence("sources", (data.sources || []).map((row) => [row.name, meta(String(row.status || "").replaceAll("_", " "), row.freshness || row.detail)]));
        const position = data.personal_context?.position;
        find("[data-holdings]").textContent = position
            ? meta((position.quantity ?? position.shares) + " shares", "Average " + valueText(number(position.avg_price)), "Value " + valueText(number(position.market_value)))
            : "No open paper position for this ticker.";
        window.StockSightProAdvanced?.research(data);
    }

    const read = async (url) => {
        const response = await fetch(url, { credentials: "include" });
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || "Request unavailable.");
        }
        return response.json();
    };
    async function load(refresh = false) {
        const button = find("[data-report-refresh]");
        const status = find("[data-report-status]");
        button.disabled = true;
        status.textContent = "Loading market data and research sources.";
        let fullRendered = false;
        const fast = read(endpoint + "/snapshot?view=market").then((data) => {
            if (!fullRendered) market(data);
        }).catch(() => {});
        try {
            const data = await read(endpoint + "/snapshot" + (refresh ? "?refresh=1" : ""));
            fullRendered = true;
            market(data);
            research(data);
            fillMissingFinancials(data);
            status.textContent = "Research sources loaded. Check Sources for coverage.";
        } catch {
            await fast;
            research({});
            fillMissingFinancials({});
            status.textContent = "Extended research is unavailable. Available market values are shown above.";
        } finally {
            button.disabled = false;
        }
    }
    report.querySelectorAll("[data-range]").forEach((button) => button.addEventListener("click", () => {
        period = Number(button.dataset.range);
        report.querySelectorAll("[data-range]").forEach((option) => option.setAttribute("aria-pressed", String(option === button)));
        charts();
    }));
    const briefButtons = [...report.querySelectorAll("[data-pro-brief]")];
    briefButtons.forEach((button) => button.addEventListener("click", async () => {
        const output = find("[data-brief-output]");
        briefButtons.forEach((item) => { item.disabled = true; });
        output.textContent = "Generating research brief.";
        try {
            const brief = await read(endpoint + "/research-brief?action=" + encodeURIComponent(button.dataset.action));
            if (brief.source === "unavailable") throw new Error(brief.summary || "Hosted AI is unavailable.");
            output.replaceChildren(element("strong", brief.stance || "Research brief"), element("p", brief.summary || ""));
            for (const [label, rows] of [
                ["Evidence", brief.evidence_used], ["Missing data", brief.evidence_gaps],
                ["Bull case", brief.bull_case], ["Risks", [...(brief.bear_case || []), ...(brief.risks || [])]],
                ["Catalysts", brief.catalysts], ["What would change the view", brief.what_changes],
                ["Paper-trade plan", Object.values(brief.paper_trade_plan || {}).filter(Boolean)],
            ]) {
                if (!rows?.length) continue;
                const list = element("ul");
                list.append(...rows.map((row) => element("li", row)));
                output.append(element("h5", label), list);
            }
            window.StockSightProAdvanced?.setStatus("score", "available", "Brief ready");
        } catch (error) {
            output.textContent = error.message;
            window.StockSightProAdvanced?.setStatus("score", "partial", "AI unavailable");
        } finally {
            briefButtons.forEach((item) => { item.disabled = false; });
        }
    }));
    const scoreButton = find("[data-run-score]");
    scoreButton.addEventListener("click", async () => {
        const status = find("[data-score-status]");
        const factors = find("[data-score-factors]");
        const details = find("[data-sentiment-details]");
        scoreButton.disabled = true;
        status.textContent = "Scoring financial data, price history, and headlines.";
        try {
            const data = await read(endpoint + "/score");
            const result = data.score == null ? data.signal : data.signal + " · " + data.score + "/100";
            status.textContent = result + " · Data coverage " + data.coverage + "%";
            factors.replaceChildren();
            for (const row of data.factors || []) {
                const line = element("div");
                line.className = "report-factor";
                const measure = element("progress");
                measure.max = 100;
                measure.setAttribute("aria-label", row.label);
                if (row.score !== null) measure.value = row.score;
                else measure.hidden = true;
                line.append(element("span", row.label + " · " + row.weight + "% base weight"), measure,
                    element("strong", row.score === null ? "Unavailable" : row.score + "/100"));
                factors.append(line);
            }
            factors.append(element("p", data.method));
            const grades = find("[data-sentiment]");
            const rows = data.sentiment?.headlines || [];
            grades.replaceChildren();
            details.hidden = false;
            const labels = { company: "Company news", market: "Broad market", sec: "SEC headline" };
            grades.append(element("p", rows.length ? "Model: " + data.sentiment.source + " · Headline-only grades, -100 to +100." : "No model grades returned. Headline sentiment did not contribute."));
            for (const row of rows) {
                const article = element("article");
                article.className = "report-headline-grade";
                article.append(element("strong", labels[row.group] + " · " + (row.score > 0 ? "+" : "") + row.score),
                    element("p", row.title), element("small", [row.publisher, row.reason].filter(Boolean).join(" · ")));
                grades.append(article);
            }
            window.StockSightProAdvanced?.setStatus("score", data.score == null ? "partial" : "available", data.score == null ? "Limited score" : "Score ready");
        } catch (error) {
            status.textContent = error.message;
            window.StockSightProAdvanced?.setStatus("score", "partial", "Score unavailable");
        } finally {
            scoreButton.disabled = false;
        }
    });
    find("[data-report-refresh]").addEventListener("click", () => load(true));
    load();
})();
