#!/usr/bin/env python3
"""Fusiona tramos de name_recover.py en un indice con offsets absolutos.

Cada JSON de tramo guarda offsets relativos al bloque que se proceso; la base
viene en el nombre del archivo (`<rpf>__<offset>.json`). Aqui se les suma.

    python3 tools/merge_index.py <dir_tramos> <dir_salida>

Escribe streams.tsv, paths.tsv, ids.tsv y summary.json. Detecta tramos solapados
por archivo, que indican que dos corridas procesaron los mismos bytes.

Un stream cuenta como nombrado si trae rutas completas o identificadores, que es
el mismo criterio que usa tools/name_recover.py.
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict


def main():
    ap = argparse.ArgumentParser(description="Fusiona tramos de name_recover en un indice")
    ap.add_argument("tramos", help="carpeta con los JSON de cada tramo")
    ap.add_argument("salida", help="carpeta donde escribir el indice")
    ap.add_argument("--skip", default="", help="nombres separados por coma a descartar (tramos duplicados)")
    args = ap.parse_args()

    saltar = {s.strip() for s in args.skip.split(",") if s.strip()}
    if not os.path.isdir(args.tramos):
        sys.exit(f"no existe la carpeta {args.tramos}")
    os.makedirs(args.salida, exist_ok=True)

    trozos = []
    for nombre in sorted(os.listdir(args.tramos)):
        if not nombre.endswith(".json") or nombre in saltar:
            continue
        m = re.match(r"(.+?)__(\d+)\.json$", nombre)
        rpf, base = (m.group(1), int(m.group(2))) if m else (nombre[:-5], 0)
        trozos.append((os.path.join(args.tramos, nombre), rpf, base))

    if not trozos:
        sys.exit("no hay tramos que fusionar")

    fs = open(os.path.join(args.salida, "streams.tsv"), "w")
    fp = open(os.path.join(args.salida, "paths.tsv"), "w")
    fi = open(os.path.join(args.salida, "ids.tsv"), "w")
    fs.write("rpf\tabs_offset\toffset_hex\tcompressed\tinflated\ttype\tstatus\tn_paths\tn_ids\n")
    fp.write("ruta\trpf\tabs_offset\n")
    fi.write("identificador\trpf\tabs_offset\n")

    por_rpf = defaultdict(lambda: {"streams": 0, "named": 0, "rangos": []})
    por_tipo = defaultdict(lambda: [0, 0])
    rutas, ids = set(), set()
    total_streams = total_nombrados = 0

    for ruta, rpf, base in trozos:
        with open(ruta) as f:
            d = json.load(f)
        for st in d.get("streams", []):
            off = base + int(st.get("offset", 0))
            comp = int(st.get("compressed_bytes", 0) or 0)
            inf = int(st.get("inflated_bytes", 0) or 0)
            tipo = st.get("stream_type", "?")
            estado = st.get("status", "?")
            p = st.get("full_paths") or []
            i = st.get("identifiers") or []
            total_streams += 1
            por_tipo[tipo][0] += 1
            r = por_rpf[rpf]
            r["streams"] += 1
            r["rangos"].append((off, off + comp))
            if p or i:
                total_nombrados += 1
                por_tipo[tipo][1] += 1
                r["named"] += 1
                for x in p:
                    fp.write(f"{x}\t{rpf}\t{off}\n")
                    rutas.add(x)
                for x in i:
                    fi.write(f"{x}\t{rpf}\t{off}\n")
                    ids.add(x)
            fs.write(f"{rpf}\t{off}\t0x{off:x}\t{comp}\t{inf}\t{tipo}\t{estado}\t{len(p)}\t{len(i)}\n")

    for h in (fs, fp, fi):
        h.close()

    resumen = {"tramos": len(trozos), "streams": total_streams, "con_nombre": total_nombrados,
               "rutas_unicas": len(rutas), "ids_unicos": len(ids), "por_rpf": {}, "por_tipo": {},
               "solapes": []}
    for rpf, v in sorted(por_rpf.items(), key=lambda x: -x[1]["named"]):
        r = sorted(v["rangos"])
        sol = sum(1 for a, b in zip(r, r[1:]) if b[0] < a[1])
        if sol:
            resumen["solapes"].append({"rpf": rpf, "casos": sol})
        resumen["por_rpf"][rpf] = {"streams": v["streams"], "nombrados": v["named"], "solapes": sol}
    resumen["por_tipo"] = {t: {"total": a, "nombrados": b, "cobertura": round(b / max(1, a) * 100, 2)}
                           for t, (a, b) in sorted(por_tipo.items(), key=lambda x: -x[1][0])}
    with open(os.path.join(args.salida, "summary.json"), "w") as f:
        json.dump(resumen, f, indent=1, ensure_ascii=False)

    pct = total_nombrados / max(1, total_streams) * 100
    print(f"tramos      {len(trozos)}")
    print(f"streams     {total_streams:,}")
    print(f"con nombre  {total_nombrados:,} ({pct:.2f}%)")
    print(f"rutas       {len(rutas):,} unicas · ids {len(ids):,} unicos")
    if resumen["solapes"]:
        print(f"ATENCION: solapes en {len(resumen['solapes'])} archivos: {resumen['solapes']}")


if __name__ == "__main__":
    main()
