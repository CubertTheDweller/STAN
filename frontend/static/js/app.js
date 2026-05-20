/* ═══════════════════════════════════════════════════════════════════════════
   STAN — app.js
   Handles: candlestick chart, news markers, autocomplete, stocks table,
            news feed, auto-refresh, news detail panel, and all new features:
            favorites, category filters, light/dark theme, keyboard shortcuts,
            SMA overlays, volume spikes, comparison mode, impact sparklines,
            price alerts, sentiment badges, CSV export, trending tickers,
            sector heatmap, and WebSocket live push.
   ═══════════════════════════════════════════════════════════════════════════ */
'use strict';

// ─── Global state ───────────────────────────────────────────────────────────
const S = {
  symbol:           null,
  period:           '1d',
  mode:             'market',
  chart:            null,
  candleSeries:     null,
  volSeries:        null,
  overlayLineSeries: null,
  sp500LineSeries:  null,
  markerMap:        new Map(),
  allStocks:        [],
  refreshTimer:     null,
  candles:          [],
  smaLines:         {},
  compareSeries:    [],
  compareSymbols:   [],
  ws:               null,

  favorites:        new Set(JSON.parse(localStorage.getItem('stan_favorites')  || '[]')),
  hiddenCategories: new Set(JSON.parse(localStorage.getItem('stan_hidden_cats') || '[]')),
  activeSMAs:       new Set(JSON.parse(localStorage.getItem('stan_smas')        || '[]')),
  alerts:           JSON.parse(localStorage.getItem('stan_alerts') || '{}'),
};

// ─── Lightweight Charts compat shim (v4 + v5) ──────────────────────────────
const LC = window.LightweightCharts;

function lcAddCandlestick(chart, opts) {
  if (typeof chart.addCandlestickSeries === 'function') return chart.addCandlestickSeries(opts);
  return chart.addSeries(LC.CandlestickSeries, opts);
}
function lcAddHistogram(chart, opts) {
  if (typeof chart.addHistogramSeries === 'function') return chart.addHistogramSeries(opts);
  return chart.addSeries(LC.HistogramSeries, opts);
}
function lcAddLine(chart, opts) {
  if (typeof chart.addLineSeries === 'function') return chart.addLineSeries(opts);
  return chart.addSeries(LC.LineSeries, opts);
}
function lcSetMarkers(series, markers) {
  if (typeof LC.createSeriesMarkers === 'function') LC.createSeriesMarkers(series, markers);
  else if (typeof series.setMarkers === 'function') series.setMarkers(markers);
}

// ─── Theme helpers ───────────────────────────────────────────────────────────
function isDarkTheme() {
  return document.documentElement.dataset.theme !== 'light';
}

function applyThemeToChart() {
  if (!S.chart) return;
  const dark = isDarkTheme();
  S.chart.applyOptions({
    layout: {
      background: { type: 'solid', color: dark ? '#0f1117' : '#ffffff' },
      textColor:  dark ? '#787b86' : '#666',
    },
    grid: {
      vertLines: { color: dark ? '#1e2130' : '#e0e0e0' },
      horzLines: { color: dark ? '#1e2130' : '#e0e0e0' },
    },
  });
}

function toggleTheme() {
  const next = isDarkTheme() ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem('stan_theme', next);
  document.getElementById('themeToggle').textContent = next === 'light' ? '\u263e' : '\u2600';
  applyThemeToChart();
}

// ─── Chart initialisation ────────────────────────────────────────────────────
function initChart() {
  const container = document.getElementById('chartContainer');
  const dark = isDarkTheme();

  S.chart = LC.createChart(container, {
    layout: {
      background: { type: 'solid', color: dark ? '#0f1117' : '#ffffff' },
      textColor:  dark ? '#787b86' : '#666',
    },
    grid: {
      vertLines: { color: dark ? '#1e2130' : '#e0e0e0' },
      horzLines: { color: dark ? '#1e2130' : '#e0e0e0' },
    },
    crosshair: { mode: LC.CrosshairMode ? LC.CrosshairMode.Normal : 1 },
    leftPriceScale:  { visible: false, borderColor: dark ? '#2a2e39' : '#ccc' },
    rightPriceScale: { borderColor: dark ? '#2a2e39' : '#ccc' },
    timeScale: { borderColor: dark ? '#2a2e39' : '#ccc', timeVisible: true, secondsVisible: false },
    width:  container.clientWidth,
    height: 420,
  });

  S.candleSeries = lcAddCandlestick(S.chart, {
    upColor: '#26a69a', downColor: '#ef5350',
    borderVisible: false, wickUpColor: '#26a69a', wickDownColor: '#ef5350',
  });

  S.volSeries = lcAddHistogram(S.chart, {
    color: '#26a69a', priceFormat: { type: 'volume' },
    priceScaleId: 'volume', scaleMargins: { top: 0.85, bottom: 0 },
  });

  S.overlayLineSeries = lcAddLine(S.chart, {
    color: '#2196f3', lineWidth: 2, priceScaleId: 'left', title: 'NASDAQ %',
    lastValueVisible: true, priceLineVisible: false, crosshairMarkerVisible: true,
  });

  S.sp500LineSeries = lcAddLine(S.chart, {
    color: '#ff9800', lineWidth: 2, priceScaleId: 'left', title: 'S&P 500 %',
    lastValueVisible: true, priceLineVisible: false, crosshairMarkerVisible: true,
  });

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

  S.chart.subscribeClick((params) => {
    if (!params || params.time == null) return;
    const t = params.time;
    let best = null, bestDist = Infinity;
    for (const [ts, marker] of S.markerMap) {
      const dist = Math.abs(ts - t);
      if (dist < bestDist && dist < 300) { bestDist = dist; best = marker; }
    }
    if (best) openNewsPanel(best);
  });

  const ro = new ResizeObserver(() => {
    if (S.chart) S.chart.applyOptions({ width: container.clientWidth });
  });
  ro.observe(container);
}

