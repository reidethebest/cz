#!/usr/bin/env python3
"""Vigia de proxys rotativos para el bot en Actions.

Prueba cada proxy de AFK_PROXIES contra el server (tunel + ping de Minecraft) y deja dos pools para los clientes
(ver ProxyPool en el cliente; una linea: id TAB tipo TAB host TAB puerto TAB usuario TAB clave TAB probado):
  comprador.tsv  la cuenta que compra: los sanos, primero los que entraron bien hace poco y despues por latencia
  vigia.tsv      la cuenta que prueba: los sanos, primero el que hace mas que no se prueba entrando de verdad
Los clientes anotan en <pool>.buenos (siguio conectado 90 s) y <pool>.malos (tunel fallido o corte rapido).
Un proxy que la cuenta vigia no pudo usar para entrar (lo echaron, anti-VPN) no va al comprador por CASTIGO_S.

AFK_PROXIES: una linea por proxy, en cualquiera de estas formas
  socks5://usuario:clave@host:puerto   socks4://host:puerto   http://usuario:clave@host:puerto
  host:puerto   host:puerto:usuario:clave   usuario:clave@host:puerto     (tipo: AFK_PROXY_TIPO, http por defecto)
Si una linea tiene {sesion} (proxys rotativos con sesion fija en el usuario, por ejemplo usuario-session-{sesion}),
se arman AFK_PROXY_SESIONES sesiones al azar (5 por defecto); una sesion que se cae se cambia por otra (otra IP).

AFK_PROXY_FUENTES: una URL por linea de listas publicas que se actualizan solas (por ejemplo un repo de GitHub con
socks5.txt, socks4.txt, http.txt). Se vuelven a leer cada AFK_PROXY_RELEER segundos (600). El tipo sale de la linea
(socks5://...) o del nombre del archivo (socks5, socks4, http); si no, AFK_PROXY_TIPO. Como son miles y casi todos
estan muertos, en cada vuelta se reprueban los sanos y se prueban AFK_PROXY_LOTE candidatos nuevos (400), primero los
que nunca se probaron.

cache.tsv: los proxys con los que una cuenta entro de verdad al server (siguio conectada 90 s). Se guarda entre tandas
(en el estado cifrado) y al arrancar esos se prueban primero; un proxy de la cache que lleva CACHE_S sin entrar sale.

Los logs de Actions son publicos: este script solo imprime cantidades, nunca host, usuario ni clave.
"""
import hashlib, json, os, random, socket, struct, subprocess, sys, time, argparse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit, unquote

CASTIGO_S = 1800      # el vigia no pudo entrar con este proxy: afuera del comprador media hora
CACHE_S = 3 * 86400  # un proxy de la cache que no vuelve a entrar en 3 dias sale de la cache
CORTE_S = 600         # un corte del comprador: afuera 10 min (salvo que el ping vuelva a andar, ver ProxyPool)
TIPOS = {"socks5": "SOCKS5", "socks5h": "SOCKS5", "socks4": "SOCKS4", "socks4a": "SOCKS4a", "http": "HTTP", "https": "HTTP"}


def parse(line, tipo_def):
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if "://" in line:
        u = urlsplit(line)
        t = TIPOS.get(u.scheme.lower())
        if not t or not u.hostname or not u.port:
            return None
        return dict(tipo=t, host=u.hostname, port=u.port, user=unquote(u.username or ""), clave=unquote(u.password or ""))
    user = clave = ""
    if "@" in line:
        cred, hp = line.rsplit("@", 1)
        user, _, clave = cred.partition(":")
        p = hp.split(":")
    else:
        p = line.split(":")
        if len(p) >= 4:
            user, clave = p[2], ":".join(p[3:])
    if len(p) < 2 or not p[1].isdigit():
        return None
    return dict(tipo=tipo_def, host=p[0], port=int(p[1]), user=user, clave=clave)


