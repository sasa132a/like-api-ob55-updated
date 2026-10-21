# app.py — Free Fire Like API (OB55) — نسخة سيرفرات Fallback
from flask import Flask, request, jsonify
import asyncio, binascii, json, os, requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import aiohttp
import like_pb2, uid_generator_pb2, visit_count_pb2
from collections import OrderedDict

app = Flask(__name__)

TOKEN_FILE = "token_ind.json"
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "2000"))
used_count = 0

# كل إقليم: سيرفر أساسي + بدائل لو وقع
REGION_SERVERS = {
    "IND": ["https://client.ind.freefiremobile.com"],
    "ME":  ["https://clientbp.ggblueshark.com",
            "https://clientbp.ggpolarbear.com",
            "https://clientbp.common.ggbluefox.com"],
    "PK":  ["https://clientbp.ggblueshark.com",
            "https://clientbp.ggpolarbear.com",
            "https://clientbp.common.ggbluefox.com"],
    "BD":  ["https://clientbp.ggwhitehawk.com",
            "https://clientbp.ggpolarbear.com"],
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

BASE_HEADERS = {
    "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/x-www-form-urlencoded",
    "Expect": "100-continue",
    "X-Unity-Version": "2018.4.11f1",
    "X-GA": "v1 1",
    "ReleaseVersion": "OB55",
}


def load_tokens():
    with open(TOKEN_FILE, "r") as f:
        return json.load(f)


def encrypt_message(plaintext):
    key = b"Yg&tc%DEuh6%Zc^8"
    iv = b"6oyZDr22E3ychjM%"
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return binascii.hexlify(cipher.encrypt(pad(plaintext, AES.block_size))).decode()


def like_proto(uid, region):
    m = like_pb2.like()
    m.uid = int(uid)
    m.region = region
    return m.SerializeToString()


def uid_proto(uid):
    m = uid_generator_pb2.uid_generator()
    m.saturn_ = int(uid)
    m.garena = 1
    return m.SerializeToString()


def get_base(region):
    """يرجّع أول سيرفر شغال للإقليم (بيمنع خطأ الـ DNS)"""
    for base in REGION_SERVERS[region]:
        try:
            requests.head(base, timeout=8)
            return base
        except Exception:
            continue
    return REGION_SERVERS[region][0]


async def _like_one(session, url, edata, token):
    h = dict(BASE_HEADERS)
    h["Authorization"] = f"Bearer {token}"
    try:
        async with session.post(url, data=edata, headers=h) as r:
            return await r.text()
    except Exception:
        return None


async def fire_all_likes(uid, region, url, tokens):
    edata = bytes.fromhex(encrypt_message(like_proto(uid, region)))
    conn = aiohttp.TCPConnector(limit=120)
    async with aiohttp.ClientSession(connector=conn) as s:
        tasks = [_like_one(s, url, edata, t["token"]) for t in tokens]
        return await asyncio.gather(*tasks, return_exceptions=True)


def get_profile(uid, region, token, base):
    url = f"{base}/GetPlayerPersonalShow"
    edata = bytes.fromhex(encrypt_message(uid_proto(uid)))
    h = dict(BASE_HEADERS)
    h["Authorization"] = f"Bearer {token}"
    r = requests.post(url, data=edata, headers=h, verify=False, timeout=25)
    d = visit_count_pb2.Info()
    d.ParseFromString(r.content)
    return d


@app.route("/")
def home():
    return {"status": "ok", "api": "FF Like API OB55",
            "regions": list(REGION_SERVERS.keys())}


@app.route("/like")
def like():
    global used_count
    uid = request.args.get("uid")
    region = (request.args.get("region") or "").upper()

    if not uid or not region:
        return {"error": "uid و region مطلوبين"}, 400
    if region not in REGION_SERVERS:
        return {"error": f"region غير مدعوم: {region}"}, 400

    try:
        tokens = load_tokens()
        base = get_base(region)          # ← بيختار سيرفر شغال تلقائياً

        before = get_profile(uid, region, tokens[0]["token"], base)
        before_like = before.AccountInfo.Likes

        asyncio.run(fire_all_likes(uid, region, f"{base}/LikeProfile", tokens))

        after = get_profile(uid, region, tokens[0]["token"], base)
        after_like = after.AccountInfo.Likes
        given = after_like - before_like
        status = 1 if given > 0 else 2
        if status == 1:
            used_count += 1

        return OrderedDict([
            ("LikesGivenByAPI", given),
            ("LikesafterCommand", after_like),
            ("LikesbeforeCommand", before_like),
            ("PlayerNickname", after.AccountInfo.PlayerNickname),
            ("Level", after.AccountInfo.Levels),
            ("Region", after.AccountInfo.Region),
            ("UID", after.AccountInfo.UID),
            ("server_used", base),
            ("status", status),
            ("daily_limit", DAILY_LIMIT),
            ("used", used_count),
            ("remaining", max(DAILY_LIMIT - used_count, 0)),
        ])
    except Exception as e:
        return {"error": str(e)}, 500


@app.route("/remain")
def remain():
    return {"daily_limit": DAILY_LIMIT,
            "used": used_count,
            "remaining": max(DAILY_LIMIT - used_count, 0)}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