const fmt = (v) => (v == null ? '\u2013' : Number(v).toFixed(2));

function snapToCandle(t, times) {
  if (!times.length) return t;
  let lo = 0, hi = times.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (times[mid] < t) lo = mid + 1; else hi = mid;
  }
  if (lo === 0) return times[0];
  const prev = times[lo - 1], next = times[lo];
  return (t - prev) <= (next - t) ? prev : next;
}

function clusterMarkers(markers, windowSecs = 600) {
  if (!markers.length) return [];
  const sorted = [...markers].sort((a, b) => a.time - b.time);
  const clusters = [];
  let group = [sorted[0]];
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i].time - group[0].time <= windowSecs) group.push(sorted[i]);
    else { clusters.push(group); group = [sorted[i]]; }
  }
  clusters.push(group);
  return clusters.map((grp) => {
    const freq = {};
    for (const m of grp) freq[m.category || 'general'] = (freq[m.category || 'general'] || 0) + 1;
    const majorCat = Object.entries(freq).sort((a, b) => b[1] - a[1])[0][0];
    const catDef = MARKER_CATEGORIES[majorCat] || MARKER_CATEGORIES.general;
    const mid = Math.floor(grp.length / 2);
    return { time: grp[mid].time, articles: grp, category: majorCat, color: catDef.color,
             text: grp.length > 1 ? String(grp.length) : catDef.key };
  });
}

// ─── News category definitions ───────────────────────────────────────────────
const MARKER_CATEGORIES = {
  fed:          { label: 'Fed / Rates',   color: '#ef5350', key: 'F' },
  earnings:     { label: 'Earnings',      color: '#26a69a', key: 'E' },
  economic:     { label: 'Economic Data', color: '#00bcd4', key: 'D' },
  tech:         { label: 'Technology',    color: '#2196f3', key: 'T' },
  geopolitical: { label: 'Geopolitical',  color: '#9c27b0', key: 'G' },
  energy:       { label: 'Energy',        color: '#ff9800', key: 'O' },
  merger:       { label: 'M&A',           color: '#e040fb', key: 'M' },
  general:      { label: 'General News',  color: '#9b9ea3', key: 'N' },
};

const SMA_COLORS = { 20: '#4fc3f7', 50: '#ffb74d', 200: '#ce93d8' };

// ─── Load + render chart data ────────────────────────────────────────────────
async function loadChart(symbol, period) {
  document.getElementById('chartPlaceholder').style.display = 'none';
  document.getElementById('chartContainer').style.display  = 'block';
  if (!S.chart) initChart();

  document.getElementById('smaBtns').hidden = false;
  document.getElementById('alertBtn').hidden = false;
  document.getElementById('exportCandlesBtn').hidden = false;
  renderAlertBadges();

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
    S.candles = candles;
    S.candleSeries.setData(candles);

    const vols = candles.filter((c) => c.volume != null).map((c) => ({
      time:  c.time,
      value: c.volume,
      color: c.volume_spike
        ? 'rgba(246,132,16,0.65)'
        : c.close >= c.open ? 'rgba(38,166,154,0.35)' : 'rgba(239,83,80,0.35)',
    }));
    S.volSeries.setData(vols);

    S.markerMap.clear();
    const markers = (mData.markers || [])
      .filter((m) => !S.hiddenCategories.has(m.category))
      .map((m) => {
        S.markerMap.set(m.time, m);
        const cat = MARKER_CATEGORIES[m.category] || MARKER_CATEGORIES.general;
        return { time: m.time, position: 'aboveBar', color: cat.color, shape: 'arrowDown', text: cat.key };
      });
    lcSetMarkers(S.candleSeries, markers);

    S.chart.timeScale().fitContent();

    if (candles.length) {
      const latest = candles[candles.length - 1];
      if (latest.change_pct != null) checkAlerts(symbol, latest.change_pct);
    }

    clearSMAOverlays();
    if (S.activeSMAs.size) await loadSMAOverlays(symbol, period);

    if (S.compareSeries.length) clearCompareMode();

    updateStatus(true, `${symbol} \u00b7 ${period.toUpperCase()}`);
  } catch (err) {
    console.error('Chart load error:', err);
    updateStatus(false, err.message);
  }
}

function normalizeToPercent(candles) {
  const valid = candles.filter((c) => c.close != null);
  if (!valid.length) return [];
  const base = valid[0].close;
  if (!base) return [];
  return valid.map((c) => ({ time: c.time, value: +((c.close - base) / base * 100).toFixed(3) }));
}

