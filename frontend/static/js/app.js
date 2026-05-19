/* ═══════════════════════════════════════════════════════════════════════════
   STAN — app.js
   Handles: candlestick chart, news markers, autocomplete, stocks table,
            news feed, auto-refresh, and the news detail panel.
   ═══════════════════════════════════════════════════════════════════════════ */
'use strict';

// ─── Global state ──────────────────────────────────────────────────────────
const S = {
  symbol:       null,      // currently selected ticker
  period:       '1d',
  chart:        null,
  candleSeries: null,
  volSeries:    null,
  markerMap:    new Map(), // Unix-ts (number) → marker object from API
  allStocks:    [],        // cached for autocomplete + table
  refreshTimer: null,
};

// ─── Lightweight Charts compat shim (v4 + v5) ──────────────────────────────
const LC = window.LightweightCharts;

function lcAddCandlestick(chart, opts) {
  // v5: chart.addSeries(CandlestickSeries, opts)
  // v4: chart.addCandlestickSeries(opts)
  if (typeof chart.addCandlestickSeries === 'function') {
    return chart.addCandlestickSeries(opts);
  }
  return chart.addSeries(LC.CandlestickSeries, opts);
}

function lcAddHistogram(chart, opts) {
  if (typeof chart.addHistogramSeries === 'function') {
    return chart.addHistogramSeries(opts);
  }
  return chart.addSeries(LC.HistogramSeries, opts);
}

function lcSetMarkers(series, markers) {
  // v5 uses createSeriesMarkers; v4 uses series.setMarkers
  if (typeof LC.createSeriesMarkers === 'function') {
    LC.createSeriesMarkers(series, markers);
  } else if (typeof series.setMarkers === 'function') {
    series.setMarkers(markers);
  }
}

// ─── Chart initialisation ───────────────────────────────────────────────────
function initChart() {
  const container = document.getElementById('chartContainer');

  S.chart = LC.createChart(container, {
    layout: {
      background:  { type: 'solid', color: '#0f1117' },
      textColor:   '#787b86',
    },
    grid: {
      vertLines: { color: '#1e2130' },
      horzLines: { color: '#1e2130' },
    },
    crosshair: {
      mode: LC.CrosshairMode ? LC.CrosshairMode.Normal : 1,
    },
    rightPriceScale: { borderColor: '#2a2e39' },
    timeScale: {
      borderColor:    '#2a2e39',
      timeVisible:    true,
      secondsVisible: false,
    },
    width:  container.clientWidth,
    height: 420,
  });

  S.candleSeries = lcAddCandlestick(S.chart, {
    upColor:      '#26a69a',
    downColor:    '#ef5350',
    borderVisible: false,
    wickUpColor:   '#26a69a',
    wickDownColor: '#ef5350',
  });

  S.volSeries = lcAddHistogram(S.chart, {
    color:       '#26a69a',
    priceFormat: { type: 'volume' },
    priceScaleId: 'volume',
    scaleMargins: { top: 0.85, bottom: 0 },
  });

  // OHLCV crosshair legend
  S.chart.subscribeCrosshairMove((params) => {
    if (!params || !params.seriesPrices) return;
    const price = params.seriesPrices.get(S.candleSeries);
    if (!price) return;
    const dir = price.close >= price.open ? 'up' : 'down';
    document.getElementById('chartLegend').innerHTML =
      `<span>O <b>${fmt(price.open)}</b></span>` +
      `<span>H <b>${fmt(price.high)}</b></span>` +
      `<span>L <b>${fmt(price.low)}</b></span>` +
      `<span>C <b class="${dir}">${fmt(price.close)}</b></span>`;
  });

  // Click handler — open news panel if a marker was near the click time
  S.chart.subscribeClick((params) => {
    if (!params || params.time == null) return;
    // Look for a marker within ±5 minutes of click time
    const t = params.time;
    let best = null;
    let bestDist = Infinity;
    for (const [ts, marker] of S.markerMap) {
      const dist = Math.abs(ts - t);
      if (dist < bestDist && dist < 300) { // 300 s = 5 min window
        bestDist = dist;
        best = marker;
      }
    }
    if (best) openNewsPanel(best);
  });

  // Responsive resize
  const ro = new ResizeObserver(() => {
    if (S.chart) S.chart.applyOptions({ width: container.clientWidth });
  });
  ro.observe(container);
}

const fmt = (v) => (v == null ? '–' : Number(v).toFixed(2));

