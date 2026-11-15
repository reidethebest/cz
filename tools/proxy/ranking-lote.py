#!/usr/bin/env python3
"""Prueba de golpe todos los proxys de las listas publicas contra el server (una parte por job de Actions).

Lee las URLs de AFK_PROXY_FUENTES, junta y saca repetidos, se queda con la parte --parte de --partes (por el id del
proxy, asi cada job prueba otros) y prueba cada uno con el tunel + ping de Minecraft de proxy-vigia.py. Los que
contestan se prueban --vueltas veces mas, separadas unos segundos, para descartar los que andan una sola vez.
Escribe en --salida: tipo://host:puerto TAB ms (mediana) TAB vueltas ok, ordenado (primero los que nunca fallaron,
despues por ping). En el log solo imprime cantidades.
"""
import argparse, importlib.util, os, statistics, sys, time
from concurrent.futures import ThreadPoolExecutor

aqui = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("vigia", os.path.join(aqui, "proxy-vigia.py"))
vg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vg)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--server", required=True)
    a.add_argument("--parte", type=int, default=0)
    a.add_argument("--partes", type=int, default=1)
    a.add_argument("--hilos", type=int, default=256)
    a.add_argument("--timeout", type=float, default=8)
    a.add_argument("--vueltas", type=int, default=3)
    a.add_argument("--salida", required=True)
    o = a.parse_args()
    fuentes = [u.strip() for u in os.environ.get("AFK_PROXY_FUENTES", "").split() if u.strip().startswith("http")]
    cand, leidas = {}, 0
    for u in fuentes:
        try:
            for px in vg.leer_fuente(u, "HTTP"):
                px["id"] = vg.pid(px)
                cand.setdefault(px["id"], px)
            leidas += 1
        except Exception:
            pass
    total = len(cand)
    mios = [px for k, px in sorted(cand.items()) if int(k[1:], 16) % o.partes == o.parte]
    dest = vg.srv(o.server)

    def uno(px):
        try:
            return px["id"], vg.probar(px, *dest, timeout=o.timeout)
        except Exception:
            return px["id"], None

    t0 = time.time()
    with ThreadPoolExecutor(o.hilos) as ex:
        r1 = dict(ex.map(uno, mios))
    vivos = [px for px in mios if r1[px["id"]] is not None]
    ms = {px["id"]: [r1[px["id"]]] for px in vivos}
    for _ in range(o.vueltas):
        time.sleep(5)
        with ThreadPoolExecutor(min(o.hilos, max(1, len(vivos)))) as ex:
            for k, v in ex.map(uno, vivos):
                if v is not None:
                    ms[k].append(v)
    filas = []
    for px in vivos:
        m = ms[px["id"]]
        filas.append((-len(m), int(statistics.median(m)), "%s://%s:%d" % (px["tipo"].lower(), px["host"], px["port"]), len(m)))
    filas.sort()
    with open(o.salida, "w") as f:
        for _, med, url, n in filas:
            f.write("%s\t%d\t%d/%d\n" % (url, med, n, o.vueltas + 1))
    firmes = sum(1 for f in filas if -f[0] == o.vueltas + 1)
    print("parte %d/%d: %d/%d listas, %d candidatos en total, %d en esta parte, %d contestan, %d contestan todas las vueltas, %d s"
          % (o.parte + 1, o.partes, leidas, len(fuentes), total, len(mios), len(vivos), firmes, time.time() - t0), flush=True)


if __name__ == "__main__":
    sys.exit(main())