async function loadMarketChart(period) {
  S.mode   = 'market';
  S.symbol = null;
  document.getElementById('tickerInput').value = '';
  document.getElementById('chartPlaceholder').style.display = 'none';
  document.getElementById('chartContainer').style.display  = 'block';
  if (!S.chart) initChart();

  document.getElementById('smaBtns').hidden = true;
  document.getElementById('alertBtn').hidden = true;
  document.getElementById('exportCandlesBtn').hidden = true;
  document.getElementById('compareControls').hidden = true;
  document.getElementById('alertForm').hidden = true;
  clearSMAOverlays();
  clearCompareMode();

  document.getElementById('marketBtn').classList.add('active');
  document.getElementById('overlayBadge').hidden = false;
  S.chart.applyOptions({ leftPriceScale: { visible: true, borderColor: '#2a2e39' } });

  try {
    const enc = encodeURIComponent;
    const [nyaRes, ixicRes, gspcRes, mkrRes] = await Promise.all([
      fetch(`/api/stocks/${enc('^NYA')}/candles?period=${period}`),
      fetch(`/api/stocks/${enc('^IXIC')}/candles?period=${period}`),
      fetch(`/api/stocks/${enc('^GSPC')}/candles?period=${period}`),
      fetch(`/api/news/market-markers?period=${period}`),
    ]);
    if (!nyaRes.ok) throw new Error(`NYSE data unavailable (${nyaRes.status})`);

    const nyaData  = await nyaRes.json();
    const ixicData = ixicRes.ok ? await ixicRes.json() : null;
    const gspcData = gspcRes.ok ? await gspcRes.json() : null;
    const mData    = mkrRes.ok  ? await mkrRes.json()  : { markers: [] };

    const candles = nyaData.candles.filter(
      (c) => c.open != null && c.high != null && c.low != null && c.close != null,
    );
    S.candles = candles;
    S.candleSeries.setData(candles);

    const vols = candles.filter((c) => c.volume != null).map((c) => ({
      time:  c.time, value: c.volume,
      color: c.close >= c.open ? 'rgba(38,166,154,0.35)' : 'rgba(239,83,80,0.35)',
    }));
    S.volSeries.setData(vols);

    S.overlayLineSeries.setData(ixicData ? normalizeToPercent(ixicData.candles) : []);
    S.sp500LineSeries.setData(gspcData   ? normalizeToPercent(gspcData.candles)  : []);

    const candleTimes = candles.map((c) => c.time);
    S.markerMap.clear();
    const seenCategories = new Set();

    const allMarkers = mData.markers || [];
    allMarkers.forEach((m) => seenCategories.add(m.category || 'general'));

    const visibleMarkers = allMarkers.filter((m) => !S.hiddenCategories.has(m.category));
    const clusters = clusterMarkers(visibleMarkers, 600);
    const chartMarkers = clusters.map((cl) => {
      const snapped = snapToCandle(cl.time, candleTimes);
      S.markerMap.set(snapped, cl);
      return { time: snapped, position: 'aboveBar', color: cl.color, shape: 'arrowDown', text: cl.text };
    });
    lcSetMarkers(S.candleSeries, chartMarkers);
    renderMarkerLegend(seenCategories);

    S.chart.timeScale().fitContent();
    updateStatus(true, `NYSE  \u00b7  NASDAQ & S&P 500 % overlay  \u00b7  ${period.toUpperCase()}`);
  } catch (err) {
    console.error('Market chart error:', err);
    updateStatus(false, err.message);
  }
}

function renderMarkerLegend(seenCategories) {
  const el = document.getElementById('markerLegend');
  if (!seenCategories.size) { el.hidden = true; return; }
  el.hidden = false;
  el.innerHTML = Object.entries(MARKER_CATEGORIES)
    .filter(([key]) => seenCategories.has(key))
    .map(([catKey, { label, color, key }]) => {
      const disabled = S.hiddenCategories.has(catKey) ? ' disabled' : '';
      return `<span class="marker-legend-item${disabled}" data-cat="${escHtml(catKey)}" title="Click to toggle">` +
        `<span class="marker-legend-dot" style="background:${escHtml(color)}"></span>` +
        `<span class="marker-legend-key">${escHtml(key)}</span>` +
        `<span>${escHtml(label)}</span></span>`;
    })
    .join('');
  el.querySelectorAll('.marker-legend-item').forEach((item) => {
    item.addEventListener('click', () => toggleCategory(item.dataset.cat));
  });
}

// ─── Category filter toggle ──────────────────────────────────────────────────
function toggleCategory(cat) {
  if (S.hiddenCategories.has(cat)) S.hiddenCategories.delete(cat);
  else S.hiddenCategories.add(cat);
  localStorage.setItem('stan_hidden_cats', JSON.stringify([...S.hiddenCategories]));
  if (S.mode === 'market') loadMarketChart(S.period);
  else if (S.symbol) loadChart(S.symbol, S.period);
}

// ─── Incremental refresh ─────────────────────────────────────────────────────
async function refreshChart() {
  if (S.mode === 'market') { await loadMarketChart(S.period); return; }
  if (!S.symbol || !S.chart) return;
  try {
    const res = await fetch(`/api/stocks/${encodeURIComponent(S.symbol)}/candles?period=${S.period}`);
    if (!res.ok) return;
    const data = await res.json();
    const candles = data.candles.filter(
      (c) => c.open != null && c.high != null && c.low != null && c.close != null,
    );
    if (!candles.length) return;
    const last = candles[candles.length - 1];
    S.candles = candles;
    S.candleSeries.update(last);
    if (last.volume != null) {
      S.volSeries.update({
        time:  last.time, value: last.volume,
        color: last.volume_spike
          ? 'rgba(246,132,16,0.65)'
          : last.close >= last.open ? 'rgba(38,166,154,0.35)' : 'rgba(239,83,80,0.35)',
      });
    }
    if (last.change_pct != null) checkAlerts(S.symbol, last.change_pct);
    document.getElementById('lastUpdate').textContent = 'Updated ' + new Date().toLocaleTimeString();
  } catch (err) {
    console.error('Chart refresh error:', err);
  }
}