// ─── Load + render chart data ────────────────────────────────────────────────
async function loadChart(symbol, period) {
  document.getElementById('chartPlaceholder').style.display = 'none';
  document.getElementById('chartContainer').style.display  = 'block';
  if (!S.chart) initChart();

  try {
    const [cRes, mRes] = await Promise.all([
      fetch(`/api/stocks/${encodeURIComponent(symbol)}/candles?period=${period}`),
      fetch(`/api/news/markers?symbol=${encodeURIComponent(symbol)}&period=${period}`),
    ]);

    if (!cRes.ok) throw new Error(`Candle fetch ${cRes.status}: ${symbol}`);

    const cData = await cRes.json();
    const mData = mRes.ok ? await mRes.json() : { markers: [] };

    const candles = cData.candles.filter(
      (c) => c.open != null && c.high != null && c.low != null && c.close != null,
    );

    S.candleSeries.setData(candles);

    // Volume histogram
    const vols = candles
      .filter((c) => c.volume != null)
      .map((c) => ({
        time:  c.time,
        value: c.volume,
        color: c.close >= c.open ? 'rgba(38,166,154,0.35)' : 'rgba(239,83,80,0.35)',
      }));
    S.volSeries.setData(vols);

    // Build marker map and apply to chart
    S.markerMap.clear();
    const markers = (mData.markers || []).map((m) => {
      S.markerMap.set(m.time, m);
      return { time: m.time, position: 'aboveBar', color: '#f68410', shape: 'circle', text: 'N' };
    });
    lcSetMarkers(S.candleSeries, markers);

    S.chart.timeScale().fitContent();
    updateStatus(true, `${symbol} · ${period.toUpperCase()}`);
  } catch (err) {
    console.error('Chart load error:', err);
    updateStatus(false, err.message);
  }
}

// ─── Incremental refresh (append latest candle) ──────────────────────────────
async function refreshChart() {
  if (!S.symbol || !S.chart) return;
  try {
    const res = await fetch(
      `/api/stocks/${encodeURIComponent(S.symbol)}/candles?period=${S.period}`,
    );
    if (!res.ok) return;
    const data = await res.json();
    const candles = data.candles.filter(
      (c) => c.open != null && c.high != null && c.low != null && c.close != null,
    );
    if (!candles.length) return;
    const last = candles[candles.length - 1];
    S.candleSeries.update(last);
    if (last.volume != null) {
      S.volSeries.update({
        time:  last.time,
        value: last.volume,
        color: last.close >= last.open ? 'rgba(38,166,154,0.35)' : 'rgba(239,83,80,0.35)',
      });
    }
    document.getElementById('lastUpdate').textContent =
      'Updated ' + new Date().toLocaleTimeString();
  } catch (err) {
    console.error('Chart refresh error:', err);
  }
}

// ─── Ticker autocomplete ─────────────────────────────────────────────────────
function setupTickerSearch() {
  const input = document.getElementById('tickerInput');
  const list  = document.getElementById('autocompleteList');

  input.addEventListener('input', () => {
    const q = input.value.trim().toUpperCase();
    if (!q) { list.hidden = true; return; }

    const hits = S.allStocks
      .filter((s) => s.symbol.startsWith(q) || (s.name || '').toUpperCase().includes(q))
      .slice(0, 8);

    if (!hits.length) { list.hidden = true; return; }

    list.innerHTML = hits
      .map(
        (s) =>
          `<li data-symbol="${escAttr(s.symbol)}">` +
          `<b>${escHtml(s.symbol)}</b> ` +
          `<span>${escHtml(s.name || '')}</span></li>`,
      )
      .join('');
    list.hidden = false;
  });

  list.addEventListener('click', (e) => {
    const li = e.target.closest('li[data-symbol]');
    if (li) selectSymbol(li.dataset.symbol);
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const q = input.value.trim().toUpperCase();
      if (q) selectSymbol(q);
    }
    if (e.key === 'Escape') list.hidden = true;
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('.ticker-search')) list.hidden = true;
  });
}

function selectSymbol(symbol) {
  S.symbol = symbol.toUpperCase();
  document.getElementById('tickerInput').value = S.symbol;
  document.getElementById('autocompleteList').hidden = true;
  loadChart(S.symbol, S.period);
}

// ─── Period buttons ───────────────────────────────────────────────────────────
function setupPeriodButtons() {
  document.querySelectorAll('.period-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.period-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      S.period = btn.dataset.period;
      if (S.symbol) loadChart(S.symbol, S.period);
    });
  });
}

// ─── News detail panel ────────────────────────────────────────────────────────
function openNewsPanel(article) {
  document.getElementById('newsPanelBody').innerHTML = `
    <div class="article-source">${escHtml(article.source || 'News')}</div>
    <h4 class="article-headline">${escHtml(article.headline || '')}</h4>
    <p class="article-desc">${escHtml(article.description || 'No summary available.')}</p>
    <a class="article-link" href="${escAttr(article.url)}" target="_blank" rel="noopener noreferrer">
      Read full article →
    </a>
  `;
  const panel = document.getElementById('newsPanel');
  panel.classList.add('open');
  panel.setAttribute('aria-hidden', 'false');
}

function closeNewsPanel() {
  const panel = document.getElementById('newsPanel');
  panel.classList.remove('open');
  panel.setAttribute('aria-hidden', 'true');
}