def srv(server):
    """host[:puerto] -> (host, puerto) como lo resuelve Minecraft (registro SRV _minecraft._tcp)."""
    if ":" in server:
        h, p = server.rsplit(":", 1)
        return h, int(p)
    try:
        out = subprocess.run(["dig", "+short", "SRV", "_minecraft._tcp." + server], capture_output=True, text=True, timeout=10).stdout
        for l in out.splitlines():
            f = l.split()
            if len(f) == 4:
                return f[3].rstrip("."), int(f[2])
    except Exception:
        pass
    return server, 25565


def recv_exact(s, n):
    b = b""
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise IOError("cerrado")
        b += c
    return b


def tunel(s, px, host, port):
    t = px["tipo"]
    if t == "SOCKS5":
        s.sendall(b"\x05\x02\x00\x02" if px["user"] else b"\x05\x01\x00")
        v, m = recv_exact(s, 2)
        if m == 2:
            u, c = px["user"].encode(), px["clave"].encode()
            s.sendall(b"\x01" + bytes([len(u)]) + u + bytes([len(c)]) + c)
            if recv_exact(s, 2)[1] != 0:
                raise IOError("socks5: usuario o clave")
        elif m != 0:
            raise IOError("socks5: metodo")
        h = host.encode()
        s.sendall(b"\x05\x01\x00\x03" + bytes([len(h)]) + h + struct.pack(">H", port))
        r = recv_exact(s, 4)
        if r[1] != 0:
            raise IOError("socks5: rechazo %d" % r[1])
        atyp = r[3]
        n = 4 if atyp == 1 else 16 if atyp == 4 else recv_exact(s, 1)[0]
        recv_exact(s, n + 2)
    elif t in ("SOCKS4", "SOCKS4a"):
        u = px["user"].encode()
        if t == "SOCKS4":
            s.sendall(b"\x04\x01" + struct.pack(">H", port) + socket.inet_aton(socket.gethostbyname(host)) + u + b"\x00")
        else:
            s.sendall(b"\x04\x01" + struct.pack(">H", port) + b"\x00\x00\x00\x01" + u + b"\x00" + host.encode() + b"\x00")
        r = recv_exact(s, 8)
        if r[1] != 0x5A:
            raise IOError("socks4: rechazo")
    else:
        import base64
        req = "CONNECT %s:%d HTTP/1.1\r\nHost: %s:%d\r\n" % (host, port, host, port)
        if px["user"]:
            req += "Proxy-Authorization: Basic %s\r\n" % base64.b64encode(("%s:%s" % (px["user"], px["clave"])).encode()).decode()
        s.sendall((req + "\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            c = s.recv(4096)
            if not c or len(buf) > 16384:
                raise IOError("http: sin respuesta")
            buf += c
        code = buf.split(b"\r\n", 1)[0].split()
        if len(code) < 2 or code[1] != b"200":
            raise IOError("http: " + (code[1].decode(errors="replace") if len(code) > 1 else "?"))


def varint(n):
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


def read_varint(s):
    n = shift = 0
    while True:
        b = recv_exact(s, 1)[0]
        n |= (b & 0x7F) << shift
        if not b & 0x80:
            return n
        shift += 7
        if shift > 35:
            raise IOError("varint")


def mc_ping(s, host, port):
    h = host.encode()
    data = varint(0) + varint(47) + varint(len(h)) + h + struct.pack(">H", port) + varint(1)
    s.sendall(varint(len(data)) + data + b"\x01\x00")
    read_varint(s)
    if read_varint(s) != 0:
        raise IOError("status: paquete")
    js = json.loads(recv_exact(s, read_varint(s)).decode("utf-8", "replace"))
    if "version" not in js:
        raise IOError("status: sin version")


def probar(px, host, port, timeout=10):
    t0 = time.time()
    s = socket.create_connection((px["host"], px["port"]), timeout=timeout)
    try:
        s.settimeout(timeout)
        tunel(s, px, host, port)
        mc_ping(s, host, port)
        return int((time.time() - t0) * 1000)
    finally:
        s.close()


def marcas(path):
    m = {}
    try:
        for l in open(path, encoding="utf-8"):
            f = l.rstrip("\n").split("\t")
            if len(f) >= 2 and f[0].isdigit():
                m.setdefault(f[1], []).append(int(f[0]))
    except FileNotFoundError:
        pass
    return m


def escribir(path, filas):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        os.chmod(tmp, 0o600)
        for px in filas:
            f.write("\t".join([px["id"], px["tipo"], px["host"], str(px["port"]), px["user"], px["clave"], str(px.get("probado", 0))]) + "\n")
    os.replace(tmp, path)


def tipo_de_url(url, tipo_def):
    n = url.lower().rsplit("/", 1)[-1]
    for k in ("socks5", "socks4", "http"):
        if k in n:
            return TIPOS[k]
    return tipo_def


def leer_fuente(url, tipo_def, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "proxy-vigia"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        texto = r.read(20_000_000).decode("utf-8", "replace")
    t = tipo_de_url(url, tipo_def)
    return [px for px in (parse(l, t) for l in texto.splitlines()) if px]


def pid(px):
    return "x" + hashlib.sha1(("%s|%s|%d|%s" % (px["tipo"], px["host"], px["port"], px["user"])).encode()).hexdigest()[:8]


class Vigia:
    def __init__(self, lineas, tipo_def, sesiones, d, server, fuentes=(), lote=400, releer=600, hilos=64, timeout=8):
        self.d, self.server, self.tipo_def = d, server, tipo_def
        self.fuentes, self.lote, self.releer, self.hilos, self.timeout = list(fuentes), lote, releer, hilos, timeout
        self.dest = srv(server)
        self.fijos = []
        for i, l in enumerate(lineas):
            px = parse(l, tipo_def)
            if not px:
                continue
            if "{sesion}" in l:
                for j in range(sesiones):
                    self.fijos.append(self.sesion(dict(px, id="p%ds%d" % (i + 1, j + 1), plantilla=px)))
            else:
                self.fijos.append(dict(px, id="p%d" % (i + 1)))
        self.cache = self.leer_cache()
        self.cand = {px["id"]: px for px in self.fijos}
        self.cand.update({k: px for k, px in self.cache.items() if k not in self.cand})
        self.estado = {}
        self.leido = 0
        self.fuentes_ok = 0

    def leer_cache(self):
        c = {}
        try:
            for l in open(os.path.join(self.d, "cache.tsv"), encoding="utf-8"):
                f = l.rstrip("\n").split("\t")
                if len(f) >= 8 and f[1] in TIPOS.values() and f[3].isdigit():
                    c[f[0]] = dict(id=f[0], tipo=f[1], host=f[2], port=int(f[3]), user=f[4], clave=f[5], entro=int(f[7] or 0))
        except FileNotFoundError:
            pass
        return c

    def guardar_cache(self, buenos, now):
        for k, ts in buenos.items():
            px = self.cand.get(k)
            if px and "plantilla" not in px:
                self.cache[k] = dict(px, entro=max(ts + [self.cache.get(k, {}).get("entro", 0)]))
        self.cache = {k: px for k, px in self.cache.items() if now - px.get("entro", 0) < CACHE_S}
        tmp = os.path.join(self.d, "cache.tsv.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            os.chmod(tmp, 0o600)
            for px in sorted(self.cache.values(), key=lambda p: -p.get("entro", 0)):
                f.write("\t".join([px["id"], px["tipo"], px["host"], str(px["port"]), px["user"], px["clave"], "0", str(px["entro"])]) + "\n")
        os.replace(tmp, os.path.join(self.d, "cache.tsv"))

    @property
    def lista(self):
        return list(self.cand.values())

    @staticmethod
    def sesion(px):
        sid = "%08x" % random.getrandbits(32)
        p = px["plantilla"]
        px.update({k: p[k].replace("{sesion}", sid) for k in ("host", "user", "clave")})
        return px

    def leer_fuentes(self):
        if not self.fuentes or time.time() - self.leido < self.releer:
            return
        self.leido = time.time()
        nuevos, ok = {}, 0
        for u in self.fuentes:
            try:
                for px in leer_fuente(u, self.tipo_def):
                    px["id"] = pid(px)
                    nuevos[px["id"]] = px
                ok += 1
            except Exception:
                pass
        self.fuentes_ok = ok
        if not ok:
            return  # la red fallo: se siguen usando los de antes
        # quedan los fijos, los que siguen en las listas y los sanos aunque hayan salido de la lista
        sanos = {k for k, e in self.estado.items() if e["ok"]}
        self.cand = {px["id"]: px for px in self.fijos}
        self.cand.update({k: px for k, px in self.cache.items() if k not in self.cand})
        for k, px in nuevos.items():
            self.cand.setdefault(k, px)
        for k in sanos:
            if k not in self.cand and k in self.viejos:
                self.cand[k] = self.viejos[k]
        self.viejos = dict(self.cand)

    viejos = {}

    def elegir(self):
        """Los sanos y los fijos siempre; de los demas, un lote: primero los nunca probados, despues los mas viejos."""
        siempre, resto = [], []
        for px in self.cand.values():
            e = self.estado.get(px["id"])
            if px["id"].startswith("p") or px["id"] in self.cache or (e and e["ok"]):
                siempre.append(px)
            else:
                resto.append(px)
        resto.sort(key=lambda px: (self.estado.get(px["id"], {}).get("visto", 0), random.random()))
        return siempre + resto[:self.lote]

    def ronda(self):
        self.leer_fuentes()
        prueba = self.elegir()

        def uno(px):
            try:
                return px["id"], probar(px, *self.dest, timeout=self.timeout)
            except Exception:
                return px["id"], None
        with ThreadPoolExecutor(self.hilos) as ex:
            res = dict(ex.map(uno, prueba))
        now = int(time.time())
        malos_c = marcas(os.path.join(self.d, "comprador.tsv.malos"))
        malos_v = marcas(os.path.join(self.d, "vigia.tsv.malos"))
        buenos = marcas(os.path.join(self.d, "comprador.tsv.buenos"))
        for k, v in marcas(os.path.join(self.d, "vigia.tsv.buenos")).items():
            buenos.setdefault(k, []).extend(v)
        for px in prueba:
            e = self.estado.setdefault(px["id"], dict(ok=False, ms=None, fallos=0, probado=0, visto=0))
            ms = res[px["id"]]
            e["ok"], e["ms"], e["visto"] = ms is not None, ms, now
            if ms is None:
                e["fallos"] += 1
            else:
                e["fallos"], e["probado"] = 0, now
            px["probado"] = e["probado"]
            # una sesion rotativa que se cae (ping o corte reciente) cambia de sesion: otra IP
            ultimo_malo = max(malos_c.get(px["id"], []) + malos_v.get(px["id"], []) + [0])
            if "plantilla" in px and (e["fallos"] >= 2 or now - ultimo_malo < 120 and ultimo_malo > e.get("cambiada", 0)):
                self.sesion(px)
                e.update(fallos=0, cambiada=now)
        self.guardar_cache(buenos, now)
        sanos = [px for px in self.cand.values() if self.estado.get(px["id"], {}).get("ok")]

        def ultima(m, k):
            return max(m.get(k, [0]))

        # comprador: sin castigo del vigia; primero los que entraron bien hace poco, despues por latencia
        def castigado(k):
            mv = ultima(malos_v, k)
            if mv and now - mv < CASTIGO_S and mv > ultima(buenos, k):
                return True  # el vigia no pudo entrar (lo echaron o se corto enseguida)
            # el comprador se corto dos veces en la ultima hora: el ping anda pero no aguanta una sesion
            return sum(1 for t in malos_c.get(k, []) if t > now - 3600) >= 2
        comprador = [px for px in sanos if not castigado(px["id"])]
        # orden: los que aguantaron una sesion hace poco, despues los mas estables (entradas buenas menos cortes en
        # 24 h) y al final el ping
        def estable(k):
            return sum(1 for t in buenos.get(k, []) if t > now - 86400) - 2 * sum(1 for t in malos_c.get(k, []) if t > now - 86400)
        comprador.sort(key=lambda px: (-(ultima(buenos, px["id"]) > now - 3600), -estable(px["id"]), self.estado[px["id"]]["ms"]))
        # vigia: el que hace mas que nadie entra de verdad por el, primero
        vigia = sorted(sanos, key=lambda px: (max(ultima(buenos, px["id"]), ultima(malos_v, px["id"])), self.estado[px["id"]]["ms"]))
        escribir(os.path.join(self.d, "comprador.tsv"), comprador[:200])
        escribir(os.path.join(self.d, "vigia.tsv"), vigia[:200])
        # ranking legible (privado, en el dir de datos): orden del comprador con su ping y estabilidad
        with open(os.path.join(self.d, "ranking.tsv"), "w", encoding="utf-8") as f:
            os.chmod(f.name, 0o600)
            for i, px in enumerate(comprador[:200], 1):
                f.write("%d\t%s://%s:%s\t%s ms\testable %d\n" % (i, px["tipo"], px["host"], px["port"], self.estado[px["id"]]["ms"], estable(px["id"])))
        hora = now - 3600
        st = dict(at=now, candidatos=len(self.cand), probados=len(prueba), total=len(self.cand), sanos=len(sanos),
                  comprador=len(comprador), cache=len(self.cache), fuentes_ok=self.fuentes_ok, fuentes=len(self.fuentes),
                  ms_mediana=sorted(self.estado[p["id"]]["ms"] for p in sanos)[len(sanos) // 2] if sanos else None,
                  entradas_buenas_1h=sum(1 for v in buenos.values() for t in v if t > hora),
                  cortes_1h=sum(1 for m in (malos_c, malos_v) for v in m.values() for t in v if t > hora))
        with open(os.path.join(self.d, "estado.json.tmp"), "w") as f:
            json.dump(st, f)
        os.replace(os.path.join(self.d, "estado.json.tmp"), os.path.join(self.d, "estado.json"))
        return st


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--dir", required=True)
    a.add_argument("--server", default=os.environ.get("SERVER", ""))
    a.add_argument("--cada", type=int, default=60)
    a.add_argument("--una-vez", action="store_true")
    o = a.parse_args()
    env = os.environ.get
    lineas = env("AFK_PROXIES", "").splitlines()
    fuentes = [u.strip() for u in env("AFK_PROXY_FUENTES", "").split() if u.strip().startswith("http")]
    v = Vigia(lineas, TIPOS.get(env("AFK_PROXY_TIPO", "http").lower(), "HTTP"), int(env("AFK_PROXY_SESIONES", "5")),
              o.dir, o.server, fuentes, int(env("AFK_PROXY_LOTE", "400")), int(env("AFK_PROXY_RELEER", "600")))
    os.makedirs(o.dir, exist_ok=True)
    v.leer_fuentes()  # la cache ya se cargo: si la red falla, se arranca con los que entraron en tandas anteriores
    if not v.cand:
        print("vigia: sin proxys (AFK_PROXIES vacio y las listas de AFK_PROXY_FUENTES no se pudieron leer)")
        sys.exit(2)
    ultimo = 0
    while True:
        st = v.ronda()
        if o.una_vez or time.time() - ultimo > 900:
            ultimo = time.time()
            print("vigia: %d candidatos (%d en cache, %d/%d listas leidas), %d sanos, %d para comprar, mediana %s ms, %d entradas buenas y %d cortes en 1 h"
                  % (st["candidatos"], st["cache"], st["fuentes_ok"], st["fuentes"], st["sanos"], st["comprador"], st["ms_mediana"],
                     st["entradas_buenas_1h"], st["cortes_1h"]), flush=True)
        if o.una_vez:
            return
        time.sleep(o.cada)


if __name__ == "__main__":
    main()
