(() => {
  const glossary = {
    'total portfolio value': 'The current value of everything you own: cash plus all open positions.',
    'portfolio value': 'The current value of your holdings plus cash.',
    'return (today)': 'How much your portfolio moved today as a percent.',
    'return today': 'How much your portfolio moved today as a percent.',
    'return (total)': 'Your overall performance since you started, in percent.',
    'return total': 'Your overall performance since you started, in percent.',
    'market value': 'What your shares are worth right now at the latest price.',
    'cost basis': 'What you paid for the shares you own (average cost).',
    'avg price': 'Your average purchase price per share.',
    'average price': 'Your average purchase price per share.',
    'wac': 'Weighted average cost: your average price per share.',
    'profit/loss': 'How much you are up or down on a position or trade.',
    'p/l': 'How much you are up or down on a position or trade.',
    'shares': 'How many shares you own or are trading.',
    'day change': 'How much the price moved today as a percent.',
    "day's change": 'How much the price moved today as a percent.',
    'cash': 'Uninvested money available to trade.',
    'equity': 'The value of your open positions.',
    'equity curve': 'Your portfolio value over time after each trade.',
    'drawdown': 'The drop from a peak value to a lower value.',
    'max drawdown': 'The biggest peak-to-trough drop in your equity curve.',
    'win rate': 'Percent of trades that were profitable.',
    'profit factor': 'Total gains divided by total losses.',
    'expectancy': 'Average profit/loss per trade based on history.',
    'average win': 'Average gain on winning trades.',
    'average loss': 'Average loss on losing trades.',
    'best trade': 'Your most profitable trade.',
    'worst trade': 'Your least profitable trade.',
    'avg return': 'Average percent return per trade.',
    'avg hold': 'Average number of days you held a trade.',
    'limit order': 'An order that fills only at your price or better.',
    'stop order': 'An order that activates when price crosses a trigger.',
    'dividend': 'Cash paid by a company to shareholders.',
    'split': 'A change in share count that keeps value the same.',
    'volatility': 'How much price moves up and down over time.',
    'rsi': 'Relative Strength Index: momentum indicator from 0-100.',
    'macd': 'Moving Average Convergence Divergence: momentum trend signal.',
    'vwap': 'Volume-Weighted Average Price: average price weighted by volume.',
    'ema': 'Exponential Moving Average: weighted moving average.',
    'bollinger bands': 'Bands that show price volatility around a moving average.',
    'bollinger bandwidth': 'How wide the Bollinger Bands are; higher means more volatility.',
    'beta': 'How sensitive a stock is to market moves.',
    'rolling beta': 'Beta calculated over a moving window vs the market index.',
    'correlation': 'How closely two series move together; 1 = together, -1 = opposite.',
    'rolling correlation': 'Correlation over a moving window vs the market index.',
    'cumulative return': 'Total percent change since the start of the selected window.',
    'atr': 'Average True Range: typical price range used to gauge volatility.',
    'atr %': 'Average True Range as a percent of price.',
    'volume ratio': 'Current volume divided by its 20-period average.',
    'candlestick': 'Shows open, high, low, and close for each period as a candle.',
    'revenue': 'Total company sales over a period.',
    'earnings': 'Net income after expenses for a period.',
    'net income': 'Profit after all expenses, taxes, and interest.',
    'gross margin': 'Gross profit divided by revenue.',
    'operating margin': 'Operating income divided by revenue.',
    'profit margin': 'Net income divided by revenue.',
    'margins snapshot': 'Latest gross, operating, and profit margins.',
    'fundamentals': 'Financial performance metrics like revenue and earnings.',
    'industry outlook': 'Sector or industry performance compared with the broad market.',
    'market structure': 'Trend condition based on moving averages and price structure.',
    'support levels': 'Price zones where buyers historically step in.',
    'resistance levels': 'Price zones where sellers historically step in.',
    'volume profile': 'Where trading volume clustered across price levels.',
    'options positioning': 'Put/call ratios and open interest from the options market.',
    'risk controls': 'Suggested guardrails like stop loss and position sizing.',
    'stop loss level': 'Price level to exit if the trade moves against you.',
    'position size': 'Suggested number of shares based on risk per trade.',
    'max portfolio exposure': 'Maximum percent of your portfolio allocated to one position.',
    'walk-forward stability': 'How consistent model performance is across time splits.',
    'ai forecast': 'Experimental model that estimates possible future moves.',
    'risk lab': 'Risk analytics like volatility and drawdowns.',
    'market mood': 'A sentiment gauge from momentum and volatility.',
    'scenario simulator': 'A quick \"what-if\" tool for portfolio changes.',
    'screener': 'A filter to find stocks by price, volume, or momentum.',
    'portfolio insights': 'A breakdown of allocation, cash weight, and diversification.',
    'trade journal': 'Notes and tags you add to your trades.',
    'trade analytics': 'Stats that summarize your trading performance.',
    'weekly summary': 'A weekly digest of your portfolio and trades.',
    'alerts': 'Price triggers that notify you when a level is hit.',
    'subscription': 'Your paid plan that unlocks premium labs and analytics.',
    'plan': 'The tier that determines which features you can access.',
    'tier': 'A subscription level like Free, Beginner, or Enterprise.',
    'coupon': 'A code that can unlock premium features.',
    'redeem code': 'Enter a code to unlock premium access.',
    'pricing': 'Compare plan tiers, pricing, and what each includes.',
    'enterprise': 'Highest tier with full access and custom support.',
    'team': 'Plan for small groups sharing tools and insights.',
    'professional': 'Advanced tier with premium analytics and reports.',
    'advanced analytics': 'Premium insights like portfolio heatmaps, factor exposure, and stability checks.',
    'beginner': 'Entry-level paid tier with full labs access.',
    'free': 'Limited tier with Risk Lab access only.',
    'contact': 'Reach the StockSight team for support, pricing, or partnership questions.',
    'contact us': 'Reach the StockSight team for support, pricing, or partnership questions.',
    'team admin': 'Invite and manage teammates on the Team plan.',
    'team chat': 'Real-time chat for your team channels with online presence.',
    'appearance': 'Customize your theme mode and accent color.',
    'theme': 'Your chosen look-and-feel, including light/dark mode and accent color.',
    'accent color': 'The highlight color used across buttons, tabs, and accents.',
    'email verification': 'A confirmation link sent to your email to secure your account.',
  };

  const tooltip = document.createElement('div');
  tooltip.className = 'glossary-tooltip';
  document.body.appendChild(tooltip);

  let activeEl = null;
  let activeText = '';

  const normalize = (text) =>
    text
      .replace(/\s+/g, ' ')
      .replace(/[:*]+$/g, '')
      .replace(/[()]/g, '')
      .trim()
      .toLowerCase();

  const findMeaning = (el) => {
    if (!el) return null;
    if (el.dataset && el.dataset.meaning) return el.dataset.meaning;
    if (el.dataset && el.dataset.term) {
      const termKey = normalize(el.dataset.term);
      return glossary[termKey] || null;
    }
    const text = el.textContent || '';
    if (text.length < 2 || text.length > 60) return null;
    const key = normalize(text);
    return glossary[key] || null;
  };

  const findTarget = (node) => {
    if (!node) return null;
    return node.closest('[data-meaning], [data-term], .metric-label, .summary-label, .market-summary-title, th, label, .card-title, .chart-title, .card-header h2, .card-header h3');
  };

  const showTooltip = (text) => {
    tooltip.textContent = text;
    tooltip.classList.add('is-visible');
  };

  const hideTooltip = () => {
    tooltip.classList.remove('is-visible');
    activeEl = null;
    activeText = '';
  };

  document.addEventListener('mouseover', (event) => {
    const target = findTarget(event.target);
    if (!target) return;
    if (activeEl && (activeEl === target || activeEl.contains(target))) return;
    const meaning = findMeaning(target);
    if (!meaning) return;
    activeEl = target;
    activeText = meaning;
    showTooltip(meaning);
  });

  document.addEventListener('mouseout', (event) => {
    if (!activeEl) return;
    if (event.relatedTarget && activeEl.contains(event.relatedTarget)) return;
    hideTooltip();
  });

  document.addEventListener('mousemove', (event) => {
    if (!activeEl) return;
    const offset = 14;
    tooltip.style.left = `${event.clientX + offset}px`;
    tooltip.style.top = `${event.clientY + offset}px`;
    tooltip.setAttribute('aria-hidden', 'false');
  });
})();
