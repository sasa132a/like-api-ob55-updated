# app.py — Free Fire Like API (OB55) — Live JWT (التوكنات متموتش)
import os, json, time, binascii, asyncio, requests
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Flask, request
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import aiohttp
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import like_pb2, uid_generator_pb2, visit_count_pb2

app = Flask(__name__)

# ================= الإعدادات =================
JWT_API   = os.getenv("JWT_API", "https://fx-sifat-jwt-api.vercel.app/token")
API_KEY   = os.getenv("API_KEY", "")           # سيبه فاضي لو مش عايز مفتاح
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "5000"))
MAX_ACCOUNTS = int(os.getenv("MAX_ACCOUNTS", "100"))   # أقصى حسابات في الطلب
TOKEN_TTL    = int(os.getenv("TOKEN_TTL", "600"))      # صلاحية الكاش بالثواني
used_count = 0
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ================= الأقاليم والسيرفرات =================
REGION_SERVERS = {
    "ME":  ["https://clientbp.ggblueshark.com",
            "https://clientbp.ppmainecoonghj.com",
            "https://clientbp.ggpolarbear.com"],
    "PK":  ["https://clientbp.ggblueshark.com",
            "https://clientbp.ppmainecoonghj.com"],
    "BD":  ["https://clientbp.ggwhitehawk.com",
            "https://clientbp.ppmainecoonghj.com"],
    "IND": ["https://client.ind.freefiremobile.com"],
    "SG":  ["https://clientbp.ggpolarbear.com"],
    "ID":  ["https://clientbp.ggpolarbear.com"],
    "VN":  ["https://clientbp.ggpolarbear.com"],
    "TH":  ["https://clientbp.ggpolarbear.com"],
    "RU":  ["https://clientbp.ggpolarbear.com"],
    "BR":  ["https://client.us.freefiremobile.com"],
    "US":  ["https://client.us.freefiremobile.com"],
    "NA":  ["https://client.us.freefiremobile.com"],
    "SAC": ["https://client.us.freefiremobile.com"],
}

HEADERS = {
    "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/x-www-form-urlencoded",
    "Expect": "100-continue",
    "X-Unity-Version": "2018.4.11f1",
    "X-GA": "v1 1",
    "ReleaseVersion": "OB55",
}

