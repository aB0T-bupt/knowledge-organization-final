"""Offline, transit-sign-inspired views of the executed SPARQL results."""

from collections import defaultdict
from html import escape


def line_sign(name):
    number = name.split("号", 1)[0]
    return (f'<span class="line-name"><span class="line line-{escape(number)}" '
            f'aria-hidden="true">{escape(number)}</span>{escape(name)}</span>')


def line_index(rows, station_order):
    by_station = defaultdict(list)
    for _, station, attraction in rows:
        by_station[station].append(attraction)
    stops = []
    for station in station_order:
        if station in by_station:
            places = "".join(f"<li>{escape(name)}</li>" for name in by_station[station])
            stops.append(f'<li class="station"><strong>{escape(station)}</strong>'
                         f'<ul>{places}</ul></li>')
    return ('<div class="section-head"><h2>' + line_sign(rows[0][0]) +
            f'</h2><span>沿线 {len(by_station)} 个下车站</span></div>'
            '<ol class="stations line-1">' + "".join(stops) + "</ol>")


def transfer_boards(rows):
    by_transfer = defaultdict(list)
    for _, _, transfer, second, arrival, attraction in rows:
        by_transfer[transfer, second].append((arrival, attraction))
    boards = []
    for (transfer, second), places in by_transfer.items():
        number = second.split("号", 1)[0]
        destinations = "".join(
            f'<li><span class="arrival">{escape(arrival)}</span>'
            f'<span>{escape(attraction)}</span></li>'
            for arrival, attraction in places
        )
        boards.append(f'<article class="board line-{escape(number)}">'
                      f'<h3>{escape(transfer)} <span aria-hidden="true">→</span>'
                      f'{line_sign(second)}</h3>'
                      f'<ul class="destinations">{destinations}</ul></article>')
    return ('<div class="section-head"><h2>北京站出发 · 首乘 ' +
            line_sign(rows[0][1]) + f'</h2><span>{len(by_transfer)} 个换乘站</span></div>'
            '<div class="boards">' + "".join(boards) + "</div>")


def render_result(path, rows, graph_size, station_order):
    index = path.stem == "01-line-attractions"
    title = "沿线寻景" if index else "一换即达"
    description = ("1号线八通线 · 景点与下车站" if index
                   else "北京站 · 样本内恰好换乘一次")
    first_current, second_current = (' aria-current="page"', "") if index else ("", ' aria-current="page"')
    content = line_index(rows, station_order) if index else transfer_boards(rows)
    path.write_text(f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}｜北京地铁景点导览</title>
<link rel="stylesheet" href="metro.css">
</head>
<body><main>
<nav aria-label="导览查询">
<a href="01-line-attractions.html"{first_current}>沿线景点</a>
<a href="02-one-transfer.html"{second_current}>一次换乘</a>
</nav>
<header><h1>{title}</h1><p class="meta">{description}</p></header>
{content}
<footer>SPARQL 实跑 · {len(rows)} 条结果 · {graph_size} 条 RDF 三元组 ·
<a href="{path.stem}.csv">完整结果 CSV</a> ·
<a href="../queries/{path.stem}.rq">查看查询代码</a></footer>
</main></body></html>
""", encoding="utf-8")
