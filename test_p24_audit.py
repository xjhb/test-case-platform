"""P2-4 防篡改审计 自测脚本

用法: PYTHONIOENCODING=utf-8 python test_p24_audit.py
依赖: 后端已在 API_BASE(默认 http://127.0.0.1:8001) 启动并完成哈希链迁移。
账号来自环境变量 ADMIN_USER/ADMIN_PASSWORD, 未设置时回退本地开发种子账号。
脚本会直连数据库做篡改/还原,跑完链一定回到通过状态。
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.getenv("API_BASE", "http://127.0.0.1:8001/api")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PWD = os.getenv("ADMIN_PASSWORD", "admin123")

ok = 0
fail = 0


def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"[OK]   {label}")
    else:
        fail += 1
        print(f"[FAIL] {label} -> {str(extra)[:300]}")


def api(method, path, token=None, **kw):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.request(method, BASE + path, headers=headers, timeout=180, **kw)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, r.text


def login(user=ADMIN_USER, pwd=ADMIN_PWD):
    st, body = api("POST", "/auth/login", json={"username": user, "password": pwd})
    return body.get("access_token") if isinstance(body, dict) else None


def integrity(**params):
    return api("GET", "/logs/integrity", ADMIN, params=params)


def kinds(rep):
    return {i["kind"]: [x["id"] for x in rep["issues"] if x["kind"] == i["kind"]]
            for i in rep.get("issues", [])}


ADMIN = login()
if not ADMIN:
    print("[FAIL] 管理员登录失败,后端未启动或凭据不对")
    sys.exit(1)

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)  # app.database 从 backend/.env 读取连接配置
from sqlalchemy import text  # noqa: E402
from app import audit  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402


def fetch_row(log_id):
    with engine.connect() as c:
        return c.execute(text("SELECT * FROM operation_logs WHERE id=:i"), {"i": log_id}).mappings().first()


def restore(snapshot):
    cols = ", ".join(f"`{k}`" for k in snapshot)
    binds = ", ".join(f":{k}" for k in snapshot)
    with engine.begin() as c:
        c.execute(text(f"INSERT INTO operation_logs ({cols}) VALUES ({binds})"), dict(snapshot))


# ---------- A. 链概况与基线 ----------
st, state = api("GET", "/logs/state", ADMIN)
check("A1 链头接口可用", st == 200 and state.get("log_count", 0) > 0, state)
check("A2 链头哈希已初始化", len(state.get("head_hash", "")) == 64, state)
st, rep = integrity()
check("A3 全链基线校验通过", st == 200 and rep.get("ok") and not rep.get("issues"), rep)
check("A4 校验覆盖条数与链头计数一致", rep.get("checked") == state.get("log_count"),
      (rep.get("checked"), state.get("log_count")))
st, post = api("POST", "/logs/integrity/verify", ADMIN)
check("A5 留痕校验可用", st == 200 and post.get("ok"), post)
st, lg = api("GET", "/logs", ADMIN, params={"action": "校验", "page": 1, "page_size": 5})
check("A6 校验动作写进了日志", st == 200 and lg.get("total", 0) >= 1 and "完整性校验" in lg["items"][0]["detail"],
      lg.get("items", [{}])[0])

# ---------- B. 新写入自动入链 ----------
tok2 = login()  # 登录本身写一条日志
st, logs = api("GET", "/logs", ADMIN, params={"page": 1, "page_size": 2})
newest, prev_row = logs["items"][0], logs["items"][1]
check("B1 新日志带 64 位 row_hash", st == 200 and len(newest.get("row_hash", "")) == 64, newest)
check("B2 新日志 prev_hash 指向前一条", newest.get("prev_hash") == prev_row.get("row_hash"),
      (newest.get("prev_hash"), prev_row.get("row_hash")))
st, state_b = api("GET", "/logs/state", ADMIN)
check("B3 链头指向最后一条日志", state_b["head_hash"] == newest["row_hash"], state_b)
st, rep_b = integrity()
check("B4 追加后整链仍通过", rep_b["ok"], rep_b)

# ---------- C. 篡改内容 ----------
page4 = api("GET", "/logs", ADMIN, params={"page": 4, "page_size": 5})[1]["items"]
victim, victim2 = page4[2]["id"], page4[1]["id"]
orig = fetch_row(victim)
with engine.begin() as c:
    c.execute(text("UPDATE operation_logs SET detail='攻击者改过的说明' WHERE id=:i"), {"i": victim})
st, rep_c = integrity()
check("C1 改内容被检出为内容篡改", st == 200 and not rep_c["ok"]
      and victim in kinds(rep_c).get("内容被篡改", []), rep_c)
with engine.begin() as c:
    c.execute(text("UPDATE operation_logs SET detail=:d WHERE id=:i"), {"d": orig["detail"], "i": victim})
st, rep_c2 = integrity()
check("C2 还原内容后重新通过", rep_c2["ok"], rep_c2)

# ---------- D. 删除记录 ----------
snap2 = fetch_row(victim2)
with engine.begin() as c:
    c.execute(text("DELETE FROM operation_logs WHERE id=:i"), {"i": victim2})
st, rep_d = integrity()
check("D1 删记录被检出为链断裂", st == 200 and not rep_d["ok"] and "链断裂" in kinds(rep_d), rep_d)
restore(snap2)
st, rep_d2 = integrity()
check("D2 原样补回后重新通过", rep_d2["ok"], rep_d2)

# ---------- E. 伪造记录 ----------
with engine.connect() as c:
    forged_id = c.execute(text("SELECT MAX(id) FROM operation_logs")).scalar() + 9000
with engine.begin() as c:
    c.execute(text("INSERT INTO operation_logs (id, username, action, target, detail, ip, created_at) "
                   "VALUES (:i,'hacker','删除','用例#1','伪造记录,没算哈希','10.0.0.1',NOW())"), {"i": forged_id})
st, rep_e = integrity()
k_e = kinds(rep_e)
check("E1 无哈希的伪造记录被检出为未入链", st == 200 and forged_id in k_e.get("未入链", []), rep_e)
check("E2 链头与末条不一致同步检出", "链头不符" in k_e, k_e)
with engine.begin() as c:
    c.execute(text("DELETE FROM operation_logs WHERE id=:i"), {"i": forged_id})
st, rep_e2 = integrity()
check("E3 移除伪造记录后恢复通过", rep_e2["ok"], rep_e2)

# ---------- F. 只改哈希不改内容 ----------
snap_f = fetch_row(victim)
with engine.begin() as c:
    c.execute(text("UPDATE operation_logs SET prev_hash=CONCAT('ff', SUBSTRING(prev_hash,3)) WHERE id=:i"), {"i": victim})
st, rep_f = integrity()
check("F1 单独替换哈希被检出", st == 200 and not rep_f["ok"], rep_f)
with engine.begin() as c:
    c.execute(text("UPDATE operation_logs SET prev_hash=:p WHERE id=:i"), {"p": snap_f["prev_hash"], "i": victim})
st, rep_f2 = integrity()
check("F2 还原哈希后重新通过", rep_f2["ok"], rep_f2)

# ---------- G. 并发写入不裂链 ----------
before = api("GET", "/logs/state", ADMIN)[1]["log_count"]
with ThreadPoolExecutor(max_workers=8) as pool:
    tokens = list(pool.map(lambda _: login(), range(24)))
check("G1 并发登录 24 次全部成功", all(tokens), sum(1 for x in tokens if x))
st, rep_g = integrity()
check("G2 并发写入后链仍连续", rep_g["ok"], rep_g)
after = api("GET", "/logs/state", ADMIN)[1]["log_count"]
check("G3 链计数增长与写入量一致", after - before >= 24, (before, after))

# ---------- H. 分段校验与日锚定 ----------
st, seg = integrity(from_id=victim - 2, to_id=victim + 2)
check("H1 分段校验范围正确", st == 200 and seg.get("from_id") == victim - 2
      and seg.get("to_id") == victim + 2 and seg.get("ok"), seg)
st, seg2 = integrity(from_id=victim)
check("H2 从中间起点分段校验能自行接上前序哈希", st == 200 and seg2.get("ok") and seg2.get("from_id") == victim, seg2)
today = datetime.now().strftime("%Y-%m-%d")
st, a1 = api("GET", "/logs/anchor", ADMIN, params={"date": today})
st, a2 = api("GET", "/logs/anchor", ADMIN, params={"date": today})
check("H3 当日锚定值可复现", st == 200 and len(a1.get("anchor", "")) == 64 and a1 == a2, a1)
check("H4 锚定包含条数与首末 id", a1.get("count", 0) > 0 and a1.get("first_id") and a1.get("last_id"), a1)
st, bad = api("GET", "/logs/anchor", ADMIN, params={"date": "2026-13-45"})
check("H5 非法日期被拒且给出原因", st == 400 and "YYYY-MM-DD" in str(bad), bad)
st, bad2 = api("GET", "/logs/anchor", ADMIN, params={"date": "2026-02-30"})
check("H6 不存在的日期同样被拒", st == 400, bad2)

# ---------- I. 权限与密钥依赖 ----------
st_anon, _ = api("GET", "/logs/integrity")
check("I1 未登录不能读校验结果", st_anon in (401, 403), st_anon)
st_state, _ = api("GET", "/logs/state")
check("I2 未登录同样读不到链头", st_state in (401, 403), st_state)

# 拿到库权限但不知道盐的人,重算不出与库内一致的哈希
with SessionLocal() as s:
    r = s.get(audit.OperationLog, victim)
    real = audit.row_hash(r.prev_hash, r)
    saved = r.row_hash
    old = audit.settings.audit_secret
    audit.settings.audit_secret = "攻击者自己猜的盐"
    wrong = audit.row_hash(r.prev_hash, r)
    audit.settings.audit_secret = old
check("I3 盐一致时能重算出存储哈希", real == saved, (real[:16], saved[:16]))
check("I4 盐不同则算不出(故必须有独立审计密钥)", wrong != saved, (wrong[:16], saved[:16]))

print(f"\nPASS {ok} / FAIL {fail}")
sys.exit(1 if fail else 0)