// ─── SMA overlays ────────────────────────────────────────────────────────────
const _SMA_PERIOD_NAMES = { 20: 'sma20', 50: 'sma50', 200: 'sma200' };

function setupSMAButtons() {
  document.querySelectorAll('.sma-btn').forEach((btn) => {
    const n = parseInt(btn.dataset.sma, 10);
    if (S.activeSMAs.has(n)) btn.classList.add('active');
    btn.addEventListener('click', () => toggleSMA(n));
  });
}

function toggleSMA(n) {
  if (S.activeSMAs.has(n)) {
    S.activeSMAs.delete(n);
    if (S.smaLines[n]) { S.chart.removeSeries(S.smaLines[n]); delete S.smaLines[n]; }
  } else {
    S.activeSMAs.add(n);
    if (S.symbol) loadSMAOverlays(S.symbol, S.period);
  }
  localStorage.setItem('stan_smas', JSON.stringify([...S.activeSMAs]));
  document.querySelectorAll('.sma-btn').forEach((btn) => {
    btn.classList.toggle('active', S.activeSMAs.has(parseInt(btn.dataset.sma, 10)));
  });
}

async function loadSMAOverlays(symbol, period) {
  if (!S.activeSMAs.size || !S.chart) return;
  const smaParams = [...S.activeSMAs].map((n) => `sma=${n}`).join('&');
  try {
    const res = await fetch(
      `/api/stocks/${encodeURIComponent(symbol)}/indicators?period=${period}&${smaParams}`,
    );
    if (!res.ok) return;
    const data = await res.json();
    for (const n of S.activeSMAs) {
      const key = _SMA_PERIOD_NAMES[n] || `sma${n}`;
      const series = data.indicators[key];
      if (!series || !series.length) continue;
      if (!S.smaLines[n]) {
        S.smaLines[n] = lcAddLine(S.chart, {
          color: SMA_COLORS[n] || '#aaa', lineWidth: 1,
          lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
          title: `SMA${n}`,
        });
      }
      S.smaLines[n].setData(series);
    }
  } catch (err) {
    console.error('SMA load error:', err);
  }
}

function clearSMAOverlays() {
  for (const n of Object.keys(S.smaLines)) {
    try { S.chart.removeSeries(S.smaLines[n]); } catch (_) { /* ignore */ }
  }
  S.smaLines = {};
}

// ─── Stock comparison mode ───────────────────────────────────────────────────
function addCompareSymbol(symbol) {
  symbol = symbol.trim().toUpperCase();
  if (!symbol || S.compareSymbols.includes(symbol) || symbol === S.symbol) return;
  if (S.compareSymbols.length >= 3) { alert('Max 3 comparison symbols'); return; }
  S.compareSymbols.push(symbol);
  renderComparePills();
  loadComparisonOverlays();
}

function removeCompareSymbol(symbol) {
  S.compareSymbols = S.compareSymbols.filter((s) => s !== symbol);
  renderComparePills();
  if (S.compareSymbols.length === 0) {
    clearCompareMode();
    document.getElementById('compareControls').hidden = true;
  } else {
    loadComparisonOverlays();
  }
}

function renderComparePills() {
  const pills = document.getElementById('comparePills');
  const compareColors = ['#4fc3f7', '#ffb74d', '#ce93d8'];
  pills.innerHTML = S.compareSymbols
    .map((sym, i) =>
      `<span class="compare-pill" style="border-color:${compareColors[i]};color:${compareColors[i]}">` +
      `${escHtml(sym)}` +
      `<button data-sym="${escHtml(sym)}" aria-label="Remove ${escHtml(sym)}">\u2715</button></span>`,
    )
    .join('');
  pills.querySelectorAll('button[data-sym]').forEach((btn) => {
    btn.addEventListener('click', () => removeCompareSymbol(btn.dataset.sym));
  });
}

async function loadComparisonOverlays() {
  if (!S.chart || !S.symbol) return;
  for (const series of S.compareSeries) {
    try { S.chart.removeSeries(series); } catch (_) { /* ignore */ }
  }
  S.compareSeries = [];

  if (!S.compareSymbols.length) return;

  S.chart.applyOptions({ leftPriceScale: { visible: true, borderColor: '#2a2e39' } });
  const compareColors = ['#4fc3f7', '#ffb74d', '#ce93d8'];

  for (let i = 0; i < S.compareSymbols.length; i++) {
    const sym = S.compareSymbols[i];
    try {
      const res = await fetch(`/api/stocks/${encodeURIComponent(sym)}/candles?period=${S.period}`);
      if (!res.ok) continue;
      const data = await res.json();
      const pct = normalizeToPercent(data.candles.filter(
        (c) => c.open != null && c.close != null,
      ));
      if (!pct.length) continue;
      const series = lcAddLine(S.chart, {
        color: compareColors[i], lineWidth: 2, priceScaleId: 'left',
        title: sym, lastValueVisible: true, priceLineVisible: false,
      });
      series.setData(pct);
      S.compareSeries.push(series);
    } catch (err) {
      console.error('Compare load error:', sym, err);
    }
  }
}