# ================= الحسابات =================
def load_accounts(region):
    """يقرا accounts_<REGION>.txt والا accounts.txt — كل سطر: uid:password"""
    for fname in (f"accounts_{region}.txt", "accounts.txt"):
        path = os.path.join(BASE_DIR, fname)
        if os.path.exists(path):
            out = []
            with open(path, "r", encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln or ":" not in ln or ln.upper().startswith("UID"):
                        continue
                    u, p = ln.split(":", 1)
                    if u.strip() and p.strip():
                        out.append((u.strip(), p.strip()))
            if out:
                return out
    return []

# ================= توليد JWT لايف =================
def _one_jwt(uid, pw):
    try:
        r = requests.get(JWT_API, params={"uid": uid, "password": pw},
                         timeout=15, verify=False)
        if r.status_code != 200:
            return None
        try:
            j = r.json()
        except ValueError:
            t = r.text.strip()
            return t if len(t) > 40 else None
        if isinstance(j, str):
            return j
        if isinstance(j, dict):
            for k in ("token", "jwt", "access_token"):
                if j.get(k):
                    return j[k]
            d = j.get("data")
            if isinstance(d, dict):
                for k in ("token", "jwt", "access_token"):
                    if d.get(k):
                        return d[k]
        return None
    except Exception:
        return None

def live_tokens(accounts):
    toks = []
    with ThreadPoolExecutor(max_workers=60) as pool:
        futs = [pool.submit(_one_jwt, u, p) for u, p in accounts[:MAX_ACCOUNTS]]
        for f in as_completed(futs):
            t = f.result()
            if t:
                toks.append(t)
    return toks

_cache = {"t": 0, "region": None, "tokens": []}

def get_tokens(region, fresh=False):
    now = time.time()
    if (not fresh and _cache["region"] == region
            and now - _cache["t"] < TOKEN_TTL and _cache["tokens"]):
        return _cache["tokens"]
    acc = load_accounts(region)
    if not acc:
        return []
    toks = live_tokens(acc)
    _cache.update({"t": now, "region": region, "tokens": toks})
    return toks

# ================= تشفير + protobuf =================
def enc(plain: bytes) -> str:
    c = AES.new(b"Yg&tc%DEuh6%Zc^8", AES.MODE_CBC, b"6oyZDr22E3ychjM%")
    return binascii.hexlify(c.encrypt(pad(plain, AES.block_size))).decode()

def uid_proto(uid):
    m = uid_generator_pb2.uid_generator()
    for n in ("saturn_", "krishna_", "uid", "saturn", "krishna"):
        if hasattr(m, n):
            setattr(m, n, int(uid)); break
    for n in ("garena", "teamXdarks", "garena_"):
        if hasattr(m, n):
            setattr(m, n, 1); break
    return m.SerializeToString()

def like_proto(uid, region):
    m = like_pb2.like()
    m.uid = int(uid)
    m.region = region
    return m.SerializeToString()

def parse_profile(raw):
    msg = visit_count_pb2.Info()
    msg.ParseFromString(raw)
    ai = getattr(msg, "AccountInfo", None) or msg
    return {
        "uid":    int(getattr(ai, "UID", 0) or 0),
        "likes":  int(getattr(ai, "Likes", 0) or 0),
        "name":   str(getattr(ai, "PlayerNickname", "") or ""),
        "level":  int(getattr(ai, "Levels", 0) or 0),
        "region": str(getattr(ai, "PlayerRegion", "")
                      or getattr(ai, "Region", "") or ""),
    }

def get_profile(uid, base, token):
    r = requests.post(base + "/GetPlayerPersonalShow",
                      data=bytes.fromhex(enc(uid_proto(uid))),
                      headers={**HEADERS, "Authorization": f"Bearer {token}"},
                      verify=False, timeout=30)
    return parse_profile(r.content)

async def _send(session, url, edata, token):
    try:
        async with session.post(
                url, data=edata,
                headers={**HEADERS, "Authorization": f"Bearer {token}"}) as resp:
            return resp.status
    except Exception:
        return 0

async def _blast(url, edata, tokens):
    conn = aiohttp.TCPConnector(limit=150, ssl=False)
    async with aiohttp.ClientSession(connector=conn) as s:
        return await asyncio.gather(*[_send(s, url, edata, t) for t in tokens])

def send_all_likes(uid, region, base, tokens):
    edata = bytes.fromhex(enc(like_proto(uid, region)))
    res = asyncio.run(_blast(base + "/LikeProfile", edata, tokens))
    return sum(1 for s in res if s == 200)

# ================= الراوتس =================
@app.route("/")
def home():
    return {"status": "ok", "api": "FF Like API OB55 (live JWT)",
            "regions": list(REGION_SERVERS.keys())}

@app.route("/remain")
def remain():
    return {"daily_limit": DAILY_LIMIT, "used": used_count,
            "remaining": max(DAILY_LIMIT - used_count, 0)}

@app.route("/like")
def like():
    global used_count
    uid = request.args.get("uid")
    region = (request.args.get("region") or "").upper()

    if API_KEY and request.args.get("key", "") != API_KEY:
        return {"error": "invalid key"}, 403
    if not uid or not region:
        return {"error": "uid و region مطلوبين"}, 400
    if region not in REGION_SERVERS:
        return {"error": f"region غير مدعوم: {region}",
                "allowed": list(REGION_SERVERS.keys())}, 400

    try:
        tokens = get_tokens(region, fresh=bool(request.args.get("fresh")))
        if not tokens:
            return {"error": "مفيش حسابات شغالة — ضيف سطور uid:password في accounts.txt",
                    "accounts": len(load_accounts(region))}, 500

        before, base, tried = None, None, []
        for cand in REGION_SERVERS[region]:
            try:
                before = get_profile(uid, cand, tokens[0])
                base = cand
                break
            except Exception as e:
                tried.append(f"{cand} -> {e}")
        if before is None:
            return {"error": "كل السيرفرات فشلت", "tried": tried}, 502

        send_all_likes(uid, region, base, tokens)

        after = get_profile(uid, base, tokens[0])
        given = max(0, after["likes"] - before["likes"])
        if given > 0:
            used_count += 1

        return OrderedDict([
            ("LikesGivenByAPI", given),
            ("LikesafterCommand", after["likes"]),
            ("LikesbeforeCommand", before["likes"]),
            ("PlayerNickname", after["name"]),
            ("Level", after["level"]),
            ("Region", after["region"] or region),
            ("UID", after["uid"] or uid),
            ("server_used", base),
            ("tokens_used", len(tokens)),
            ("status", 1 if given > 0 else 2),
            ("daily_limit", DAILY_LIMIT),
            ("used", used_count),
            ("remaining", max(DAILY_LIMIT - used_count, 0)),
        ])
    except Exception as e:
        return {"error": str(e)}, 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
