(() => {
  const REPO_URL_FALLBACK = "https://github.com/";
  const MIN_CONFIDENCE = 0.6;

  const $ = (sel) => document.querySelector(sel);

  const fmtRel = (iso) => {
    if (!iso) return "";
    const t = new Date(iso).getTime();
    if (!t) return "";
    const diff = (Date.now() - t) / 1000;
    const abs = Math.abs(diff);
    const sign = diff >= 0 ? "ago" : "from now";
    if (abs < 60) return `${Math.round(abs)}s ${sign}`;
    if (abs < 3600) return `${Math.round(abs / 60)}m ${sign}`;
    if (abs < 86400) return `${Math.round(abs / 3600)}h ${sign}`;
    if (abs < 86400 * 30) return `${Math.round(abs / 86400)}d ${sign}`;
    return new Date(iso).toISOString().slice(0, 10);
  };

  const fmtDate = (iso) => {
    if (!iso) return "";
    return new Date(iso).toISOString().slice(0, 10);
  };

  const isToday = (iso) => {
    if (!iso) return false;
    const d = new Date(iso);
    const now = new Date();
    return (
      d.getUTCFullYear() === now.getUTCFullYear() &&
      d.getUTCMonth() === now.getUTCMonth() &&
      d.getUTCDate() === now.getUTCDate()
    );
  };

  const escapeHtml = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));

  const sevBadge = (sev) => {
    const s = (sev || "").toLowerCase();
    if (!s || s === "unknown") return "";
    return `<span class="badge badge--${escapeHtml(s)}">${escapeHtml(s)}</span>`;
  };

  const cveBadge = (cve) => {
    if (!cve) return "";
    const safe = escapeHtml(cve);
    const url = `https://nvd.nist.gov/vuln/detail/${encodeURIComponent(cve)}`;
    return `<a class="badge badge--cve" href="${url}" target="_blank" rel="noopener">${safe}</a>`;
  };

  const renderItem = (it) => {
    const today = isToday(it.created_at);
    const classes = ["item"];
    if (today) classes.push("is-today");
    const safeTitle = escapeHtml(it.title || "(untitled)");
    const safeUrl = escapeHtml(it.url || it.hn_url);
    const safeHn = escapeHtml(it.hn_url);
    const summary = it.summary
      ? `<p class="item-summary">${escapeHtml(it.summary)}</p>`
      : "";
    return `
    <li class="${classes.join(" ")}">
      <h3 class="item-title">
        <a href="${safeUrl}" target="_blank" rel="noopener">${safeTitle}</a>
      </h3>
      <div class="item-side">
        ${today ? '<span class="badge badge--today">today</span>' : ""}
        ${cveBadge(it.cve)}
        ${sevBadge(it.severity)}
      </div>
      ${summary}
      <div class="item-foot">
        <span>${escapeHtml(fmtDate(it.created_at))}</span>
        <span>·</span>
        <span>${escapeHtml(fmtRel(it.created_at))}</span>
        <span>·</span>
        <a href="${safeHn}" target="_blank" rel="noopener">HN ${it.points ? `(${it.points}↑)` : ""}</a>
        ${it.confidence != null ? `<span>·</span><span>conf ${(it.confidence * 100).toFixed(0)}%</span>` : ""}
      </div>
    </li>`;
  };

  const setStatus = (yes, count) => {
    const el = $("#status");
    const sub = $("#status-sub");
    el.classList.remove("status--unknown", "status--yes", "status--no");
    if (yes) {
      el.classList.add("status--yes");
      el.textContent = "YES.";
      sub.textContent =
        count === 1
          ? "1 new Linux privesc surfaced today."
          : `${count} new Linux privesc items surfaced today.`;
    } else {
      el.classList.add("status--no");
      el.textContent = "Not yet.";
      sub.textContent = "No fresh Linux privesc on the feed today (UTC).";
    }
  };

  const render = (data, showLow) => {
    const items = (data.items || []).filter((x) => x.is_privesc);
    const filtered = showLow
      ? items
      : items.filter((x) => (x.confidence ?? 0) >= MIN_CONFIDENCE);

    const todayCount = filtered.filter((x) => isToday(x.created_at)).length;
    setStatus(todayCount > 0, todayCount);

    const list = $("#items");
    if (!filtered.length) {
      list.innerHTML = `<li class="empty">${
        items.length
          ? "Nothing above the confidence threshold. Toggle 'show low-confidence' to see more."
          : "No Linux privesc items detected in the recent window."
      }</li>`;
    } else {
      list.innerHTML = filtered.map(renderItem).join("");
    }

    const meta = $("#meta-line");
    const gen = data.generated_at ? fmtRel(data.generated_at) : "—";
    meta.textContent =
      `updated ${gen}` +
      (data.model ? ` · model ${data.model}` : "") +
      (data.total_scanned != null ? ` · ${data.total_scanned} stories scanned` : "");
  };

  const main = async () => {
    const repo = $("#repo-link");
    if (repo) repo.href = REPO_URL_FALLBACK;

    let data;
    try {
      const r = await fetch(`data.json?cb=${Date.now()}`, { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      data = await r.json();
    } catch (e) {
      $("#status").textContent = "data unavailable";
      $("#status").classList.remove("status--unknown");
      $("#status").classList.add("status--unknown");
      $("#status-sub").textContent = String(e);
      $("#items").innerHTML = "";
      return;
    }

    const toggle = $("#show-low");
    const apply = () => render(data, toggle.checked);
    toggle.addEventListener("change", apply);
    apply();
  };

  main();
})();
