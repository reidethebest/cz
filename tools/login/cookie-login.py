#!/usr/bin/env python3
"""Login de Minecraft con las cookies de la sesion de Microsoft (sin escribir la clave), como hace Minecraft
Console Client. Deja un msa.json que portablemc usa y despues renueva solo (el token dura semanas; las cookies
se usan una sola vez).

  cookie-login.py --cookies cookies.txt --out data/solo/msa.json [--app-id ...] [--timeout 180]

Las cookies van en formato Netscape (lo que exporta el navegador: dominio TAB flag TAB path TAB secure TAB
expira TAB nombre TAB valor). Se usa el flujo device code de Microsoft (el mismo que portablemc y MCC): se pide
un codigo, y con las cookies se aprueba solo en login.live.com. Si no se puede aprobar solo (cookies vencidas,
Microsoft pide verificacion), imprime el codigo para aprobarlo a mano una vez en la URL que indica; el token que
queda sirve igual para semanas.

Nada sensible se imprime: ni cookies, ni tokens. Los logs de Actions son publicos.
"""
import argparse, http.cookiejar, json, re, sys, time, urllib.parse, urllib.request, uuid as uuidlib

# el mismo Azure app id por defecto de portablemc 5.x: asi el refresh_token que sacamos lo puede renovar el kit
APP_ID = "708e91b5-99f8-4a1d-80ec-e746cbb24771"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
DEVICECODE = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
TOKEN = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
SCOPE = "XboxLive.signin offline_access"


def log(*a):
    print(*a, flush=True)


def load_cookies(path):
    jar = http.cookiejar.CookieJar()
    n = 0
    for raw in open(path, encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n")
        if not line or line.startswith("#") and not line.startswith("#HttpOnly_"):
            continue
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        f = line.split("\t")
        if len(f) < 7:
            continue
        dom, flag, pth, sec, exp, name, val = f[:7]
        try:
            expires = int(exp) if exp and exp != "0" else None
        except ValueError:
            expires = None
        c = http.cookiejar.Cookie(0, name, val, None, False, dom, flag.upper() == "TRUE",
                                  dom.startswith("."), pth, True, sec.upper() == "TRUE", expires,
                                  False, None, None, {})
        jar.set_cookie(c)
        n += 1
    return jar, n


def opener(jar):
    o = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), urllib.request.HTTPRedirectHandler())
    o.addheaders = [("User-Agent", UA)]
    return o


def post_form(op, url, data, headers=None):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/x-www-form-urlencoded", **(headers or {})})
    with op.open(req, timeout=30) as r:
        return r.status, r.read().decode("utf-8", "replace"), r.geturl()


