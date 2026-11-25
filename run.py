"""Build the RDF graph, run the SPARQL queries and export their result views."""

import csv
import json
import re
from pathlib import Path
from urllib.parse import quote

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, XSD

from report_ui import render_result

ROOT = Path(__file__).resolve().parent
KG = Namespace("https://w3id.org/beijing-metro-course/schema/")
ID = Namespace("https://w3id.org/beijing-metro-course/id/")
METRO = URIRef("https://maps.gaode.com/ssr/subway/beijing-1100")
T1_SOURCE = URIRef("https://www.mtr.bj.cn/service/line/distable/Yizhuang%20T1%20Line.html")
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
        graph.add((line, DCTERMS.source, T1_SOURCE if number == "t1" else METRO))
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
        if number == 'capital-airport':
            # The airport end has a terminal loop joined at Sanyuanqiao.
            left, right = stations['三元桥'], stations['3号航站楼']
            graph.add((left, KG.nextTo, right))
            graph.add((right, KG.nextTo, left))
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


def main():
    graph = build_graph()
    entities, links = validate_graph(graph)
    graph.serialize(ROOT / "北京地铁知识图谱.rdf", format="pretty-xml")
    reloaded = Graph().parse(ROOT / "北京地铁知识图谱.rdf", format="xml")
    assert set(graph) == set(reloaded)
    output = ROOT / "results"
    output.mkdir(exist_ok=True)

    specs = [
        ("01-line-attractions",
         ("线路", "下车站", "景点")),
        ("02-one-transfer",
         ("起点", "首乘线路", "换乘站", "次乘线路", "下车站", "景点")),
    ]
    results = {}
    explorer = {'index': [], 'transfer': []}
    lines = json.loads((ROOT / 'data/lines.json').read_text(encoding='utf-8'))
    station_order = next(sequence.split() for number, _, _, sequence in lines if number == '1')
    for stem, columns in specs:
        query = (ROOT / f"queries/{stem}.rq").read_text(encoding="utf-8")
        rows = [tuple(map(str, row)) for row in reloaded.query(query)]
        results[stem] = rows
        all_query, parameter_count = re.subn(r'^  VALUES .*\n', '', query, count=1, flags=re.M)
        assert parameter_count == 1
        key = 'index' if stem.startswith('01') else 'transfer'
        explorer[key] = [tuple(map(str, row)) for row in reloaded.query(all_query)]
        with (output / f"{stem}.csv").open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream)
            writer.writerow(columns)
            writer.writerows(rows)
        render_result(output / f"{stem}.html", rows, len(reloaded), station_order)
        print(f"{stem}: {len(rows)} rows")

    explorer['lines'] = [(label, sequence.split()) for _, label, _, sequence in lines]
    (output / 'network-data.js').write_text('window.metro = ' + json.dumps(explorer, ensure_ascii=False) + ';\n', encoding='utf-8')
    first, second = results.values()
    assert entities["Line"] == 28 and len(first) == 10
    print("Transfer destinations:", len({row[-1] for row in second}))
    assert ("1号线八通线", "天安门东", "故宫博物院") in first
    assert ("北京站", "2号线", "崇文门", "5号线", "天坛东门", "天坛公园") in second
    assert ("北京站", "2号线", "朝阳门", "6号线", "南锣鼓巷", "南锣鼓巷") in second
    assert {"前门大街", "雍和宫", "北京古观象台"}.isdisjoint(row[-1] for row in second)
    assert sum(1 for row in explorer['transfer'] if row[0] == '北京站') == len(second)
    print(f"Entities: {entities}; logical links: {links}; RDF triples: {len(reloaded)}")


if __name__ == "__main__":
    main()