function clearCompareMode() {
  for (const series of S.compareSeries) {
    try { S.chart.removeSeries(series); } catch (_) { /* ignore */ }
  }
  S.compareSeries = [];
  S.compareSymbols = [];
  renderComparePills();
  if (S.chart && S.mode !== 'market') {
    S.chart.applyOptions({ leftPriceScale: { visible: false } });
  }
}

// ─── Ticker autocomplete ──────────────────────────────────────────────────────
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
    list.innerHTML = hits.map((s) => {
      const star = S.favorites.has(s.symbol) ? '\u2605 ' : '';
      return `<li data-symbol="${escHtml(s.symbol)}"><b>${escHtml(star + s.symbol)}</b> <span>${escHtml(s.name || '')}</span></li>`;
    }).join('');
    list.hidden = false;
  });

  list.addEventListener('click', (e) => {
    const li = e.target.closest('li[data-symbol]');
    if (li) selectSymbol(li.dataset.symbol);
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { const q = input.value.trim().toUpperCase(); if (q) selectSymbol(q); }
    if (e.key === 'Escape') list.hidden = true;
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('.ticker-search')) list.hidden = true;
  });

  const cmpInput = document.getElementById('compareInput');
  if (cmpInput) {
    cmpInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { addCompareSymbol(cmpInput.value); cmpInput.value = ''; }
      if (e.key === 'Escape') cmpInput.value = '';
    });
  }
}

function selectSymbol(symbol) {
  S.mode   = 'symbol';
  S.symbol = symbol.toUpperCase();
  document.getElementById('tickerInput').value = S.symbol;
  document.getElementById('autocompleteList').hidden = true;
  document.getElementById('marketBtn').classList.remove('active');
  document.getElementById('overlayBadge').hidden = true;
  document.getElementById('markerLegend').hidden = true;
  if (S.chart) S.chart.applyOptions({ leftPriceScale: { visible: false } });
  if (S.overlayLineSeries) S.overlayLineSeries.setData([]);
  if (S.sp500LineSeries)   S.sp500LineSeries.setData([]);
  loadChart(S.symbol, S.period);
}

// ─── Period buttons ───────────────────────────────────────────────────────────
function setupPeriodButtons() {
  document.querySelectorAll('.period-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.period-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      S.period = btn.dataset.period;
      if (S.mode === 'market') loadMarketChart(S.period);
      else if (S.symbol) loadChart(S.symbol, S.period);
    });
  });
}

// ─── Keyboard shortcuts ───────────────────────────────────────────────────────
function setupKeyboard() {
  const PERIODS = ['1d', '5d', '1mo', '3mo'];
  document.addEventListener('keydown', (e) => {
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea') return;
    if (e.key === 'ArrowRight') {
      const idx = Math.min(PERIODS.indexOf(S.period) + 1, PERIODS.length - 1);
      setPeriod(PERIODS[idx]);
    } else if (e.key === 'ArrowLeft') {
      const idx = Math.max(PERIODS.indexOf(S.period) - 1, 0);
      setPeriod(PERIODS[idx]);
    } else if (e.key === '/') {
      e.preventDefault();
      document.getElementById('tickerInput').focus();
    } else if (e.key === 'Escape') {
      closeNewsPanel();
      document.getElementById('autocompleteList').hidden = true;
    } else if (e.key === 'm' || e.key === 'M') {
      loadMarketChart(S.period);
    }
  });
}

function setPeriod(p) {
  S.period = p;
  document.querySelectorAll('.period-btn').forEach((b) => {
    b.classList.toggle('active', b.dataset.period === p);
  });
  if (S.mode === 'market') loadMarketChart(p);
  else if (S.symbol) loadChart(S.symbol, p);
}

// ─── News detail panel ────────────────────────────────────────────────────────
function openNewsPanel(item) {
  const articles = item.articles || [item];
  let html;
  if (articles.length === 1) {
    const a = articles[0];
    html = `
      <div class="article-source">${escHtml(a.source || 'News')}</div>
      <h4 class="article-headline">${escHtml(a.headline || '')}</h4>
      <p class="article-desc">${escHtml(a.description || 'No summary available.')}</p>
      <a class="article-link" href="${escAttr(a.url)}" target="_blank" rel="noopener noreferrer">
        Read full article \u2192
      </a>`;
  } else {
    html = `<p class="cluster-count">${articles.length} news events</p>` +
      articles.map((a) => `
      <div class="cluster-item">
        <div class="article-source">${escHtml(a.source || 'News')}</div>
        <a class="article-link" href="${escAttr(a.url)}" target="_blank" rel="noopener noreferrer">
          ${escHtml(a.headline || '')}
        </a>
        <p class="article-desc">${escHtml(a.description || '')}</p>
      </div>`).join('<hr class="cluster-divider">');
  }

  document.getElementById('newsPanelBody').innerHTML = html;
  const panel = document.getElementById('newsPanel');
  panel.classList.add('open');
  panel.setAttribute('aria-hidden', 'false');

  if (articles.length === 1 && articles[0].id) {
    renderImpactCharts(articles[0].id);
  }
}

function closeNewsPanel() {
  const panel = document.getElementById('newsPanel');
  panel.classList.remove('open');
  panel.setAttribute('aria-hidden', 'true');
}