def post_json(op, url, obj, headers=None):
    body = json.dumps(obj).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json", "Accept": "application/json", **(headers or {})})
    with op.open(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def get(op, url):
    with op.open(urllib.request.Request(url), timeout=30) as r:
        return r.status, r.read().decode("utf-8", "replace"), r.geturl()


def aprobar_con_cookies(op, user_code, verification_uri):
    """Aprueba el device code en login.live.com usando las cookies. Best-effort: devuelve True si parece que
    aprobo. Microsoft cambia este HTML seguido, asi que si falla, se cae al modo manual."""
    try:
        # la pagina del codigo (microsoft.com/link o la del tenant) lleva a login.live.com/oauth20_remoteconnect
        st, html, url = get(op, verification_uri)
        # meter el codigo
        for u in (url, "https://login.live.com/oauth20_remoteconnect.srf"):
            ppft = re.search(r'name="PPFT"[^>]*value="([^"]+)"', html)
            post_url = re.search(r"urlPost:'([^']+)'", html) or re.search(r'id="fmHF"[^>]*action="([^"]+)"', html)
            data = {"otc": user_code}
            if ppft:
                data["PPFT"] = ppft.group(1)
            target = post_url.group(1) if post_url else "https://login.live.com/ppsecure/post.srf"
            st, html, url = post_form(op, target, data)
            # consentimiento: a veces hay un form de "Si/Continuar"
            if "oauth20_remoteconnect" in url.lower() or "approve" in html.lower() or "confirm" in html.lower():
                ppft = re.search(r'name="PPFT"[^>]*value="([^"]+)"', html)
                pu = re.search(r"urlPost:'([^']+)'", html)
                if pu:
                    d = {"ipt": "", "pprid": "", "uaid": ""}
                    if ppft:
                        d["PPFT"] = ppft.group(1)
                    for k, v in re.findall(r'name="([^"]+)"[^>]*value="([^"]*)"', html):
                        d[k] = v
                    d["canary"] = d.get("canary", "")
                    st, html, url = post_form(op, pu.group(1), d)
            if "success" in html.lower() or "you can close" in html.lower() or "ya puede" in html.lower():
                return True
        return True  # no sabemos seguro; el polling confirma de verdad
    except Exception as e:
        log("  (no se pudo aprobar con cookies:", type(e).__name__, "- se aprueba a mano)")
        return False


def device_flow(op, app_id, timeout):
    st, body, _ = post_form(op, DEVICECODE, {"client_id": app_id, "scope": SCOPE})
    d = json.loads(body)
    user_code, device_code = d["user_code"], d["device_code"]
    vuri = d.get("verification_uri") or d.get("verification_url") or "https://microsoft.com/link"
    interval = int(d.get("interval", 5))
    log("codigo:", user_code, "  aprobar en:", vuri)
    aprobar_con_cookies(op, user_code, vuri)
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(interval)
        try:
            tok = post_form(op, TOKEN, {"client_id": app_id, "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                                        "device_code": device_code})
            data = json.loads(tok[1])
        except urllib.error.HTTPError as e:
            data = json.loads(e.read().decode("utf-8", "replace"))
        err = data.get("error")
        if not err:
            return data["access_token"], data["refresh_token"]
        if err == "authorization_pending":
            continue
        if err in ("authorization_declined", "expired_token", "bad_verification_code"):
            raise SystemExit("login: " + err + " (volve a exportar las cookies o aproba el codigo a mano)")
    raise SystemExit("login: se acabo el tiempo esperando la aprobacion del codigo")


def xbox_chain(op, msa_access):
    xbl = post_json(op, "https://user.auth.xboxlive.com/user/authenticate", {
        "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": "d=" + msa_access},
        "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"})
    xbl_tok = xbl["Token"]
    xsts = post_json(op, "https://xsts.auth.xboxlive.com/xsts/authorize", {
        "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl_tok]},
        "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"})
    xsts_tok = xsts["Token"]
    uhs = xsts["DisplayClaims"]["xui"][0]["uhs"]
    mc = post_json(op, "https://api.minecraftservices.com/authentication/login_with_xbox",
                   {"identityToken": "XBL3.0 x=%s;%s" % (uhs, xsts_tok)})
    mc_access = mc["access_token"]
    req = urllib.request.Request("https://api.minecraftservices.com/minecraft/profile",
                                 headers={"Authorization": "Bearer " + mc_access})
    with op.open(req, timeout=30) as r:
        prof = json.loads(r.read().decode("utf-8", "replace"))
    if "id" not in prof:
        raise SystemExit("login: la cuenta no tiene perfil de Minecraft (no es dueña del juego?)")
    return mc_access, prof["id"], prof["name"]


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--cookies", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--app-id", default=APP_ID)
    a.add_argument("--timeout", type=int, default=180)
    o = a.parse_args()
    jar, n = load_cookies(o.cookies)
    log("cookies cargadas:", n)
    op = opener(jar)
    msa_access, refresh = device_flow(op, o.app_id, o.timeout)
    mc_access, raw_uuid, name = xbox_chain(op, msa_access)
    u = str(uuidlib.UUID(raw_uuid))  # con guiones, como lo guarda portablemc
    # el xuid va dentro del JWT de Minecraft (claim "xuid"); portablemc lo lee del token, aca lo dejamos vacio si no esta
    xuid = ""
    try:
        import base64
        payload = mc_access.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        xuid = json.loads(base64.urlsafe_b64decode(payload)).get("xuid", "")
    except Exception:
        pass
    data = {"accounts": [{"app_id": o.app_id, "refresh_token": refresh, "access_token": mc_access,
                          "uuid": u, "username": name, "xuid": xuid}]}
    import os
    os.makedirs(os.path.dirname(o.out) or ".", exist_ok=True)
    fd = os.open(o.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    log("login OK: cuenta", name, "(token guardado; el kit lo renueva solo)")


if __name__ == "__main__":
    main()
