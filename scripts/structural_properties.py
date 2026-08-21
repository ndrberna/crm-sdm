#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
structural_properties.py
=========================================================================
Independent structural / topological verification for the CRM-SDM
instantiated graph (https://w3id.org/crm-sdm).

This script reproduces, from the released Turtle file alone, every
number quoted in the "Structural Properties of the Instantiated Graph"
subsection of the CRM-SDM paper: network size and density, degree
distribution, connectivity (weak and strong components), diameter,
average shortest-path length, clustering coefficient, and multi-hop
reachability of the target economy. It also re-derives the
StableCriticalIntermediary extension directly from the four defined-
class conjuncts (Manchester syntax, Section 7 of the paper) using plain
graph traversal, as an independent check against the OWL reasoner
(HermiT) and the equivalent SPARQL query already released with the
ontology. All three routes are expected to agree on the same
extension; this script is the third, dependency-light route, requiring
only rdflib and networkx (no OWL reasoner).

Usage
-----
    pip install rdflib networkx
    python structural_properties.py path/to/crmsdmkg.ttl

If no path is given, it defaults to "crmsdmkg.ttl" in the current
directory. Pass --json report.json to additionally dump a machine-
readable summary.

Design notes
------------
- The analysis is restricted to sdm:Trader individuals connected by
  sdm:suppliesTo. Schema, provenance and metadata triples are excluded
  on purpose: they are not part of the economic network and would
  distort any topological reading (see the paper's Section 5 on why
  trade flows are reified as first-class objects rather than as plain
  edges).
- Governance and elasticity thresholds (0.5 / 0.5) are read from the
  ontology's own defined classes (FavorableGovernanceCountry,
  StableCriticalIntermediary, Section 7) and are kept as named
  constants below so a threshold change in the TBox can be mirrored
  here with a one-line edit rather than by re-deriving the value.
- All shortest-path / component computations are exact (not sampled):
  with 192 nodes this is cheap, so no approximation is needed.
