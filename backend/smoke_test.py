import sys
import httpx

sys.stdout.reconfigure(encoding="utf-8")
BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
passed, failed, skipped = 0, 0, 0


def call(method, path, **kw):
    kw.setdefault("timeout", 60)
    return httpx.request(method, BASE + path, **kw)


def run(name, fn):
    global passed, failed, skipped
    try:
        ok, extra = fn()
    except Exception as e:
        ok, extra = False, f"error: {e}"
    if ok == "skip":
        skipped += 1
        print(f"SKIP  {name}  ({extra})")
    elif ok:
        passed += 1
        print(f"PASS  {name}  ({extra})")
    else:
        failed += 1
        print(f"FAIL  {name}  ({extra})")


state = {}


def t_health():
    r = call("GET", "/health")
    d = r.json()
    return r.status_code == 200 and d.get("ok") is True, f"supabase={d.get('supabase')} gemini={d.get('gemini')}"


def t_rank():
    r = call("POST", "/rank", json={"lat": 12.8728, "lng": 80.2257, "type": "cardiac"})
    d = r.json()
    ok = r.status_code == 200 and len(d) > 0 and "reasons" in d[0] and "score" in d[0]
    if ok:
        state["first_id"] = d[0]["hospital"]["id"]
    return ok, f"{len(d)} hospitals, eta_source={d[0].get('eta_source')}"


def t_rank_bad_type():
    r = call("POST", "/rank", json={"lat": 12.8, "lng": 80.2, "type": "dragon"})
    return r.status_code == 400, f"status {r.status_code}"


def t_rank_exclude():
    hid = state.get("first_id")
    r = call("POST", "/rank", json={"lat": 12.8728, "lng": 80.2257, "type": "cardiac", "exclude": [hid]})
    ids = [x["hospital"]["id"] for x in r.json()]
    return hid not in ids, f"excluded id {hid}"


def t_route():
    body = {"origin": {"lat": 12.8728, "lng": 80.2257}, "destination": {"lat": 13.0226, "lng": 80.1851}}
    r = call("POST", "/route", json=body)
    d = r.json()
    return r.status_code == 200 and len(d["line"]) >= 2, f"source={d.get('source')}, points={len(d['line'])}, {d.get('minutes')} min"


def t_alert_cycle():
    hid = state.get("first_id", 1)
    r = call("POST", "/alert", json={"hospital_id": hid, "type": "cardiac", "eta_min": 9, "summary": "smoke test"})
    d = r.json()
    aid = d["id"]
    s1 = call("GET", f"/alert/{aid}").json()["status"]
    call("PATCH", f"/alert/{aid}", json={"status": "accepted"})
    s2 = call("GET", f"/alert/{aid}").json()["status"]
    return s1 == "sent" and s2 == "accepted", f"alert {aid}: {s1} -> {s2}"


def triage_check(text, expect_type=None, expect_lang=None):
    def fn():
        r = call("POST", "/triage", json={"text": text, "lang": "en"})
        d = r.json()
        ok = r.status_code == 200 and d.get("type") in ("cardiac", "stroke", "accident", "pregnancy")
        if expect_type:
            ok = ok and d["type"] == expect_type
        if expect_lang:
            ok = ok and d.get("lang") == expect_lang
        return ok, f"type={d.get('type')} urgency={d.get('urgency')} source={d.get('source')}"
    return fn


def t_stats():
    r = call("GET", "/stats")
    if r.status_code == 404:
        return "skip", "no /stats yet"
    d = r.json()
    return "totals" in d and "hospitals" in d, f"{d['totals']}"


print(f"Testing {BASE}\n(the first call can take about 30 seconds if the server is asleep)\n")
run("health", t_health)
run("rank cardiac", t_rank)
run("rank rejects bad type", t_rank_bad_type)
run("rank exclude works", t_rank_exclude)
run("route", t_route)
run("alert: send, accept, read back", t_alert_cycle)
run("triage english chest pain", triage_check("chest pain", "cardiac", "en"))
run("triage tamil", triage_check("நெஞ்சு வலி", "cardiac", "ta"))
run("triage hindi", triage_check("सीने में दर्द", "cardiac", "hi"))
run("triage unclear text", triage_check("feeling weak and dizzy since morning"))
run("stats", t_stats)

print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
sys.exit(1 if failed else 0)