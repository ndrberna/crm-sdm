#!/usr/bin/env python3
"""
build_graph.py — costruisce kg/crm-sdm-kg.ttl da ABox + TBox.

Perche' esiste
--------------
Il file caricabile in Protege' e' l'unione di ontology/crm-sdm.ttl e
data/crm-sdm-abox.ttl. Per tre volte, nel corso dello sviluppo, una
modifica e' stata applicata direttamente a quel file unito invece che a
una delle due sorgenti. L'ultima e' costata cara: il TBox nel file unito
conteneva ancora la vecchia restrizione di StableCriticalIntermediary
mentre ontology/crm-sdm.ttl aveva quella nuova, e il file spedito
classificava la classe come VUOTA senza segnalare nulla — il reasoner
resta coerente, semplicemente non trova piu' niente.

Regola: kg/crm-sdm-kg.ttl e' un PRODOTTO. Non va mai modificato a mano.
Si modifica il TBox oppure l'ABox, e si rilancia questo script.

Uso
---
    python3 scripts/build_graph.py
    python3 scripts/build_graph.py --check      # verifica soltanto
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import rdflib
from rdflib import RDF, OWL

SDM = rdflib.Namespace("https://w3id.org/crm-sdm#")

# conteggi sui tipi ASSERITI. sdm:Trader non compare: i trader sono
# asseriti come sintetici o empirici e la sussunzione la fa il reasoner.
EXPECTED = {"SyntheticTrader": 186, "EmpiricalTrader": 6, "Country": 154,
            "TradeFlow": 5568, "TargetEconomy": 1, "CriticalRawMaterial": 1,
            "DownscalingActivity": 1}


import os as _os

# I percorsi di default sono ancorati alla radice del repository, non
# alla directory da cui si lancia il comando: cosi' lo script funziona
# sia da "python3 scripts/build_graph.py" sia da dentro scripts/.
# Un percorso passato esplicitamente resta relativo alla directory
# corrente, come ci si aspetta.
ROOT = pathlib.Path(__file__).resolve().parent.parent
def _d(rel): return str(ROOT / rel)

# i percorsi di default sono relativi alla radice del repository, non alla
# directory da cui si lancia il comando: cosi' lo script funziona sia da
# `python3 scripts/build_graph.py` sia da dentro scripts/.
_os.chdir(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tbox", default=_d("ontology/crm-sdm.ttl"))
    ap.add_argument("--abox", default=_d("data/crm-sdm-abox.ttl"))
    ap.add_argument("--out", default=_d("kg/crm-sdm-kg.ttl"))
    ap.add_argument("--check", action="store_true",
                    help="verifica che --out sia allineato, senza riscriverlo")
    args = ap.parse_args()

    T = rdflib.Graph(); T.parse(args.tbox, format="turtle")
    A = rdflib.Graph(); A.parse(args.abox, format="turtle")

    # l'ABox non deve contenere assiomi di schema: sarebbero una copia
    # che diverge silenziosamente dal TBox
    schema = [s for s in set(A.subjects()) if s in set(T.subjects())
              and not isinstance(s, rdflib.BNode)]
    if schema:
        sys.exit("L'ABox contiene soggetti dichiarati anche nel TBox: "
                 + ", ".join(str(s).rsplit("#", 1)[-1] for s in schema[:8])
                 + "\nSpostare quegli assiomi nel TBox ed eliminarli dall'ABox.")

    M = rdflib.Graph()
    for pfx, ns in list(A.namespaces()) + list(T.namespaces()):
        M.bind(pfx, ns)
    for t in A:
        M.add(t)
    for t in T:
        M.add(t)

    counts = {n: len(set(M.subjects(RDF.type, SDM[n]))) for n in EXPECTED}
    bad = {n: (counts[n], e) for n, e in EXPECTED.items() if counts[n] != e}
    print(f"TBox {len(T)} + ABox {len(A)}  ->  {len(M)} triple")
    for n, e in EXPECTED.items():
        flag = "" if counts[n] == e else f"   <-- atteso {e}"
        print(f"  {n:20}{counts[n]:>7}{flag}")
    tot = counts["SyntheticTrader"] + counts["EmpiricalTrader"]
    print(f"  {'(traders, totale)':20}{tot:>7}" + ("" if tot == 192 else "   <-- atteso 192"))
    n_eq = len(list(M.objects(SDM.StableCriticalIntermediary, OWL.equivalentClass)))
    print(f"  assiomi di equivalenza su StableCriticalIntermediary: {n_eq}"
          + ("   <-- devono essere 1: due copie divergenti" if n_eq != 1 else ""))
    if bad or n_eq != 1 or tot != 192:
        sys.exit("Costruzione interrotta: il grafo non ha la forma attesa.")

    if args.check:
        try:
            C = rdflib.Graph(); C.parse(args.out, format="turtle")
        except Exception as e:
            sys.exit(f"Impossibile leggere {args.out}: {e}")
        same = len(C) == len(M)
        print(f"\n{args.out}: {len(C)} triple — "
              + ("allineato." if same else "DISALLINEATO, rilanciare senza --check."))
        sys.exit(0 if same else 1)

    M.serialize(args.out, format="turtle")
    print(f"\nScritto {args.out}")
    print("Ricordarsi di rieseguire il reasoner e le shape dopo ogni build.")


if __name__ == "__main__":
    main()