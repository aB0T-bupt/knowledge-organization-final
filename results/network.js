"use strict";

const { lines, index, transfer } = window.metro;
const mode = document.getElementById("mode");
const line = document.getElementById("line");
const station = document.getElementById("station");
const results = document.getElementById("matches");
const summary = document.getElementById("summary");
const stations = new Set(lines.flatMap(([, stops]) => stops));

for (const [name] of lines) line.add(new Option(name, name));
const options = document.getElementById("station-list");
for (const name of [...stations].sort((a, b) => a.localeCompare(b, "zh"))) {
  options.append(new Option(name, name));
}

function addRow(parent, first, second) {
  const row = document.createElement("li");
  row.className = "station";
  const label = document.createElement("strong");
  label.textContent = first;
  const value = document.createElement("span");
  value.textContent = second;
  row.append(label, value);
  parent.append(row);
}

function showResults() {
  const byLine = mode.value === "line";
  document.getElementById("line-field").hidden = !byLine;
  document.getElementById("station-field").hidden = byLine;
  const start = station.value.trim();
  results.replaceChildren();
  if (!byLine && !stations.has(start)) {
    summary.textContent = "请输入或从建议中选择一个运营站名。";
    return;
  }

  const rows = byLine
    ? index.filter(([name]) => name === line.value)
    : transfer.filter(([name]) => name === start);
  if (rows.length === 0) {
    summary.textContent = byLine ? "该线路暂无收录景点。" : "该起点暂无需要一次换乘的已收录景点。";
    return;
  }

  const list = document.createElement("ol");
  list.className = "stations";
  if (byLine) {
    const order = lines.find(([name]) => name === line.value)[1];
    const byStop = new Map();
    for (const [, stop, name] of rows) {
      if (!byStop.has(stop)) byStop.set(stop, []);
      byStop.get(stop).push(name);
    }
    for (const stop of order) {
      if (byStop.has(stop)) addRow(list, stop, byStop.get(stop).join("、"));
    }
    summary.textContent = `${rows.length} 个景点 · ${byStop.size} 个下车站`;
  } else {
    for (const [, first, change, second, arrival, name] of rows) {
      addRow(list, name, `${first} → ${change}换乘 → ${second} → ${arrival}下车`);
    }
    summary.textContent = `${rows.length} 个方案 · ${new Set(rows.map(row => row[5])).size} 个景点`;
  }
  results.append(list);
}

mode.addEventListener("change", showResults);
line.addEventListener("change", showResults);
station.addEventListener("input", showResults);
showResults();
