"""Vuelve a pasar solo los pasos de código de una etapa que el modelo ya hizo, y la da por terminada. Sirve cuando un
paso «tras» falló por una regla que se ha corregido: no hace falta gastar otra vez el modelo.

  hyt_repasar.py <canal> <encargo> <etapa>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hyt_encargos as E  # noqa: E402
import hyt_etapa as ET  # noqa: E402
import hyt_pipelines as PL  # noqa: E402


def repasar(slug: str, eid: str, etapa: str) -> dict:
    enc, d = E.leer(slug, eid), E.carpeta(slug, eid)
    s = next((x for x in PL.cargar(enc["pipeline"], slug)["etapas"] if x["id"] == etapa), None)
    if not s:
        return {"outcome": "failed", "reason": f"la etapa {etapa} no es de este encargo"}
    salida = s.get("salida") or f"{etapa}.md"
    if not (d / salida).exists():
        return {"outcome": "failed", "reason": f"la etapa no dejó {salida}: no hay nada que repasar"}
    res = {"outcome": "done", "salida": salida, "ejecutor": "codigo", "modelo": ""}
    for nombre in s.get("tras") or []:
        try:
            r = ET.tras(slug, d, nombre, enc)
        except ET.B.Rechazo as e:
            r = {"fallo": str(e)}
        if r.get("fallo"):
            res = {**res, "outcome": "failed", "reason": r["fallo"]}
            break
        if r.get("resumen"):
            res["resumen"] = r["resumen"]
    return ET.fin(slug, eid, etapa, res, time.time())


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    print(json.dumps(repasar(*sys.argv[1:4]), ensure_ascii=False))
