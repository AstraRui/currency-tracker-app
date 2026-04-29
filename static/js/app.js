const rootEl = document.documentElement;
const themeToggleEl = document.getElementById("themeToggle");
const statusEl = document.getElementById("status");
const codeEl = document.getElementById("code");
const daysEl = document.getElementById("days");
const emptyHintEl = document.getElementById("emptyHint");
const apiAlertEl = document.getElementById("apiAlert");
const apiAlertTextEl = document.getElementById("apiAlertText");
const favoritesLeftEl = document.getElementById("favoritesLeft");
const favoritesRightEl = document.getElementById("favoritesRight");

let chart;

function getTheme() {
  return rootEl.getAttribute("data-theme") || "light";
}

function setTheme(name) {
  const next = (name === "dark") ? "dark" : "light";
  rootEl.setAttribute("data-theme", next);
  if (themeToggleEl) themeToggleEl.checked = next === "dark";
  try { localStorage.setItem("theme", next); } catch {}
  applyChartTheme();
}

function setStatus(text) {
  statusEl.textContent = text || "";
}

function showAlert(text) {
  if (!apiAlertEl || !apiAlertTextEl) return;
  apiAlertTextEl.textContent = text || "";
  apiAlertEl.classList.toggle("hidden", !text);
}

function showEmptyHint(show) {
  if (!emptyHintEl) return;
  emptyHintEl.classList.toggle("hidden", !show);
}

function formatRub(x) {
  if (!Number.isFinite(x)) return "—";
  return new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 4 }).format(x);
}

function formatDelta(delta) {
  if (!Number.isFinite(delta)) return "—";
  const sign = delta > 0 ? "+" : "";
  const txt = sign + new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 4 }).format(delta);
  return `${txt} ₽`;
}

async function loadCodes() {
  const r = await fetch("/api/codes");
  const j = await r.json();
  const codes = (j.codes || []);
  const preferred = ["USD", "EUR", "CNY", "GBP", "KZT"];
  const ordered = [...new Set([...preferred.filter(c => codes.includes(c)), ...codes])];
  codeEl.innerHTML = ordered.map(c => `<option value="${c}">${c}</option>`).join("");
  if (!codeEl.value && ordered.length) codeEl.value = ordered[0];
  showEmptyHint(ordered.length === 0);
}

function pct(x) {
  if (!Number.isFinite(x)) return "—";
  if (Math.abs(x) < 0.005) return "";
  const sign = x > 0 ? "+" : "";
  return sign + new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(x) + "%";
}

function favRowHtml(it) {
  const val = Number(it.value_per_1);
  const dd = Number(it.delta_day);
  const arrow = Number.isFinite(dd) ? (dd > 0 ? "▲" : (dd < 0 ? "▼" : "•")) : "";
  const ddTxt = Number.isFinite(dd) ? `${arrow} ${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 4 }).format(dd)} ₽` : "";
  const ddCls = Number.isFinite(dd) ? (dd > 0 ? "badge-success" : (dd < 0 ? "badge-error" : "badge-neutral")) : "badge-neutral";

  return `<button type="button" class="w-full text-left rounded-box border border-base-200/60 hover:bg-base-200/30 transition-colors px-3 py-2" data-code="${it.code}">
    <div class="popular-item">
      <div class="min-w-0">
        <div class="flex items-center gap-2">
          <span class="badge badge-soft nav-accent-ring">${it.code}</span>
          <span class="text-sm truncate">${it.name || ""}</span>
        </div>
      </div>
      <div class="popular-right">
        <div class="text-sm font-semibold tabular-nums">${formatRub(val)}</div>
        ${ddTxt ? `<span class="badge badge-soft ${ddCls} mt-1">${ddTxt}</span>` : ``}
      </div>
    </div>
  </button>`;
}

function wireFavoritesClicks(containerEl) {
  if (!containerEl) return;
  containerEl.querySelectorAll("button[data-code]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const code = btn.getAttribute("data-code");
      if (!code) return;
      codeEl.value = code;
      await refresh();
    });
  });
}

