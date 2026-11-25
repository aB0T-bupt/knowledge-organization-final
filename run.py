"""Build the RDF graph, run the SPARQL queries and export their result views."""

import csv
import json
from html import escape
from pathlib import Path
from urllib.parse import quote

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, XSD

ROOT = Path(__file__).resolve().parent
KG = Namespace("https://w3id.org/beijing-metro-course/schema/")
ID = Namespace("https://w3id.org/beijing-metro-course/id/")
METRO = URIRef("https://www.bjsubway.com/station/xltcx/")
SOURCES = {
    "guide": URIRef("https://focacsummit.mfa.gov.cn/hyfw/201807/t20180712_5860770.htm"),
    "rail-guide": URIRef("https://zdzqgw.beijing.gov.cn/zqfw/cxzn/202310/t20231012_3275952.html"),
}
CLASSES = {
    "Entity": ("领域实体", None),
    "Line": ("地铁线路", "Entity"),
    "Station": ("地铁站", "Entity"),
    "Attraction": ("景点", "Entity"),
    "Museum": ("博物馆", "Attraction"),
    "HeritageSite": ("历史地标", "Attraction"),
    "Park": ("公园", "Attraction"),
    "HistoricStreet": ("历史或商业街区", "Attraction"),
    "CulturalVenue": ("文化场馆", "Attraction"),
}
PROPERTIES = {
    "onLine": ("属于线路", KG.Station, KG.Line),
    "nextTo": ("相邻站", KG.Station, KG.Station),
    "servedBy": ("下车站", KG.Attraction, KG.Station),
}