// ─── News feed ─────────────────────────────────────────────────────────────────
async function loadNewsFeed() {
  try {
    const res = await fetch('/api/news?limit=60');
    if (!res.ok) return;
    const data = await res.json();
    renderNewsFeed(data.items);
  } catch (err) {
    console.error('News feed error:', err);
  }
}

function renderNewsFeed(items) {
  const list = document.getElementById('newsList');
  if (!items || !items.length) {
    list.innerHTML = '<li class="placeholder-row">No news yet — collecting…</li>';
    return;
  }

  list.innerHTML = items
    .map(
      (a) => `
    <li class="news-item">
      <div class="news-meta">
        <span class="news-source">${escHtml(a.source || '')}</span>
        <span class="news-time">${relTime(a.published_at)}</span>
      </div>
      <a class="news-headline" href="${escAttr(a.url)}" target="_blank" rel="noopener noreferrer">
        ${escHtml(a.headline)}
      </a>
      ${
        a.tickers && a.tickers.length
          ? `<div class="news-tickers">${a.tickers
              .map((t) => `<span class="ticker-tag" data-symbol="${escAttr(t)}">${escHtml(t)}</span>`)
              .join('')}</div>`
          : ''
      }
    </li>`,
    )
    .join('');

  list.querySelectorAll('.ticker-tag').forEach((tag) => {
    tag.addEventListener('click', () => selectSymbol(tag.dataset.symbol));
  });
}

function relTime(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60)    return 'Just now';
  if (diff < 3600)  return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return new Date(iso).toLocaleDateString();
}

// ─── Stocks table ──────────────────────────────────────────────────────────────
async function loadStockList() {
  try {
    const res = await fetch('/api/stocks?limit=500');
    if (!res.ok) return;
    const data = await res.json();
    S.allStocks = data.items;
    renderStocksTable(data.items);
  } catch (err) {
    console.error('Stock list error:', err);
  }
}

function renderStocksTable(items) {
  const tbody = document.getElementById('stocksBody');
  if (!items || !items.length) {
    tbody.innerHTML =
      '<tr><td colspan="5" class="placeholder-row">No data yet — collecting…</td></tr>';
    return;
  }

  tbody.innerHTML = items
    .map((s) => {
      const chg     = s.change_pct;
      const cls     = chg == null ? '' : chg >= 0 ? 'up' : 'down';
      const chgStr  = chg == null ? '–' : (chg >= 0 ? '+' : '') + chg.toFixed(2) + '%';
      return `
      <tr class="stock-row" data-symbol="${escAttr(s.symbol)}">
        <td>${escHtml(s.symbol)}</td>
        <td class="name-cell">${escHtml(s.name || '–')}</td>
        <td>${s.close != null ? '$' + s.close.toFixed(2) : '–'}</td>
        <td class="${cls}">${chgStr}</td>
        <td>${s.volume != null ? fmtVol(s.volume) : '–'}</td>
      </tr>`;
    })
    .join('');

  tbody.querySelectorAll('.stock-row').forEach((row) => {
    row.addEventListener('click', () => selectSymbol(row.dataset.symbol));
  });
}

function fmtVol(v) {
  if (v >= 1e9) return (v / 1e9).toFixed(1) + 'B';
  if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
  if (v >= 1e3) return (v / 1e3).toFixed(0) + 'K';
  return String(Math.round(v));
}

// ─── Status bar ───────────────────────────────────────────────────────────────
function updateStatus(ok, msg) {
  document.getElementById('statusDot').className = 'status-dot ' + (ok ? 'ok' : 'error');
  document.getElementById('statusText').textContent = msg;
  document.getElementById('lastUpdate').textContent =
    'Updated ' + new Date().toLocaleTimeString();
}

// ─── XSS helpers ──────────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escAttr(s) {
  const str = String(s);
  // Only allow safe http/https URLs in href/data-* attributes
  if (/^(https?:\/\/|#|\/)/i.test(str) === false) return '#';
  return str.replace(/"/g, '%22').replace(/'/g, '%27');
}

// ─── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  // Wire up static UI handlers
  document.getElementById('closePanelBtn').addEventListener('click', closeNewsPanel);

  document.getElementById('newsSearch').addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase();
    document.querySelectorAll('.news-item').forEach((el) => {
      el.style.display = el.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
  });

  document.getElementById('stockSearch').addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase();
    document.querySelectorAll('.stock-row').forEach((el) => {
      el.style.display = el.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
  });

  setupTickerSearch();
  setupPeriodButtons();

  // Initial data load
  await Promise.all([loadStockList(), loadNewsFeed()]);
  updateStatus(true, 'Connected — waiting for first data…');

  // Auto-refresh every 60 s
  S.refreshTimer = setInterval(async () => {
    await Promise.all([refreshChart(), loadNewsFeed(), loadStockList()]);
    document.getElementById('lastUpdate').textContent =
      'Updated ' + new Date().toLocaleTimeString();
  }, 60_000);
});