async function refreshFavorites() {
  if (!favoritesLeftEl || !favoritesRightEl) return;
  try {
    const r = await fetch("/api/favorites?limit=10&spark_days=14");
    const j = await r.json();
    const items = j.items || [];
    if (!items.length) {
      const msg = `<div class="text-sm text-base-content/70">Нет данных. Нажмите “Синхронизировать сегодня”.</div>`;
      favoritesLeftEl.innerHTML = msg;
      favoritesRightEl.innerHTML = msg;
      return;
    }

    const mid = Math.ceil(items.length / 2);
    const left = items.slice(0, mid);
    const right = items.slice(mid);

    favoritesLeftEl.innerHTML = left.map(favRowHtml).join("");
    favoritesRightEl.innerHTML = right.map(favRowHtml).join("");
    wireFavoritesClicks(favoritesLeftEl);
    wireFavoritesClicks(favoritesRightEl);
  } catch (e) {
    const msg = `<div class="text-sm text-base-content/70">Ошибка загрузки списка</div>`;
    if (favoritesLeftEl) favoritesLeftEl.innerHTML = msg;
    if (favoritesRightEl) favoritesRightEl.innerHTML = msg;
  }
}

async function loadRates() {
  const code = codeEl.value || "USD";
  const days = Number(daysEl.value || 30);
  setStatus("Загружаю данные...");
  const r = await fetch(`/api/rates/${encodeURIComponent(code)}?days=${days}`);
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || "Ошибка API. Попробуйте “Синхронизировать сегодня”.");
  }
  return await r.json();
}

async function loadQuote(code) {
  const r = await fetch(`/api/rates/${encodeURIComponent(code)}?days=2`);
  if (!r.ok) return null;
  return await r.json();
}

function per1Rub(payload, value) {
  const nominal = Number(payload?.nominal || 1);
  const v = Number(value);
  if (!Number.isFinite(v) || !Number.isFinite(nominal) || nominal <= 0) return NaN;
  return v / nominal;
}

function renderCard(prefix, code, payload) {
  const valueEl = document.getElementById(`${prefix}_value`);
  const deltaEl = document.getElementById(`${prefix}_delta`);
  const metaEl = document.getElementById(`${prefix}_meta`);

  if (!payload || !payload.items || payload.items.length === 0) {
    if (valueEl) valueEl.textContent = "—";
    if (deltaEl) deltaEl.textContent = "нет данных";
    if (metaEl) metaEl.textContent = "";
    return;
  }

  const items = payload.items;
  const last = items[items.length - 1];
  const prev = items.length >= 2 ? items[items.length - 2] : null;
  const lastPer1 = per1Rub(payload, last.value);
  const prevPer1 = prev ? per1Rub(payload, prev.value) : NaN;
  const delta = Number.isFinite(lastPer1) && Number.isFinite(prevPer1) ? (lastPer1 - prevPer1) : NaN;

  if (valueEl) valueEl.textContent = formatRub(lastPer1);
  if (deltaEl) {
    const arrow = Number.isFinite(delta) ? (delta > 0 ? "▲ " : (delta < 0 ? "▼ " : "• ")) : "";
    deltaEl.textContent = arrow + formatDelta(delta);
    deltaEl.classList.toggle("badge-success", Number.isFinite(delta) && delta > 0);
    deltaEl.classList.toggle("badge-error", Number.isFinite(delta) && delta < 0);
    deltaEl.classList.toggle("badge-neutral", Number.isFinite(delta) && delta === 0);
  }
  if (metaEl) {
    const nominal = Number(payload.nominal || 1);
    const raw = Number(last.value);
    const rawTxt = (Number.isFinite(raw) && Number.isFinite(nominal)) ? `${formatRub(raw)} за ${nominal} ${code}` : "";
    metaEl.textContent = `${payload.name || code} • ${last.date}${rawTxt ? " • " + rawTxt : ""}`;
  }
}