def build_graph():
    graph = Graph()
    graph.bind("kg", KG)
    graph.bind("id", ID)
    graph.bind("dcterms", DCTERMS)
    graph.add((URIRef(str(KG)), RDF.type, OWL.Ontology))

    for name, (label, parent) in CLASSES.items():
        graph.add((KG[name], RDF.type, OWL.Class))
        graph.add((KG[name], RDFS.label, Literal(label, lang="zh")))
        if parent:
            graph.add((KG[name], RDFS.subClassOf, KG[parent]))

    for name, (label, domain, range_) in PROPERTIES.items():
        graph.add((KG[name], RDF.type, OWL.ObjectProperty))
        graph.add((KG[name], RDFS.label, Literal(label, lang="zh")))
        graph.add((KG[name], RDFS.domain, domain))
        graph.add((KG[name], RDFS.range, range_))
    graph.add((KG.nextTo, RDF.type, OWL.SymmetricProperty))
    graph.add((KG.isLoop, RDF.type, OWL.DatatypeProperty))
    graph.add((KG.isLoop, RDFS.domain, KG.Line))
    graph.add((KG.isLoop, RDFS.range, XSD.boolean))

    stations = {}
    lines = json.loads((ROOT / "data/lines.json").read_text(encoding="utf-8"))
    for number, label, loop, sequence in lines:
        line = ID[f"line-{number}"]
        graph.add((line, RDF.type, KG.Line))
        graph.add((line, RDFS.label, Literal(label, lang="zh")))
        graph.add((line, DCTERMS.source, METRO))
        graph.add((line, KG.isLoop, Literal(loop)))
        names = sequence.split()
        assert len(names) == len(set(names)), f"重复站点 {label}"
        ordered = []
        for name in names:
            station = stations.setdefault(name, ID[f"station-{quote(name)}"])
            graph.add((station, RDF.type, KG.Station))
            graph.add((station, RDFS.label, Literal(name, lang="zh")))
            graph.add((station, KG.onLine, line))
            ordered.append(station)
        if loop:
            ordered.append(ordered[0])
        for left, right in zip(ordered, ordered[1:]):
            graph.add((left, KG.nextTo, right))
            graph.add((right, KG.nextTo, left))

    seen = set()
    with (ROOT / "data/attractions.tsv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            key = row["id"]
            category = row["type"]
            assert key not in seen and CLASSES[category][1] == "Attraction", row
            seen.add(key)
            attraction = ID[f"poi-{key}"]
            graph.add((attraction, RDF.type, KG.Attraction))
            graph.add((attraction, RDF.type, KG[category]))
            graph.add((attraction, RDFS.label, Literal(row["name"], lang="zh")))
            graph.add((attraction, KG.servedBy, stations[row["station"]]))
            graph.add((attraction, DCTERMS.source, SOURCES[row["source"]]))
    return graph


def validate_graph(graph):
    entities = {kind: set(graph.subjects(RDF.type, KG[kind]))
                for kind in ("Station", "Line", "Attraction")}
    assert sum(map(len, entities.values())) == len(set.union(*entities.values()))
    links = {}
    for name, (_, domain, range_) in PROPERTIES.items():
        pairs = set(graph.subject_objects(KG[name]))
        assert all(left in entities[domain.split("/")[-1]]
                   and right in entities[range_.split("/")[-1]]
                   for left, right in pairs)
        if name == "nextTo":
            assert all(left != right and (right, left) in pairs for left, right in pairs)
            assert all(set(graph.objects(left, KG.onLine)) &
                       set(graph.objects(right, KG.onLine)) for left, right in pairs)
            links[name] = len(pairs) // 2
        else:
            links[name] = len(pairs)
    assert sum(map(len, entities.values())) >= 50 and sum(links.values()) >= 100
    for line in entities["Line"]:
        remaining = set(graph.subjects(KG.onLine, line))
        frontier = [remaining.pop()]
        while frontier:
            neighbors = remaining.intersection(graph.objects(frontier.pop(), KG.nextTo))
            remaining.difference_update(neighbors)
            frontier.extend(neighbors)
        assert not remaining, f"线路子图不连通 {line}"
    return {kind: len(items) for kind, items in entities.items()}, links


def render_result(path, title, columns, rows, graph_size):
    headings = "".join(f"<th>{escape(col)}</th>" for col in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    path.write_text(f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>{escape(title)}</title>
<style>
* {{box-sizing:border-box}} body {{margin:0;background:#f0f5f7;color:#173043;
font:16px 'Microsoft YaHei','Noto Sans SC',sans-serif}}
main {{margin:32px auto;width:calc(100% - 80px);max-width:1240px;background:white;
border:1px solid #d2e1e7;border-radius:12px;overflow:hidden}}
header {{padding:25px 30px;background:#12394a;color:white}} h1 {{margin:0 0 10px;font-size:27px}}
header p {{margin:0;color:#bce5e4}} table {{border-collapse:collapse;width:100%}}
th, td {{padding:9px 13px;text-align:left;border-bottom:1px solid #e8eff1}}
th {{background:#def0ef}} tr:nth-child(even) {{background:#f5fafb}}
</style><main><header><h1>{escape(title)}</h1><p>SPARQL 执行结果 · RDFLib ·
{len(rows)} 行 · RDF 图 {graph_size} 条三元组</p></header>
<table><thead><tr>{headings}</tr></thead><tbody>{body}</tbody></table></main></html>""",
                    encoding="utf-8")


def main():
    graph = build_graph()
    entities, links = validate_graph(graph)
    graph.serialize(ROOT / "北京地铁知识图谱.rdf", format="pretty-xml")
    reloaded = Graph().parse(ROOT / "北京地铁知识图谱.rdf", format="xml")
    assert set(graph) == set(reloaded)
    output = ROOT / "results"
    output.mkdir(exist_ok=True)

    specs = [
        ("01-line-attractions", "查询一 · 1号线八通线景点索引",
         ("线路", "下车站", "景点")),
        ("02-one-transfer", "查询二 · 从北京站出发，恰好一次换乘",
         ("起点", "首乘线路", "换乘站", "次乘线路", "下车站", "景点")),
    ]
    results = {}
    for stem, title, columns in specs:
        query = (ROOT / f"queries/{stem}.rq").read_text(encoding="utf-8")
        rows = [tuple(map(str, row)) for row in reloaded.query(query)]
        results[stem] = rows
        with (output / f"{stem}.csv").open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream)
            writer.writerow(columns)
            writer.writerows(rows)
        render_result(output / f"{stem}.html", title, columns, rows, len(reloaded))
        print(f"{stem}: {len(rows)} rows")

    first, second = results.values()
    assert len(first) == 10 and len(second) == 26
    assert len({row[-1] for row in second}) == 13
    assert ("1号线八通线", "天安门东", "故宫博物院") in first
    assert ("北京站", "2号线", "崇文门", "5号线", "天坛东门", "天坛公园") in second
    assert ("北京站", "2号线", "朝阳门", "6号线", "南锣鼓巷", "南锣鼓巷") in second
    assert {"前门大街", "雍和宫", "北京古观象台"}.isdisjoint(row[-1] for row in second)
    print(f"Entities: {entities}; logical links: {links}; RDF triples: {len(reloaded)}")


if __name__ == "__main__":
    main()