=========================================================================
"""

import argparse
import json
import statistics
import sys
from collections import Counter

import networkx as nx
import rdflib
from rdflib import RDF, Namespace

SDM = Namespace("https://w3id.org/crm-sdm#")

# Thresholds asserted by the two OWL defined classes (Section 7 of the paper).
# Kept here as named constants purely for readability of this script;
# the ontology's own axioms remain the normative source of truth.
GOVERNANCE_THRESHOLD = 0.5   # FavorableGovernanceCountry: wgiCompositeScore >= 0.5
ELASTICITY_THRESHOLD = 0.5   # StableCriticalIntermediary: nodalElasticity >= 0.5


def qn(uri, ns=SDM):
    """Shorten an sdm: URI to its local name for readable output."""
    s = str(uri)
    return s[len(str(ns)):] if s.startswith(str(ns)) else s


def load_graph(path):
    g = rdflib.Graph()
    g.parse(path, format="turtle")
    return g


def build_trader_network(g):
    """Build the directed Trader--suppliesTo network.

    Returns (DiGraph, emp_set, syn_set). Nodes are restricted to
    individuals explicitly typed as EmpiricalTrader or SyntheticTrader
    (the two disjoint subclasses of Trader), matching the population
    the paper reports (Section 6: "192 traders, of which 6 are
    empirical and 186 synthetic").
    """
    emp = set(g.subjects(RDF.type, SDM.EmpiricalTrader))
    syn = set(g.subjects(RDF.type, SDM.SyntheticTrader))
    traders = emp | syn

    dg = nx.DiGraph()
    dg.add_nodes_from(traders)
    for s, o in g.subject_objects(SDM.suppliesTo):
        if s in traders and o in traders:
            dg.add_edge(s, o)
    return dg, emp, syn


def size_and_density(dg):
    n, m = dg.number_of_nodes(), dg.number_of_edges()
    density = m / (n * (n - 1)) if n > 1 else 0.0
    return {"nodes": n, "edges": m, "density": round(density, 5)}


def degree_stats(dg):
    indeg = [d for _, d in dg.in_degree()]
    outdeg = [d for _, d in dg.out_degree()]
    m = dg.number_of_edges()

    sorted_out = sorted(outdeg, reverse=True)
    top_decile_n = max(1, len(sorted_out) // 10)
    top_decile_edge_share = sum(sorted_out[:top_decile_n]) / m if m else 0.0

    return {
        "in_degree": {
            "mean": round(statistics.mean(indeg), 2),
            "median": statistics.median(indeg),
            "max": max(indeg),
            "min": min(indeg),
        },
        "out_degree": {
            "mean": round(statistics.mean(outdeg), 2),
            "median": statistics.median(outdeg),
            "max": max(outdeg),
            "min": min(outdeg),
        },
        "pure_sinks_out_degree_zero": sum(1 for d in outdeg if d == 0),
        "pure_sources_in_degree_zero": sum(1 for d in indeg if d == 0),
        "top_decile_out_degree_node_count": top_decile_n,
        "top_decile_out_degree_edge_share": round(top_decile_edge_share, 4),
    }


def connectivity_stats(dg):
    ug = dg.to_undirected()
    wccs = list(nx.connected_components(ug))
    giant = max(wccs, key=len)

    sccs = sorted(nx.strongly_connected_components(dg), key=len, reverse=True)
    scc_size_hist = Counter(len(s) for s in sccs)

    result = {
        "weakly_connected_components": len(wccs),
        "giant_wcc_size": len(giant),
        "giant_wcc_fraction": round(len(giant) / dg.number_of_nodes(), 4),
        "strongly_connected_components": len(sccs),
        "largest_scc_size": len(sccs[0]),
        "scc_size_histogram": dict(scc_size_hist),
    }

    sub = ug.subgraph(giant)
    if nx.is_connected(sub):
        result["giant_component_diameter_undirected"] = nx.diameter(sub)
        result["giant_component_avg_shortest_path_undirected"] = round(
            nx.average_shortest_path_length(sub), 3
        )
    result["average_clustering_undirected"] = round(nx.average_clustering(ug), 4)
    return result


def target_economy_reachability(g, dg):
    """Hop-distance from every trader to the closest trader located in
    the TargetEconomy country, following suppliesTo forward (i.e.
    distance = shortest supply path length into the target economy).
    """
    target_countries = set(g.subjects(RDF.type, SDM.TargetEconomy))
    if not target_countries:
        raise ValueError("No sdm:TargetEconomy individual found in the graph.")
    target_country = next(iter(target_countries))

    loc = dict(g.subject_objects(SDM.locatedIn))
    target_traders = {t for t, c in loc.items() if c == target_country and t in dg}

    rg = dg.reverse(copy=True)
    dist = {}
    for tt in target_traders:
        for node, d in nx.single_source_shortest_path_length(rg, tt).items():
            if node not in dist or d < dist[node]:
                dist[node] = d

    reachable = {k: v for k, v in dist.items() if k not in target_traders}
    hop_hist = Counter(reachable.values())
    n_total = dg.number_of_nodes() - len(target_traders)

    return {
        "target_country": qn(target_country),
        "target_traders": [qn(t) for t in target_traders],
        "non_target_traders": n_total,
        "reachable_any_hop": len(reachable),
        "direct_1_hop": hop_hist.get(1, 0),
        "indirect_2plus_hop": sum(v for h, v in hop_hist.items() if h >= 2),
        "hop_histogram": dict(sorted(hop_hist.items())),
        "unreachable": n_total - len(reachable),
        "_distances": dist,  # kept for reuse by the StableCriticalIntermediary check below
    }


def favorable_governance_countries(g):
    """Re-derive FavorableGovernanceCountry: Country with composite
    governance score >= GOVERNANCE_THRESHOLD, via
    Country -> hasGeopoliticalRisk -> GeopoliticalRiskIndicator -> wgiCompositeScore.
    """
    country_gov = {}
    for country, risk_ind in g.subject_objects(SDM.hasGeopoliticalRisk):
        for score in g.objects(risk_ind, SDM.wgiCompositeScore):
            country_gov[country] = float(score)
    favorable = {c for c, v in country_gov.items() if v >= GOVERNANCE_THRESHOLD}
    return country_gov, favorable


def stable_critical_intermediary_check(g, dg, dist_to_target):
    """Independent, reasoner-free re-derivation of the
    StableCriticalIntermediary defined class:

        Trader
        and (nodalElasticity some xsd:decimal[>= 0.5])
        and (locatedIn some FavorableGovernanceCountry)
        and (inverse(suppliesTo) some Trader)
        and (suppliesToTransitively some
             (Trader and (locatedIn some TargetEconomy)))

    The fourth conjunct (transitive reachability to a trader located in
    the target economy) is exactly the multi-hop reachability computed
    in target_economy_reachability(): a trader qualifies on this
    conjunct iff it appears as a key in dist_to_target (any finite hop
    count, direct or indirect).
    """
    ne = {s: float(o) for s, o in g.subject_objects(SDM.nodalElasticity)}
    high_elastic = {k: v for k, v in ne.items() if v >= ELASTICITY_THRESHOLD}

    _, favorable_countries = favorable_governance_countries(g)
    trader_country = dict(g.subject_objects(SDM.locatedIn))

    rows = []
    for trader, elasticity in sorted(high_elastic.items(), key=lambda kv: -kv[1]):
        country = trader_country.get(trader)
        favorable_gov = country in favorable_countries if country else False
        has_upstream = dg.in_degree(trader) > 0 if trader in dg else False
        reaches_target = trader in dist_to_target
        hops = dist_to_target.get(trader)
        qualifies = bool(favorable_gov and has_upstream and reaches_target)
        rows.append(
            {
                "trader": qn(trader),
                "nodal_elasticity": round(elasticity, 4),
                "country": qn(country) if country else None,
                "favorable_governance_country": favorable_gov,
                "has_upstream_supplier": has_upstream,
                "reaches_target_economy": reaches_target,
                "hops_to_target": hops,
                "qualifies_StableCriticalIntermediary": qualifies,
            }
        )
    return rows


def print_report(size, degrees, connectivity, reach, sci_rows):
    def section(title):
        print("\n" + "=" * 72)
        print(title)
        print("=" * 72)

    section("1. Network size and density")
    print(f"  Trader nodes           : {size['nodes']}")
    print(f"  suppliesTo edges       : {size['edges']}")
    print(f"  Density                : {size['density']}")

    section("2. Degree distribution")
    d = degrees
    print(f"  In-degree  mean/median/max/min : "
          f"{d['in_degree']['mean']}/{d['in_degree']['median']}/"
          f"{d['in_degree']['max']}/{d['in_degree']['min']}")
    print(f"  Out-degree mean/median/max/min : "
          f"{d['out_degree']['mean']}/{d['out_degree']['median']}/"
          f"{d['out_degree']['max']}/{d['out_degree']['min']}")
    print(f"  Pure sinks (out-degree 0)      : {d['pure_sinks_out_degree_zero']}")
    print(f"  Pure sources (in-degree 0)     : {d['pure_sources_in_degree_zero']}")
    print(f"  Top-decile out-degree edge share ({d['top_decile_out_degree_node_count']} nodes): "
          f"{d['top_decile_out_degree_edge_share']:.1%}")

    section("3. Connectivity")
    c = connectivity
    print(f"  Weakly connected components    : {c['weakly_connected_components']}")
    print(f"  Giant WCC size                 : {c['giant_wcc_size']} "
          f"({c['giant_wcc_fraction']:.1%} of nodes)")
    print(f"  Strongly connected components  : {c['strongly_connected_components']}")
    print(f"  Largest SCC size               : {c['largest_scc_size']}")
    print(f"  SCC size histogram             : {c['scc_size_histogram']}")
    if "giant_component_diameter_undirected" in c:
        print(f"  Diameter (undirected)          : {c['giant_component_diameter_undirected']}")
        print(f"  Avg. shortest path (undirected): {c['giant_component_avg_shortest_path_undirected']}")
    print(f"  Avg. clustering coefficient    : {c['average_clustering_undirected']}")

    section("4. Reachability to the target economy")
    print(f"  Target economy country         : {reach['target_country']}")
    print(f"  Traders located in target      : {reach['target_traders']}")
    print(f"  Non-target traders             : {reach['non_target_traders']}")
    print(f"  Reach target (any hop)         : {reach['reachable_any_hop']}")
    print(f"  Direct (1 hop)                 : {reach['direct_1_hop']}")
    print(f"  Indirect (2+ hops)             : {reach['indirect_2plus_hop']}")
    print(f"  Hop histogram                  : {reach['hop_histogram']}")
    print(f"  Unreachable                    : {reach['unreachable']}")

    section("5. StableCriticalIntermediary — independent re-derivation")
    print(f"  {'trader':20s} {'elast.':>7s} {'country':10s} {'fav.gov':>8s} "
          f"{'upstr.':>7s} {'hops':>5s}  qualifies")
    for r in sci_rows:
        print(
            f"  {r['trader']:20s} {r['nodal_elasticity']:7.4f} "
            f"{(r['country'] or '-'):10s} {str(r['favorable_governance_country']):>8s} "
            f"{str(r['has_upstream_supplier']):>7s} "
            f"{str(r['hops_to_target']):>5s}  {r['qualifies_StableCriticalIntermediary']}"
        )
    n_qualify = sum(1 for r in sci_rows if r["qualifies_StableCriticalIntermediary"])
    print(f"\n  => StableCriticalIntermediary extension size: {n_qualify}")
    print("     (compare against the HermiT-inferred class extension and the")
    print("      equivalent SPARQL query released with the ontology; all three")
    print("      routes are expected to return the same set of traders.)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ttl_path", nargs="?", default="../kg/crm-sdm-kg.ttl",
                         help="Path to the instantiated CRM-SDM Turtle graph.")
    parser.add_argument("--json", metavar="PATH", default=None,
                         help="Optional path to also dump a JSON summary.")
    args = parser.parse_args()

    try:
        g = load_graph(args.ttl_path)
    except FileNotFoundError:
        print(f"error: could not find '{args.ttl_path}'", file=sys.stderr)
        sys.exit(1)

    dg, emp, syn = build_trader_network(g)
    print(f"Loaded {len(g)} triples. Trader population: "
          f"{len(emp)} empirical + {len(syn)} synthetic = {len(emp) + len(syn)}.")

    size = size_and_density(dg)
    degrees = degree_stats(dg)
    connectivity = connectivity_stats(dg)
    reach = target_economy_reachability(g, dg)
    sci_rows = stable_critical_intermediary_check(g, dg, reach["_distances"])

    print_report(size, degrees, connectivity, reach, sci_rows)

    if args.json:
        summary = {
            "size_and_density": size,
            "degree_stats": degrees,
            "connectivity": connectivity,
            "target_economy_reachability": {
                k: v for k, v in reach.items() if k != "_distances"
            },
            "stable_critical_intermediary_check": sci_rows,
        }
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"\nJSON summary written to {args.json}")


if __name__ == "__main__":
    main()