// ─── News impact sparklines ───────────────────────────────────────────────────
async function renderImpactCharts(articleId) {
  try {
    const res = await fetch(`/api/news/${encodeURIComponent(String(articleId))}/impact`);
    if (!res.ok) return;
    const data = await res.json();

    const tickersWithData = (data.tickers || []).filter((t) => {
      const filled = t.intervals.filter((i) => i.interval_price != null);
      return t.base_price && filled.length >= 2;
    });
    if (!tickersWithData.length) return;

    const div = document.createElement('div');
    div.className = 'impact-charts';
    div.innerHTML = '<div class="impact-charts-title">Price Impact (5m \u2192 24h)</div>' +
      tickersWithData.map((t) => {
        const values = [
          t.base_price,
          ...t.intervals.map((i) => i.interval_price).filter((v) => v != null),
        ];
        return `<div class="impact-chart">
          <span class="impact-symbol">${escHtml(t.symbol)}</span>
          ${buildSparkline(values)}
        </div>`;
      }).join('');
    document.getElementById('newsPanelBody').appendChild(div);
  } catch (_) {
    // Impact data unavailable — silently skip
  }
}

function buildSparkline(values) {
  if (values.length < 2) return '';
  const W = 120, H = 40, PAD = 4;
  const min = Math.min(...values), max = Math.max(...values);
  const range = max - min || 1;
  const points = values.map((v, i) => {
    const x = PAD + (i / (values.length - 1)) * (W - PAD * 2);
    const y = H - PAD - ((v - min) / range) * (H - PAD * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const last = values[values.length - 1], base = values[0];
  const color = last > base ? '#26a69a' : last < base ? '#ef5350' : '#9b9ea3';
  const pct   = ((last - base) / base * 100).toFixed(2);
  const str   = (last >= base ? '+' : '') + pct + '%';
  return `<svg class="sparkline" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">` +
    `<polyline points="${points.join(' ')}" fill="none" stroke="${color}" stroke-width="1.5"/>` +
    `</svg><span class="impact-change" style="color:${color}">${escHtml(str)}</span>`;
}

// ─── News feed ─────────────────────────────────────────────────────────────────
let _newsSearchTimer = null;

async function loadNewsFeed(q = '') {
  try {
    const url = q ? `/api/news?q=${encodeURIComponent(q)}&limit=60` : '/api/news?limit=60';
    const res = await fetch(url);
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
    list.innerHTML = '<li class="placeholder-row">No news yet \u2014 collecting\u2026</li>';
    return;
  }
  list.innerHTML = items.map((a) => {
    const sentClass = a.sentiment || 'neutral';
    return `<li class="news-item">
      <div class="news-meta">
        <span class="news-source">
          <span class="sentiment-dot ${escHtml(sentClass)}" title="${escHtml(sentClass)}"></span>
          ${escHtml(a.source || '')}
        </span>
        <span class="news-time">${relTime(a.published_at)}</span>
      </div>
      <a class="news-headline" href="${escAttr(a.url)}" target="_blank" rel="noopener noreferrer">
        ${escHtml(a.headline)}
      </a>
      ${a.tickers && a.tickers.length
        ? `<div class="news-tickers">${a.tickers.map((t) =>
            `<span class="ticker-tag" data-symbol="${escHtml(t)}">${escHtml(t)}</span>`).join('')}</div>`
        : ''}
    </li>`;
  }).join('');
  list.querySelectorAll('.ticker-tag').forEach((tag) => {
    tag.addEventListener('click', () => selectSymbol(tag.dataset.symbol));
  });
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
    tbody.innerHTML = '<tr><td colspan="6" class="placeholder-row">No data yet \u2014 collecting\u2026</td></tr>';
    return;
  }
  const sorted = [
    ...items.filter((s) => S.favorites.has(s.symbol)),
    ...items.filter((s) => !S.favorites.has(s.symbol)),
  ];
  tbody.innerHTML = sorted.map((s) => {
    const chg    = s.change_pct;
    const cls    = chg == null ? '' : chg >= 0 ? 'up' : 'down';
    const chgStr = chg == null ? '\u2013' : (chg >= 0 ? '+' : '') + chg.toFixed(2) + '%';
    const isFav  = S.favorites.has(s.symbol);
    const favRow = isFav ? ' favorited' : '';
    return `<tr class="stock-row${favRow}" data-symbol="${escHtml(s.symbol)}">
      <td class="fav-col"><span class="fav-star${isFav ? ' active' : ''}" data-sym="${escHtml(s.symbol)}">\u2605</span></td>
      <td>${escHtml(s.symbol)}</td>
      <td class="name-cell">${escHtml(s.name || '\u2013')}</td>
      <td>${s.close != null ? '$' + s.close.toFixed(2) : '\u2013'}</td>
      <td class="${cls}">${chgStr}</td>
      <td>${s.volume != null ? fmtVol(s.volume) : '\u2013'}</td>
    </tr>`;
  }).join('');

  tbody.querySelectorAll('.stock-row').forEach((row) => {
    row.addEventListener('click', (e) => {
      if (e.target.closest('.fav-star')) return;
      selectSymbol(row.dataset.symbol);
    });
  });
  tbody.querySelectorAll('.fav-star').forEach((star) => {
    star.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleFavorite(star.dataset.sym);
    });
  });
}

// ─── Favorites ────────────────────────────────────────────────────────────────
function toggleFavorite(symbol) {
  if (S.favorites.has(symbol)) S.favorites.delete(symbol);
  else S.favorites.add(symbol);
  localStorage.setItem('stan_favorites', JSON.stringify([...S.favorites]));
  renderStocksTable(S.allStocks);
}

