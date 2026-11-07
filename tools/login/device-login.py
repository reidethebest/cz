#!/usr/bin/env python3
# Login de Microsoft/Minecraft por "device code", para correr DENTRO de GitHub Actions (red abierta).
# Pide un codigo, lo imprime (una linea: CODIGO <user_code>), espera que lo aprueben en microsoft.com/link,
# y hace XBL -> XSTS -> Minecraft -> perfil. Escribe <out> con el esquema que lee portablemc 5.x, asi el kit
# renueva el login solo por semanas. No imprime tokens ni el device_code.
import argparse, base64, json, sys, time, urllib.error, urllib.parse, urllib.request, uuid as uuidlib

APP_ID = "708e91b5-99f8-4a1d-80ec-e746cbb24771"  # el mismo Azure app id por defecto de portablemc 5.x
DEVICECODE = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
TOKEN = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
SCOPE = "XboxLive.signin offline_access"


def log(*a): print(*a, flush=True)


def post_form(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace"))


def post_json(url, obj):
    body = json.dumps(obj).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def device_flow(app_id, timeout):
    st, body = post_form(DEVICECODE, {"client_id": app_id, "scope": SCOPE})
    if st != 200:
        raise SystemExit("login: no pude pedir el codigo (%s)" % body.get("error", st))
    log("LINK https://www.microsoft.com/link")
    log("CODIGO", body["user_code"])
    log("(entra con la cuenta del bot y apruba; vale %d min)" % (body.get("expires_in", 900) // 60))
    dev = body["device_code"]; interval = body.get("interval", 5); fin = time.time() + timeout
    while time.time() < fin:
        time.sleep(interval)
        st, tok = post_form(TOKEN, {"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                                    "client_id": app_id, "device_code": dev})
        if st == 200:
            log("codigo aprobado"); return tok["access_token"], tok.get("refresh_token", "")
        err = tok.get("error")
        if err == "authorization_pending": continue
        if err == "slow_down": interval += 3; continue
        raise SystemExit("login: " + {"expired_token": "el codigo vencio sin aprobar",
                                      "authorization_declined": "rechazaron el codigo"}.get(err, err or "error"))
    raise SystemExit("login: nadie aprobo el codigo a tiempo")


def xbox_chain(msa_access):
    xbl = post_json("https://user.auth.xboxlive.com/user/authenticate", {
        "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": "d=" + msa_access},
        "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"})
    xsts = post_json("https://xsts.auth.xboxlive.com/xsts/authorize", {
        "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl["Token"]]},
        "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"})
    uhs = xsts["DisplayClaims"]["xui"][0]["uhs"]
    mc = post_json("https://api.minecraftservices.com/authentication/login_with_xbox",
                   {"identityToken": "XBL3.0 x=%s;%s" % (uhs, xsts["Token"])})
    mc_access = mc["access_token"]
    req = urllib.request.Request("https://api.minecraftservices.com/minecraft/profile",
                                 headers={"Authorization": "Bearer " + mc_access})
    with urllib.request.urlopen(req, timeout=30) as r:
        prof = json.loads(r.read().decode("utf-8", "replace"))
    if "id" not in prof:
        raise SystemExit("login: la cuenta no tiene perfil de Minecraft (no es duena del juego?)")
    return mc_access, prof["id"], prof["name"]


def write_msa(out, app_id, refresh, mc_access, raw_uuid, name):
    import os
    u = str(uuidlib.UUID(raw_uuid))
    xuid = ""
    try:
        p = mc_access.split(".")[1]; p += "=" * (-len(p) % 4)
        xuid = json.loads(base64.urlsafe_b64decode(p)).get("xuid", "")
    except Exception:
        pass
    data = {"accounts": [{"app_id": app_id, "refresh_token": refresh, "access_token": mc_access,
                          "uuid": u, "username": name, "xuid": xuid}]}
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--out", required=True)
    a.add_argument("--app-id", default=APP_ID)
    a.add_argument("--timeout", type=int, default=840)
    o = a.parse_args()
    msa_access, refresh = device_flow(o.app_id, o.timeout)
    mc_access, raw_uuid, name = xbox_chain(msa_access)
    write_msa(o.out, o.app_id, refresh, mc_access, raw_uuid, name)
    log("login OK: cuenta", name)


if __name__ == "__main__":
    main()