function renderChart(payload) {
  const labels = payload.items.map(x => x.date);
  const data = payload.items.map(x => per1Rub(payload, x.value));
  const title = `${payload.char_code} — ${payload.name} (за ${payload.days} дней) • в пересчёте за 1`;

  const ctx = document.getElementById("chart").getContext("2d");
  if (chart) chart.destroy();
  const { baseContent, primary, grid } = getChartColors();

  chart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "Value (RUB)",
        data,
        borderWidth: 2,
        tension: 0.25,
        borderColor: primary,
        pointBackgroundColor: primary,
      }]
    },
    options: {
      plugins: {
        title: { display: true, text: title, color: baseContent },
        legend: { labels: { color: baseContent } }
      },
      scales: {
        x: { ticks: { color: baseContent }, grid: { color: grid } },
        y: { ticks: { color: baseContent }, grid: { color: grid }, title: { display: true, text: `RUB за 1 ${payload.char_code}`, color: baseContent } }
      }
    }
  });
}

function getChartColors() {
  const theme = getTheme();
  const computed = getComputedStyle(rootEl);
  const baseContent = computed.getPropertyValue("--color-base-content").trim()
    || (theme === "dark" ? "#ffffff" : "#111827");
  const primary = computed.getPropertyValue("--color-primary").trim() || "#1d4ed8";
  const grid = theme === "dark" ? "rgba(229, 231, 235, 0.22)" : "rgba(17, 24, 39, 0.12)";
  return { baseContent, primary, grid };
}

function applyChartTheme() {
  if (!chart) return;
  const { baseContent, primary, grid } = getChartColors();
  chart.data.datasets.forEach(ds => {
    ds.borderColor = primary;
    ds.pointBackgroundColor = primary;
  });
  if (chart.options?.plugins?.title) chart.options.plugins.title.color = baseContent;
  if (chart.options?.plugins?.legend?.labels) chart.options.plugins.legend.labels.color = baseContent;
  if (chart.options?.scales?.x?.ticks) chart.options.scales.x.ticks.color = baseContent;
  if (chart.options?.scales?.x?.grid) chart.options.scales.x.grid.color = grid;
  if (chart.options?.scales?.y?.ticks) chart.options.scales.y.ticks.color = baseContent;
  if (chart.options?.scales?.y?.grid) chart.options.scales.y.grid.color = grid;
  if (chart.options?.scales?.y?.title) chart.options.scales.y.title.color = baseContent;
  chart.update();
}

async function refresh() {
  try {
    showAlert("");
    const payload = await loadRates();
    renderChart(payload);
    setStatus("");
  } catch (e) {
    const msg = String(e.message || e);
    setStatus(msg);
    showAlert(msg);
  }
}

async function refreshHeroCards() {
  try {
    const [usd, eur, cny] = await Promise.all([
      loadQuote("USD"),
      loadQuote("EUR"),
      loadQuote("CNY"),
    ]);
    renderCard("cardUSD", "USD", usd);
    renderCard("cardEUR", "EUR", eur);
    renderCard("cardCNY", "CNY", cny);
  } catch {
  }
}

function wireCard(cardId, code) {
  const el = document.getElementById(cardId);
  if (!el) return;
  el.addEventListener("click", async () => {
    codeEl.value = code;
    await refresh();
  });
}

document.getElementById("reload").addEventListener("click", refresh);
document.getElementById("sync").addEventListener("click", async () => {
  try {
    showAlert("");
    setStatus("Синхронизация...");
    const r = await fetch("/api/sync", { method: "POST" });
    const j = await r.json();
    setStatus(j.synced ? `Синхронизировано: ${j.date}` : `Без изменений: ${j.date}`);
    await loadCodes();
    await refreshFavorites();
    await refreshHeroCards();
    await refresh();
  } catch (e) {
    const msg = String(e.message || e);
    setStatus(msg);
    showAlert(msg);
  }
});

(async () => {
  try {
    const saved = (() => { try { return localStorage.getItem("theme"); } catch { return null; } })();
    setTheme(saved || "light");
    if (themeToggleEl) {
      themeToggleEl.addEventListener("change", () => setTheme(themeToggleEl.checked ? "dark" : "light"));
    }
    await loadCodes();
    await refreshFavorites();
    wireCard("cardUSD", "USD");
    wireCard("cardEUR", "EUR");
    wireCard("cardCNY", "CNY");
    await refreshHeroCards();
    await refresh();
  } catch (e) {
    setStatus(String(e.message || e));
  }
})();