// ─── Price alerts ─────────────────────────────────────────────────────────────
function renderAlertBadges() {
  const sym = S.symbol;
  const alertForm = document.getElementById('alertForm');
  if (!sym) { alertForm.hidden = true; return; }
  const alert = S.alerts[sym];
  const input = document.getElementById('alertThreshold');
  const removeBtn = document.getElementById('removeAlertBtn');
  if (alert) { input.value = alert.threshold; removeBtn.hidden = false; }
  else { input.value = ''; removeBtn.hidden = true; }
}

function checkAlerts(symbol, changePct) {
  const alert = S.alerts[symbol];
  if (!alert) return;
  if (Math.abs(changePct) >= alert.threshold) triggerAlert(symbol, changePct);
}

function triggerAlert(symbol, changePct) {
  const dir = changePct >= 0 ? '\u25b2' : '\u25bc';
  const msg = `${symbol} ${dir} ${Math.abs(changePct).toFixed(2)}%`;
  if ('Notification' in window && Notification.permission === 'granted') {
    new Notification('STAN Price Alert', { body: msg });
  } else if ('Notification' in window && Notification.permission !== 'denied') {
    Notification.requestPermission().then((p) => {
      if (p === 'granted') new Notification('STAN Price Alert', { body: msg });
    });
  }
  updateStatus(true, `\u26a0 Alert: ${msg}`);
}

// ─── CSV export ───────────────────────────────────────────────────────────────
function exportCSV(filename, rows, headers) {
  const lines = [headers.join(',')];
  for (const row of rows) {
    lines.push(headers.map((h) => {
      const v = row[h] == null ? '' : String(row[h]);
      return v.includes(',') ? `"${v.replace(/"/g, '""')}"` : v;
    }).join(','));
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ─── Trending tickers ─────────────────────────────────────────────────────────
async function loadTrendingTickers() {
  try {
    const res = await fetch('/api/news/trending?hours=24&limit=10');
    if (!res.ok) return;
    const data = await res.json();
    renderTrendingTickers(data.items);
  } catch (err) {
    console.error('Trending error:', err);
  }
}

function renderTrendingTickers(items) {
  const list = document.getElementById('trendingList');
  if (!items || !items.length) {
    list.innerHTML = '<li class="placeholder-row">No data yet</li>';
    return;
  }
  list.innerHTML = items.map((item, i) => {
    const chg    = item.change_pct;
    const cls    = chg == null ? '' : chg >= 0 ? 'up' : 'down';
    const chgStr = chg == null ? '' : (chg >= 0 ? '+' : '') + chg.toFixed(2) + '%';
    return `<li class="trending-item" data-symbol="${escHtml(item.symbol)}">
      <span class="trending-rank">${i + 1}</span>
      <span class="trending-symbol">${escHtml(item.symbol)}</span>
      <span class="trending-mentions">${item.mentions}\u2736</span>
      <span class="trending-chg ${cls}">${escHtml(chgStr)}</span>
    </li>`;
  }).join('');
  list.querySelectorAll('.trending-item').forEach((row) => {
    row.addEventListener('click', () => selectSymbol(row.dataset.symbol));
  });
}

// ─── Sector heatmap ───────────────────────────────────────────────────────────
async function loadSectorHeatmap() {
  try {
    const res = await fetch('/api/stocks/sectors');
    if (!res.ok) return;
    const data = await res.json();
    renderSectorHeatmap(data.sectors);
  } catch (err) {
    console.error('Sector heatmap error:', err);
  }
}

function sectorColor(pct) {
  if (pct == null) return 'rgba(30,33,48,0.8)';
  const intensity = Math.min(Math.abs(pct) / 2, 1);
  if (pct > 0) return `rgba(38,166,154,${(0.2 + intensity * 0.6).toFixed(2)})`;
  return `rgba(239,83,80,${(0.2 + intensity * 0.6).toFixed(2)})`;
}

function renderSectorHeatmap(sectors) {
  const tiles = document.getElementById('sectorTiles');
  if (!sectors || !sectors.length) {
    tiles.innerHTML = '<span class="placeholder-row">No sector data</span>';
    return;
  }
  tiles.innerHTML = sectors.map((s) => {
    const pct    = s.avg_change_pct;
    const color  = sectorColor(pct);
    const pctStr = pct == null ? '\u2013' : (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%';
    return `<div class="sector-tile" style="background:${color}" data-sector="${escHtml(s.sector)}" title="${escHtml(s.sector)} (${escHtml(pctStr)})">
      <span class="sector-name">${escHtml(s.sector)}</span>
      <span class="sector-pct">${escHtml(pctStr)}</span>
    </div>`;
  }).join('');

  tiles.querySelectorAll('.sector-tile').forEach((tile) => {
    tile.addEventListener('click', () => {
      const q = tile.dataset.sector;
      document.getElementById('stockSearch').value = q;
      document.querySelectorAll('.stock-row').forEach((row) => {
        row.style.display = row.textContent.toLowerCase().includes(q.toLowerCase()) ? '' : 'none';
      });
    });
  });
}

// ─── WebSocket live push ─────────────────────────────────────────────────────
function setupWebSocket() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const url   = `${proto}://${location.host}/ws`;

  function connect() {
    S.ws = new WebSocket(url);

    S.ws.addEventListener('open', () => {
      if (S.refreshTimer) { clearInterval(S.refreshTimer); S.refreshTimer = null; }
    });

    S.ws.addEventListener('message', async (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.event === 'update') {
          await Promise.all([refreshChart(), loadNewsFeed(), loadStockList(),
                             loadTrendingTickers(), loadSectorHeatmap()]);
          document.getElementById('lastUpdate').textContent =
            'Updated ' + new Date().toLocaleTimeString();
        }
      } catch (_) { /* ignore malformed */ }
    });

    S.ws.addEventListener('close', () => {
      S.ws = null;
      if (!S.refreshTimer) S.refreshTimer = setInterval(pollingRefresh, 60_000);
      setTimeout(connect, 10_000);
    });

    S.ws.addEventListener('error', () => {
      // close handler will run next and handle reconnect
    });
  }

  connect();
}

