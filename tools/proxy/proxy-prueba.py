#!/usr/bin/env python3
"""Proxys de prueba para el modo prueba de afk-actions (nunca se usan contra el server real).

  proxy-prueba.py PUERTO TIPO [--user U --clave C] [--vive S --muerto S] [--echa-a S]
TIPO socks5 o http. --vive/--muerto: anda S segundos, despues corta todo y rechaza S segundos (como un proxy
residencial que se cae). --echa-a: corta cada tunel a los S segundos (un proxy que no aguanta una sesion larga).
"""
import argparse, base64, select, socket, struct, threading, time

a = argparse.ArgumentParser()
a.add_argument("puerto", type=int)
a.add_argument("tipo", choices=["socks5", "http"])
a.add_argument("--user", default="")
a.add_argument("--clave", default="")
a.add_argument("--vive", type=float, default=0)
a.add_argument("--muerto", type=float, default=0)
a.add_argument("--echa-a", type=float, default=0)
o = a.parse_args()
t0 = time.time()
vivos = set()
lock = threading.Lock()


def muerto():
    if not o.vive:
        return False
    return (time.time() - t0) % (o.vive + o.muerto) >= o.vive


def rx(s, n):
    b = b""
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise IOError
        b += c
    return b


def socks5(c):
    v, n = rx(c, 2)
    metodos = rx(c, n)
    if o.user:
        if 2 not in metodos:
            c.sendall(b"\x05\xff"); return None
        c.sendall(b"\x05\x02")
        rx(c, 1); u = rx(c, rx(c, 1)[0]).decode(); p = rx(c, rx(c, 1)[0]).decode()
        if u != o.user or p != o.clave:
            c.sendall(b"\x01\x01"); return None
        c.sendall(b"\x01\x00")
    else:
        c.sendall(b"\x05\x00")
    _, cmd, _, at = rx(c, 4)
    host = socket.inet_ntoa(rx(c, 4)) if at == 1 else rx(c, rx(c, 1)[0]).decode() if at == 3 else socket.inet_ntop(socket.AF_INET6, rx(c, 16))
    port = struct.unpack(">H", rx(c, 2))[0]
    try:
        d = socket.create_connection((host, port), timeout=10)
    except Exception:
        c.sendall(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00"); return None
    c.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
    return d


def http(c):
    buf = b""
    while b"\r\n\r\n" not in buf:
        x = c.recv(4096)
        if not x:
            return None
        buf += x
    head = buf.split(b"\r\n\r\n")[0].decode(errors="replace").split("\r\n")
    meth, hp, _ = head[0].split(" ", 2)
    if meth != "CONNECT":
        c.sendall(b"HTTP/1.1 405 No\r\n\r\n"); return None
    if o.user:
        auth = [h for h in head[1:] if h.lower().startswith("proxy-authorization:")]
        ok = auth and base64.b64decode(auth[0].split()[-1]).decode() == "%s:%s" % (o.user, o.clave)
        if not ok:
            c.sendall(b"HTTP/1.1 407 Auth\r\n\r\n"); return None
    h, p = hp.rsplit(":", 1)
    try:
        d = socket.create_connection((h, int(p)), timeout=10)
    except Exception:
        c.sendall(b"HTTP/1.1 502 No\r\n\r\n"); return None
    c.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
    return d


def atender(c):
    d = None
    try:
        if muerto():
            return
        d = socks5(c) if o.tipo == "socks5" else http(c)
        if not d:
            return
        with lock:
            vivos.add((c, d))
        inicio = time.time()
        while True:
            if muerto() or (o.echa_a and time.time() - inicio > o.echa_a):
                break
            r, _, _ = select.select([c, d], [], [], 1)
            for s in r:
                x = s.recv(65536)
                if not x:
                    return
                (d if s is c else c).sendall(x)
    except Exception:
        pass
    finally:
        with lock:
            vivos.discard((c, d))
        for s in (c, d):
            try:
                s and s.close()
            except Exception:
                pass


srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", o.puerto))
srv.listen(64)
while True:
    c, _ = srv.accept()
    if muerto():
        c.close(); continue
    threading.Thread(target=atender, args=(c,), daemon=True).start()
