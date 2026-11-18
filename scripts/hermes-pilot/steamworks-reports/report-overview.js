(() => {
  const appId = location.pathname.match(/^\/app\/details\/(\d+)\/?$/)?.[1];
  if (location.origin !== "https://partner.steampowered.com" || !appId) {
    return { status: "outside_app_report" };
  }

  const text = (node) => (node?.innerText || "").trim();
  const lifetimeLabel = /^Lifetime (Steam revenue|Steam units|total units|units returned)\b/i;
  const selectedLabel = /^(Steam units|Total units|Steam revenue|In-game revenue(?: \(details\))?|Total revenue)$/i;
  const reports = {};

  for (const table of document.querySelectorAll("table")) {
    if (!table.getClientRects().length) continue;
    const rows = Array.from(table.rows).filter((row) => row.getClientRects().length).map((row) =>
      Array.from(row.cells).map((cell) => cell.querySelector("table") ? "" : text(cell))
    );
    const lifetime = rows.filter(([label]) => lifetimeLabel.test(label));
    if (lifetime.some(([label]) => /revenue \(gross\)/i.test(label)) &&
        lifetime.some(([label]) => /steam units/i.test(label))) {
      reports.lifetime = lifetime.map(([label, value, note]) =>
        ({ label, value: value || null, note: note || null }));
    }

    const selected = rows.filter(([label]) => selectedLabel.test(label));
    if (selected.some(([label]) => /^steam units$/i.test(label)) &&
        selected.some(([label]) => /^steam revenue$/i.test(label))) {
      const firstMetric = rows.findIndex(([label]) => selectedLabel.test(label));
      const period = rows.slice(0, firstMetric)
        .map((row) => row[2]).filter(Boolean).at(-1) || null;
      reports.selected = {
        period, rows: selected.map(([label, , value]) => ({ label, value: value || null }))
      };
    }
  }

  if (!reports.lifetime || !reports.selected) {
    return { status: "report_structure_missing", appId };
  }
  return { status: "ok", appId, ...reports };
})()