async function pollingRefresh() {
  await Promise.all([refreshChart(), loadNewsFeed(), loadStockList(),
                     loadTrendingTickers(), loadSectorHeatmap()]);
  document.getElementById('lastUpdate').textContent =
    'Updated ' + new Date().toLocaleTimeString();
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function relTime(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60)    return 'Just now';
  if (diff < 3600)  return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return new Date(iso).toLocaleDateString();
}

function fmtVol(v) {
  if (v >= 1e9) return (v / 1e9).toFixed(1) + 'B';
  if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
  if (v >= 1e3) return (v / 1e3).toFixed(0) + 'K';
  return String(Math.round(v));
}

function updateStatus(ok, msg) {
  document.getElementById('statusDot').className = 'status-dot ' + (ok ? 'ok' : 'error');
  document.getElementById('statusText').textContent = msg;
  document.getElementById('lastUpdate').textContent =
    'Updated ' + new Date().toLocaleTimeString();
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function escAttr(s) {
  const str = String(s);
  if (!/^(https?:\/\/|#|\/)/i.test(str)) return '#';
  return str.replace(/"/g, '%22').replace(/'/g, '%27');
}

// ─── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  const savedTheme = localStorage.getItem('stan_theme') || 'dark';
  document.documentElement.dataset.theme = savedTheme;
  document.getElementById('themeToggle').textContent = savedTheme === 'light' ? '\u263e' : '\u2600';

  document.getElementById('closePanelBtn').addEventListener('click', closeNewsPanel);
  document.getElementById('themeToggle').addEventListener('click', toggleTheme);

  // News search — debounced server-side FTS
  document.getElementById('newsSearch').addEventListener('input', (e) => {
    clearTimeout(_newsSearchTimer);
    const q = e.target.value.trim();
    _newsSearchTimer = setTimeout(() => loadNewsFeed(q), 300);
  });

  // Stocks table filter (client-side DOM)
  document.getElementById('stockSearch').addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase();
    document.querySelectorAll('.stock-row').forEach((row) => {
      row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
  });

  // Alert toggle
  document.getElementById('alertBtn').addEventListener('click', () => {
    const form = document.getElementById('alertForm');
    form.hidden = !form.hidden;
  });

  document.getElementById('setAlertBtn').addEventListener('click', () => {
    const sym = S.symbol;
    const val = parseFloat(document.getElementById('alertThreshold').value);
    if (!sym || isNaN(val) || val <= 0) return;
    S.alerts[sym] = { threshold: val };
    localStorage.setItem('stan_alerts', JSON.stringify(S.alerts));
    renderAlertBadges();
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  });

  document.getElementById('removeAlertBtn').addEventListener('click', () => {
    const sym = S.symbol;
    if (sym) { delete S.alerts[sym]; localStorage.setItem('stan_alerts', JSON.stringify(S.alerts)); }
    renderAlertBadges();
  });

  // Compare toggle
  document.getElementById('compareBtn').addEventListener('click', () => {
    const ctrl = document.getElementById('compareControls');
    ctrl.hidden = !ctrl.hidden;
    if (!ctrl.hidden) document.getElementById('compareInput').focus();
  });

  document.getElementById('clearCompareBtn').addEventListener('click', () => {
    clearCompareMode();
    document.getElementById('compareControls').hidden = true;
    if (S.symbol) loadChart(S.symbol, S.period);
  });

  // CSV exports
  document.getElementById('exportCandlesBtn').addEventListener('click', () => {
    if (!S.candles.length) return;
    const symbol = S.symbol || 'market';
    exportCSV(
      `${symbol}_${S.period}_candles.csv`,
      S.candles,
      ['time', 'open', 'high', 'low', 'close', 'volume', 'volume_spike'],
    );
  });

  document.getElementById('exportStocksBtn').addEventListener('click', () => {
    if (!S.allStocks.length) return;
    exportCSV(
      'stan_stocks.csv',
      S.allStocks,
      ['symbol', 'name', 'sector', 'exchange', 'close', 'change_pct', 'volume'],
    );
  });

  setupTickerSearch();
  setupPeriodButtons();
  setupSMAButtons();
  setupKeyboard();

  // Market overview button
  document.getElementById('marketBtn').addEventListener('click', () => {
    document.querySelectorAll('.period-btn').forEach((b) => {
      b.classList.toggle('active', b.dataset.period === S.period);
    });
    loadMarketChart(S.period);
  });

  // Initial data load
  await Promise.all([loadStockList(), loadNewsFeed(), loadTrendingTickers(), loadSectorHeatmap()]);

  // Default to market overview
  loadMarketChart(S.period);

  // WebSocket with polling fallback
  setupWebSocket();
  S.refreshTimer = setInterval(pollingRefresh, 60_000);
});
