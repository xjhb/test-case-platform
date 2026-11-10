"""P2-5 数据血缘图 + 影响分析 自测脚本

用法:
    cd D:\\Qoder
    set PYTHONIOENCODING=utf-8
    python test_p25_lineage.py > p25.txt 2>&1

依赖: 后端已在 API_BASE(默认 http://127.0.0.1:8001) 启动。
账号来自环境变量 ADMIN_USER/ADMIN_PASSWORD, 未设置时回退本地开发种子账号。

脚本先用 SQL 搭一个关系完整的夹具项目(需求-用例-批次-轮次-环境-执行-缺陷全链路),
所有断言都基于这个夹具的已知数量做精确校验,跑完删除夹具项目(外键 CASCADE 连带清理)。
血缘接口全部是 GET,不写业务数据也不写操作日志。
"""
import os
import sys

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.getenv("API_BASE", "http://127.0.0.1:8001/api")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PWD = os.getenv("ADMIN_PASSWORD", "admin123")
TEST_USER = "lineage_probe"
TEST_PWD = os.getenv("LINEAGE_TEST_PASSWORD", "Probe#2026x")
FIXTURE = "LINEAGE_FIXTURE"

ok = 0
fail = 0


def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"[OK]   {label}")
    else:
        fail += 1
        print(f"[FAIL] {label} -> {str(extra)[:400]}")


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


ADMIN = login()
if not ADMIN:
    print("[FAIL] 管理员登录失败,后端未启动或凭据不对")
    sys.exit(1)

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)  # app.database 从 backend/.env 读取连接配置
from sqlalchemy import text  # noqa: E402
from app.database import engine  # noqa: E402


def q(sql, **binds):
    with engine.connect() as c:
        return c.execute(text(sql), binds).all()


def one(sql, **binds):
    rows = q(sql, **binds)
    return rows[0][0] if rows else None


def exe(sql, **binds):
    with engine.begin() as c:
        return c.execute(text(sql), binds)


def graph(**params):
    return api("GET", "/lineage/graph", ADMIN, params=params)


def impact(**params):
    return api("GET", "/lineage/impact", ADMIN, params=params)


TYPE_PREFIX = {
    "requirement": "req", "testcase": "tc", "plan": "plan",
    "run": "run", "defect": "def", "environment": "env",
}
LINK_PATH = {
    "requirement": "/requirements", "testcase": "/testcases", "plan": "/plans",
    "defect": "/defects", "environment": "/environments",
}

# ======================================================================
# 夹具: 一个关系完整的项目
#   R1 ─┬─ T1 ─┬─ RUN1(通过,E1,RD1,PL1) ── D2(提示,已关闭)
#       │      ├─ RUN3(失败,E1,UAT,PL1)
#       │      └─ 2 条版本历史
#   R2 ─┘      PL1 圈选 T1/T2 ; PL2 未圈选(隐式覆盖全部用例)
#   R1 ─── T2 ─── RUN2(失败,E1,RD1,PL1) ── D1(致命,新建,挂 PL1) → 卡准出门禁
#            T3 无需求关联 ; RUN4 无批次无环境 ; D3 孤儿缺陷
# ======================================================================
ADMIN_ID = one("SELECT id FROM users WHERE username=:u", u=ADMIN_USER)


def cleanup_fixture():
    pid = one("SELECT id FROM projects WHERE name LIKE :n", n=f"{FIXTURE}%")
    while pid:
        exe("DELETE FROM projects WHERE id=:p", p=pid)
        pid = one("SELECT id FROM projects WHERE name LIKE :n", n=f"{FIXTURE}%")


cleanup_fixture()
exe(
    "INSERT INTO projects (name, description, project_no) "
    "VALUES (:n, '血缘自测夹具,跑完自动删除', 'LIN-FIXTURE')",
    n=FIXTURE,
)
PID = one("SELECT id FROM projects WHERE name=:n", n=FIXTURE)
if not PID:
    print("[FAIL] 夹具项目创建失败")
    sys.exit(1)
print(f"[INFO] 夹具项目 project_id={PID}")


def ins(table, **cols):
    """插入一行并返回自增ID。

    库里不少 NOT NULL 的文本列没有默认值(建表时 SQLAlchemy 的 default 只在 ORM 层生效),
    所以这里按 INFORMATION_SCHEMA 自动补齐未提供的必填列,避免夹具脚本逐表硬编码。
    """
    meta = q("""
        SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t
    """, t=table)
    values = dict(cols)
    for name, dtype, nullable, default, extra in meta:
        if name in values or nullable == "YES" or default is not None:
            continue
        if "auto_increment" in (extra or ""):
            continue
        if dtype in ("datetime", "timestamp"):
            values[name] = "2026-11-10 10:00:00"
        elif dtype in ("int", "bigint", "smallint", "tinyint", "decimal", "float", "double"):
            values[name] = 0
        else:
            values[name] = ""
    keys = ", ".join(f"`{k}`" for k in values)
    binds = ", ".join(f":{k}" for k in values)
    exe(f"INSERT INTO {table} ({keys}) VALUES ({binds})", **values)
    return one(f"SELECT MAX(id) FROM {table}")


R1 = ins("requirements", project_id=PID, req_no="REQ-LIN-001", title="客户开户", priority="高",
         status="进行中", created_by=ADMIN_ID)
R2 = ins("requirements", project_id=PID, req_no="REQ-LIN-002", title="客户销户", priority="中",
         status="待处理", created_by=ADMIN_ID)
T1 = ins("testcases", project_id=PID, module="客户", title="开户成功流程", priority="P0",
         status="失败", review_status="已批准", created_by=ADMIN_ID)
T2 = ins("testcases", project_id=PID, module="客户", title="销户余额校验", priority="P1",
         status="失败", review_status="草稿", created_by=ADMIN_ID)
T3 = ins("testcases", project_id=PID, module="客户", title="未关联需求的用例", priority="P2",
         status="未执行", review_status="草稿", created_by=ADMIN_ID)
exe("INSERT INTO requirement_testcases (requirement_id, testcase_id) VALUES (:r,:t)", r=R1, t=T1)
exe("INSERT INTO requirement_testcases (requirement_id, testcase_id) VALUES (:r,:t)", r=R2, t=T1)
exe("INSERT INTO requirement_testcases (requirement_id, testcase_id) VALUES (:r,:t)", r=R1, t=T2)
E1 = ins("test_environments", project_id=PID, name="SIT-主环境", stage="SIT", status="可用",
         url="https://sit.example.internal", version="v1.2.0")
PL1 = ins("testplans", project_id=PID, version="vLIN-1", current_stage="SIT", status="进行中",
          created_by=ADMIN_ID)
PL2 = ins("testplans", project_id=PID, version="vLIN-2", current_stage="UAT", status="已完成",
          created_by=ADMIN_ID)
exe("INSERT INTO plan_testcases (plan_id, testcase_id, added_by) VALUES (:p,:t,:u)", p=PL1, t=T1, u=ADMIN_ID)
exe("INSERT INTO plan_testcases (plan_id, testcase_id, added_by) VALUES (:p,:t,:u)", p=PL1, t=T2, u=ADMIN_ID)
RD1 = ins("test_rounds", plan_id=PL1, name="第1轮", round_number=1, status="进行中", created_by=ADMIN_ID)
RUN1 = ins("testruns", testcase_id=T1, plan_id=PL1, stage="SIT", status="通过", executed_by=ADMIN_ID,
           round_id=RD1, env_id=E1, duration_seconds=120)
RUN2 = ins("testruns", testcase_id=T2, plan_id=PL1, stage="SIT", status="失败", executed_by=ADMIN_ID,
           round_id=RD1, env_id=E1, duration_seconds=90)
RUN3 = ins("testruns", testcase_id=T1, plan_id=PL1, stage="UAT", status="失败", executed_by=ADMIN_ID,
           env_id=E1)
RUN4 = ins("testruns", testcase_id=T3, plan_id=None, stage="SIT", status="通过", executed_by=ADMIN_ID)
D1 = ins("defects", title="销户余额未清零", description="夹具", severity="致命", priority="P0",
         status="新建", testcase_id=T2, plan_id=PL1, run_id=RUN2, project_id=PID, reporter_id=ADMIN_ID)
D2 = ins("defects", title="开户回显慢", description="夹具", severity="提示", priority="P3",
         status="关闭", testcase_id=T1, plan_id=PL1, run_id=RUN3, project_id=PID, reporter_id=ADMIN_ID)
D3 = ins("defects", title="孤儿缺陷(无来源)", description="夹具", severity="一般", priority="P2",
         status="处理中", project_id=PID, reporter_id=ADMIN_ID)
ins("testcase_versions", testcase_id=T1, version=1, title="开户成功流程", changed_by=ADMIN_ID,
    change_summary="初版")
ins("testcase_versions", testcase_id=T1, version=2, title="开户成功流程(改)", changed_by=ADMIN_ID,
    change_summary="补充异常分支")

CRIT = None  # 由接口返回的 critical_severities 决定哪些严重程度算紧急

print("\n===== A. 鉴权与参数校验 =====")
st, _ = api("GET", "/lineage/graph", None, params={"project_id": PID})
check("A1 未登录访问血缘图 401", st == 401, st)
st, _ = api("GET", "/lineage/impact", None, params={"project_id": PID, "type": "testcase", "id": T1})
check("A2 未登录访问影响分析 401", st == 401, st)

st, body = graph(project_id=PID, root_type="nonsense", root_id=T1)
check("A3 root_type 非法 400", st == 400, (st, body))
st, body = graph(project_id=PID, root_type="testcase")
check("A4 只给 root_type 不给 root_id 400", st == 400, (st, body))
st, body = graph(project_id=PID, root_id=T1)
check("A5 只给 root_id 不给 root_type 400", st == 400, (st, body))
st, body = graph(project_id=PID, root_type="testcase", root_id=T1, depth=9)
check("A6 depth 超上限 422", st == 422, (st, body))
st, body = graph(project_id=PID, root_type="testcase", root_id=T1, max_nodes=5)
check("A7 max_nodes 低于下限 422", st == 422, (st, body))

uid = one("SELECT id FROM users WHERE username=:u", u=TEST_USER)
if uid is None:
    st, body = api("POST", "/users", ADMIN, json={
        "username": TEST_USER, "password": TEST_PWD, "display_name": "血缘自测账号",
    })
    uid = one("SELECT id FROM users WHERE username=:u", u=TEST_USER)
    if uid is None:
        print(f"[INFO] 探针账号创建失败 st={st} body={str(body)[:200]}")
PROBE = login(TEST_USER, TEST_PWD) if uid else None
if PROBE:
    st, body = api("GET", "/lineage/graph", PROBE, params={"project_id": PID})
    check("A8 非项目成员访问血缘图 403", st == 403, (st, body))
    st, body = api("GET", "/lineage/impact", PROBE, params={"project_id": PID, "type": "testcase", "id": T1})
    check("A9 非项目成员访问影响分析 403", st == 403, (st, body))
    st, body = api("GET", "/lineage/overview", PROBE, params={"project_id": PID})
    check("A10 非项目成员访问血缘体检 403", st == 403, (st, body))
    st, body = api("GET", "/lineage/roots", PROBE, params={"project_id": PID, "type": "testcase"})
    check("A11 非项目成员访问起点列表 403", st == 403, (st, body))
else:
    for n in range(8, 12):
        check(f"A{n} 非项目成员 403", False, "探针账号不可用")

st, body = impact(project_id=PID, type="module", id=T1)
check("A12 impact type 非法 400", st == 400, (st, body))
st, body = impact(project_id=PID, type="run", id=RUN1)
check("A13 impact 不支持执行记录为根 400", st == 400, (st, body))
st, body = impact(project_id=PID, type="testcase", id=T1, change="drop")
check("A14 impact change 非法 400", st == 400, (st, body))
st, body = impact(project_id=PID, type="testcase", id=999999)
check("A15 impact 对象不存在 404", st == 404, (st, body))

OTHER_PID = one("SELECT id FROM projects WHERE id<>:p ORDER BY id LIMIT 1", p=PID)
OTHER_TC = one("SELECT id FROM testcases WHERE project_id=:p ORDER BY id LIMIT 1", p=OTHER_PID) if OTHER_PID else None
if OTHER_TC:
    st, body = impact(project_id=PID, type="testcase", id=OTHER_TC)
    check("A16 跨项目对象按 404 处理(不泄露其它项目数据)", st == 404, (st, body))
else:
    check("A16 跨项目对象按 404 处理", True, "库中没有其它项目,跳过")

print("\n===== B. 血缘图结构 =====")
st, g = graph(project_id=PID, root_type="testcase", root_id=T1, depth=1)
check("B1 用例根图 depth=1 返回 200", st == 200, (st, g))
ids = {n["id"] for n in g.get("nodes", [])}
check("B2 depth=1 节点集精确等于 用例+需求+执行+圈选批次+直接缺陷",
      ids == {f"tc:{T1}", f"req:{R1}", f"req:{R2}", f"run:{RUN1}", f"run:{RUN3}", f"plan:{PL1}", f"def:{D2}"},
      sorted(ids))
check("B3 depth=1 不含未圈选批次(图上只画显式关系)", f"plan:{PL2}" not in ids, sorted(ids))
check("B4 root 字段回显", g.get("root") == f"tc:{T1}", g.get("root"))
check("B5 truncated=False", g.get("truncated") is False, g.get("truncated"))
check("B6 counts 与 nodes 一致", sum(g["counts"].values()) == len(g["nodes"]), (g["counts"], len(g["nodes"])))
check("B7 counts 分类计数正确",
      g["counts"] == {"requirement": 2, "testcase": 1, "plan": 1, "run": 2, "defect": 1, "environment": 0},
      g["counts"])
check("B8 categories 为六类且顺序稳定",
      [c["name"] for c in g["categories"]] == ["需求", "用例", "批次", "执行记录", "缺陷", "环境"],
      g.get("categories"))
links = g.get("links", [])
check("B9 每条边两端都在节点集里(无悬空边)",
      all(l["source"] in ids and l["target"] in ids for l in links),
      [l for l in links if l["source"] not in ids or l["target"] not in ids][:3])
triples = {(l["source"], l["target"], l["type"]) for l in links}
expect_edges = {
    (f"req:{R1}", f"tc:{T1}", "覆盖"),
    (f"req:{R2}", f"tc:{T1}", "覆盖"),
    (f"tc:{T1}", f"run:{RUN1}", "执行"),
    (f"tc:{T1}", f"run:{RUN3}", "执行"),
    (f"plan:{PL1}", f"tc:{T1}", "圈选"),
    (f"tc:{T1}", f"def:{D2}", "关联"),
    # 返回的是节点集上的诱导子图: 同一批节点之间的其它真实关系也会画出来
    (f"run:{RUN1}", f"plan:{PL1}", "归属"),
    (f"run:{RUN3}", f"plan:{PL1}", "归属"),
    (f"plan:{PL1}", f"def:{D2}", "关联"),
    (f"run:{RUN3}", f"def:{D2}", "产生"),
}
check("B10 depth=1 边集 = 节点集上的诱导子图(方向为业务流向)", triples == expect_edges,
      {"缺少": sorted(expect_edges - triples), "多余": sorted(triples - expect_edges)})
nodes = {n["id"]: n for n in g["nodes"]}
check("B11 节点 id 前缀与 type 对应",
      all(n["id"].startswith(TYPE_PREFIX[n["type"]] + ":") for n in nodes.values()), list(nodes))
check("B12 节点带 type_label 与 info",
      all(n["type_label"] == {"req": "需求", "tc": "用例", "plan": "批次", "run": "执行记录",
                              "def": "缺陷", "env": "环境"}[n["id"].split(":")[0]] and n["info"]
          for n in nodes.values()),
      [(n["id"], n["type_label"], n["info"]) for n in nodes.values()][:3])
check("B13 用例节点 info 含模块/优先级/结果/评审",
      set(nodes[f"tc:{T1}"]["info"]) == {"模块", "优先级", "结果", "评审"}, nodes[f"tc:{T1}"]["info"])
check("B14 需求节点名称为 编号+标题",
      nodes[f"req:{R1}"]["name"] == "REQ-LIN-001 客户开户", nodes[f"req:{R1}"]["name"])
check("B15 category 序号与类型顺序一致",
      all(n["category"] == ["requirement", "testcase", "plan", "run", "defect", "environment"].index(n["type"])
          for n in nodes.values()), [(n["id"], n["category"]) for n in nodes.values()])

st, g2 = graph(project_id=PID, root_type="testcase", root_id=T1, depth=2)
ids2 = {n["id"] for n in g2["nodes"]}
check("B16 depth=2 扩出 T2/环境/RUN2/D1",
      {f"tc:{T2}", f"env:{E1}", f"run:{RUN2}", f"def:{D1}"} <= ids2, sorted(ids2))
check("B17 depth=2 仍不扩出未圈选批次 PL2", f"plan:{PL2}" not in ids2, sorted(ids2))
check("B18 depth=2 无悬空边",
      all(l["source"] in ids2 and l["target"] in ids2 for l in g2["links"]), g2["links"][:3])
check("B19 depth=2 出现 执行记录→环境 的「运行于」边",
      (f"run:{RUN1}", f"env:{E1}", "运行于") in {(l["source"], l["target"], l["type"]) for l in g2["links"]},
      g2["links"])
check("B20 depth=2 出现 执行记录→缺陷 的「产生」边",
      (f"run:{RUN2}", f"def:{D1}", "产生") in {(l["source"], l["target"], l["type"]) for l in g2["links"]},
      g2["links"])

st, g0 = graph(project_id=PID, root_type="testcase", root_id=T1, depth=0)
check("B21 depth=0 只返回根节点且无边",
      st == 200 and len(g0["nodes"]) == 1 and g0["links"] == [], (st, g0.get("nodes"), g0.get("links")))

st, gs = graph(project_id=PID, depth=3, max_nodes=10)
check("B22 max_nodes 生效", st == 200 and len(gs["nodes"]) <= 10, (st, len(gs.get("nodes", []))))
sids = {n["id"] for n in gs["nodes"]}
check("B23 截断后仍无悬空边",
      all(l["source"] in sids and l["target"] in sids for l in gs["links"]), gs["links"][:3])
check("B24 截断时 truncated=True", gs["truncated"] is True, gs["truncated"])

st, gall = graph(project_id=PID, depth=3, max_nodes=500)
allids = {n["id"] for n in gall["nodes"]}
check("B25 全景图不指定 root 时 root 为空串", gall.get("root") == "", gall.get("root"))
check("B26 全景图覆盖全部 12 个对象",
      allids == {f"req:{R1}", f"req:{R2}", f"tc:{T1}", f"tc:{T2}", f"tc:{T3}", f"plan:{PL1}", f"plan:{PL2}",
                 f"run:{RUN1}", f"run:{RUN2}", f"run:{RUN3}", f"run:{RUN4}", f"def:{D1}", f"def:{D2}",
                 f"def:{D3}", f"env:{E1}"},
      sorted(allids))
check("B27 全景图 counts 合计 15", sum(gall["counts"].values()) == 15, gall["counts"])
check("B28 全景图包含孤儿对象(未关联需求的用例/无批次的执行/孤儿缺陷)",
      {f"tc:{T3}", f"run:{RUN4}", f"def:{D3}"} <= allids
      and (f"plan:{PL2}", f"tc:{T3}", "圈选") not in
      {(l["source"], l["target"], l["type"]) for l in gall["links"]}, gall["counts"])

st, gr = graph(project_id=PID, root_type="requirement", root_id=R1, depth=1)
rids = {n["id"] for n in gr["nodes"]}
check("B29 需求根图 depth=1 = 需求 + 覆盖用例", rids == {f"req:{R1}", f"tc:{T1}", f"tc:{T2}"}, sorted(rids))

st, ge = graph(project_id=PID, root_type="environment", root_id=E1, depth=1)
eids = {n["id"] for n in ge["nodes"]}
check("B30 环境根图 depth=1 = 环境 + 其上的执行记录",
      eids == {f"env:{E1}", f"run:{RUN1}", f"run:{RUN2}", f"run:{RUN3}"}, sorted(eids))
check("B31 环境边方向为 执行记录→环境",
      all(l["target"] == f"env:{E1}" and l["type"] == "运行于" for l in ge["links"]), ge["links"])

st, gd = graph(project_id=PID, root_type="defect", root_id=D1, depth=1)
dids = {n["id"] for n in gd["nodes"]}
check("B32 缺陷根图 depth=1 = 缺陷 + 来源用例/执行/批次",
      dids == {f"def:{D1}", f"tc:{T2}", f"run:{RUN2}", f"plan:{PL1}"}, sorted(dids))

st, grn = graph(project_id=PID, root_type="run", root_id=RUN4, depth=1)
check("B33 无批次无环境的执行记录只连到用例",
      {n["id"] for n in grn["nodes"]} == {f"run:{RUN4}", f"tc:{T3}"}
      and {(l["source"], l["target"], l["type"]) for l in grn["links"]} == {(f"tc:{T3}", f"run:{RUN4}", "执行")},
      (grn["nodes"], grn["links"]))

if OTHER_TC:
    st, gx = graph(project_id=PID, root_type="testcase", root_id=OTHER_TC, depth=2)
    check("B34 跨项目根节点被丢弃(节点集为空)", st == 200 and gx["nodes"] == [], (st, gx.get("nodes")))
else:
    check("B34 跨项目根节点被丢弃", True, "库中没有其它项目,跳过")

print("\n===== C. 影响分析: 用例 =====")
st, im = impact(project_id=PID, type="testcase", id=T1)
check("C1 用例影响分析 200", st == 200, (st, im))
CRIT = tuple(im.get("critical_severities") or [])
check("C2 critical_severities 来自数据字典且非空", len(CRIT) > 0, CRIT)
secs = {s["key"]: s for s in im.get("sections", [])}
check("C3 分组齐全(需求/批次/执行/缺陷/环境)",
      set(secs) == {"requirements", "plans", "runs", "defects", "environments"}, list(secs))
check("C4 分组含 level/note/count/items/action/title",
      all(all(k in s for k in ("level", "note", "count", "shown", "items", "action", "title"))
          for s in secs.values()),
      [s["key"] for s in secs.values() if not all(k in s for k in ("level", "note", "count", "items", "action"))])
check("C5 level 取值合法",
      all(s["level"] in ("danger", "warning", "info") for s in secs.values()),
      [(s["key"], s["level"]) for s in secs.values()])
check("C6 关联需求 = R1/R2",
      {i["id"] for i in secs["requirements"]["items"]} == {R1, R2} and secs["requirements"]["count"] == 2,
      secs["requirements"])
check("C7 关联需求分组 level=warning(需要重新确认覆盖)",
      secs["requirements"]["level"] == "warning", secs["requirements"]["level"])
check("C8 受影响批次 = 显式圈选 PL1 + 未圈选 PL2(隐式覆盖)",
      {i["id"] for i in secs["plans"]["items"]} == {PL1, PL2} and secs["plans"]["count"] == 2,
      secs["plans"]["items"])
check("C9 隐式覆盖批次在 note 里说明",
      any("未圈选范围,隐式覆盖" in i["note"] for i in secs["plans"]["items"] if i["id"] == PL2),
      [i["note"] for i in secs["plans"]["items"]])
check("C10 有进行中批次时 level=danger", secs["plans"]["level"] == "danger", secs["plans"]["level"])
check("C11 执行记录只算该用例的 2 条(RUN1/RUN3)",
      secs["runs"]["count"] == 2 and {i["id"] for i in secs["runs"]["items"]} == {RUN1, RUN3},
      secs["runs"])
check("C12 最近一次执行失败时 note 点明",
      "失败" in secs["runs"]["note"] and secs["runs"]["level"] == "warning", secs["runs"]["note"])
check("C13 关联缺陷 = 直接关联 D2 + 执行记录产生的缺陷(去重)",
      secs["defects"]["count"] == 1 and {i["id"] for i in secs["defects"]["items"]} == {D2},
      secs["defects"])
check("C14 缺陷全部关闭时不算未关闭",
      "均已关闭" in secs["defects"]["note"] and secs["defects"]["level"] == "info", secs["defects"]["note"])
check("C15 涉及环境 = E1",
      {i["id"] for i in secs["environments"]["items"]} == {E1}, secs["environments"])
sm = {x["label"]: x["value"] for x in im["summary"]}
check("C16 summary 数值精确",
      sm == {"关联需求": 2, "受影响批次": 2, "进行中批次": 1, "执行记录": 2,
             "关联缺陷": 1, "未关闭缺陷": 0, "历史版本": 2}, sm)
check("C17 risk=medium(有进行中批次但无未关闭缺陷)",
      im["risk"]["level"] == "medium" and im["risk"]["label"] == "中" and im["risk"]["reason"], im["risk"])
check("C18 root 回显用例节点", im["root"]["id"] == f"tc:{T1}" and im["root"]["type"] == "testcase", im["root"])
check("C19 change 默认 modify/修改", im["change"] == "modify" and im["change_label"] == "修改",
      (im.get("change"), im.get("change_label")))
check("C20 每条建议非空字符串",
      isinstance(im["suggestion"], list) and im["suggestion"] and all(isinstance(s, str) and s for s in im["suggestion"]),
      im["suggestion"])
check("C21 修改场景建议要求重新执行",
      any("重新执行" in s for s in im["suggestion"]), im["suggestion"])
check("C22 条目链接指向对应视图并带 focus",
      all(i["link"] == f"{LINK_PATH['plan']}?project_id={PID}&focus={i['id']}" for i in secs["plans"]["items"])
      and all(i["link"] == "/requirements" for i in secs["requirements"]["items"])
      and all(i["link"] == f"/environments" for i in secs["environments"]["items"]),
      [i["link"] for s in secs.values() for i in s["items"]])
check("C23 执行记录条目不给链接(无独立视图)",
      all(i["link"] == "" for i in secs["runs"]["items"]), secs["runs"]["items"])

st, im2 = impact(project_id=PID, type="testcase", id=T2)
s2 = {s["key"]: s for s in im2["sections"]}
if "致命" in CRIT:
    check("C24 有未关闭紧急缺陷的用例 risk=high",
          im2["risk"]["level"] == "high" and "紧急" in im2["risk"]["reason"], im2["risk"])
    check("C25 缺陷分组 level=danger 且 note 给出紧急数量",
          s2["defects"]["level"] == "danger" and "计入紧急 1" in s2["defects"]["note"], s2["defects"]["note"])
else:
    check("C24 有未关闭紧急缺陷的用例 risk=high", True, f"致命 不在紧急集合 {CRIT},跳过")
    check("C25 缺陷分组 level=danger", True, "同上")
check("C26 缺陷链接带 focus", s2["defects"]["items"][0]["link"] == f"/defects?project_id={PID}&focus={D1}",
      s2["defects"]["items"][0]["link"])
check("C27 summary 未关闭缺陷=1", {x["label"]: x["value"] for x in im2["summary"]}["未关闭缺陷"] == 1,
      im2["summary"])

st, im3 = impact(project_id=PID, type="testcase", id=T3)
s3 = {s["key"]: s for s in im3["sections"]}
check("C28 无需求关联的用例提示覆盖盲区",
      s3["requirements"]["count"] == 0 and "未关联任何需求" in s3["requirements"]["note"],
      s3["requirements"]["note"])
check("C29 无圈选批次的用例提示尚未纳入",
      s3["plans"]["count"] == 1 and "隐式覆盖" in s3["plans"]["items"][0]["note"], s3["plans"])
check("C30 执行记录未归属环境时说明",
      s3["environments"]["count"] == 0 and "未归属环境" in s3["environments"]["note"], s3["environments"]["note"])

st, imd = impact(project_id=PID, type="testcase", id=T1, change="delete")
check("C31 change=delete 标签为删除", imd["change_label"] == "删除", imd.get("change_label"))
check("C32 删除场景建议与修改场景不同", imd["suggestion"] != im["suggestion"],
      (imd["suggestion"], im["suggestion"]))
check("C33 删除场景提示执行记录会连带删除",
      any("连带删除" in s and "2 条执行记录" in s for s in imd["suggestion"]), imd["suggestion"])
check("C34 删除场景提示需求覆盖需转移",
      any("覆盖关系" in s for s in imd["suggestion"]), imd["suggestion"])
st, imd2 = impact(project_id=PID, type="testcase", id=T2, change="delete")
check("C35 删除有未关闭缺陷的用例时提示追溯链断裂",
      any("追溯链断裂" in s for s in imd2["suggestion"]), imd2["suggestion"])

print("\n===== D. 影响分析: 需求 / 批次 / 环境 / 缺陷 =====")
st, ir = impact(project_id=PID, type="requirement", id=R1)
rs = {s["key"]: s for s in ir.get("sections", [])}
check("D1 需求影响分析 200 且分组齐全",
      st == 200 and set(rs) == {"testcases", "plans", "runs", "defects"}, (st, list(rs)))
check("D2 覆盖用例 = T1/T2", {i["id"] for i in rs["testcases"]["items"]} == {T1, T2}, rs["testcases"])
check("D3 有评审未通过用例时 level=danger 且 note 给数量",
      rs["testcases"]["level"] == "danger" and "1 条评审未通过" in rs["testcases"]["note"], rs["testcases"]["note"])
check("D4 下游批次含 PL1(经覆盖用例)", PL1 in {i["id"] for i in rs["plans"]["items"]}, rs["plans"])
check("D5 下游缺陷含 D1/D2", {i["id"] for i in rs["defects"]["items"]} == {D1, D2}, rs["defects"])
check("D6 下游执行记录 = RUN1/RUN2/RUN3",
      {i["id"] for i in rs["runs"]["items"]} == {RUN1, RUN2, RUN3}, rs["runs"])
rsm = {x["label"]: x["value"] for x in ir["summary"]}
check("D7 需求 summary 精确", rsm == {"覆盖用例": 2, "评审未通过": 1, "受影响批次": 2,
                                    "执行记录": 3, "关联缺陷": 2, "未关闭缺陷": 1}, rsm)
if "致命" in CRIT:
    check("D8 有紧急未关闭缺陷时需求 risk=high", ir["risk"]["level"] == "high", ir["risk"])
else:
    check("D8 有紧急未关闭缺陷时需求 risk=high", True, f"致命 不在紧急集合 {CRIT},跳过")
st, ird = impact(project_id=PID, type="requirement", id=R1, change="delete")
check("D9 删除需求提示覆盖关系一并删除且用例保留",
      any("覆盖关系" in s and "用例本身保留" in s for s in ird["suggestion"]), ird["suggestion"])
st, ir2 = impact(project_id=PID, type="requirement", id=R2)
check("D10 只覆盖一条用例的需求 summary 正确",
      {x["label"]: x["value"] for x in ir2["summary"]}["覆盖用例"] == 1, ir2["summary"])

st, ip = impact(project_id=PID, type="plan", id=PL1)
ps = {s["key"]: s for s in ip.get("sections", [])}
check("D11 批次影响分析 200 且分组齐全",
      st == 200 and set(ps) == {"testcases", "runs", "defects", "rounds", "environments"}, (st, list(ps)))
check("D12 已圈选批次 note 说明口径与数量",
      "已圈选 2 条用例" in ps["testcases"]["note"] and ps["testcases"]["level"] == "info", ps["testcases"]["note"])
check("D13 纳入用例 = T1/T2", {i["id"] for i in ps["testcases"]["items"]} == {T1, T2}, ps["testcases"])
psm = {x["label"]: x["value"] for x in ip["summary"]}
check("D14 批次 summary 精确",
      psm == {"纳入用例": 2, "执行记录": 3, "测试轮次": 1, "关联缺陷": 2, "未关闭缺陷": 1,
              "使用环境": 1, "SIT 准出门禁": psm["SIT 准出门禁"]}, psm)
check("D15 门禁结论取值合法", psm["SIT 准出门禁"] in ("达标", "未达标", "未配置"), psm["SIT 准出门禁"])
check("D16 轮次分组给出第1轮", {i["name"] for i in ps["rounds"]["items"]} == {"第1轮"}, ps["rounds"])
check("D17 批次缺陷 = 挂批次的 + 范围内用例的(去重)",
      {i["id"] for i in ps["defects"]["items"]} == {D1, D2}, ps["defects"])
if "致命" in CRIT:
    check("D18 有紧急未关闭缺陷时批次 risk=high 且点出门禁",
          ip["risk"]["level"] == "high" and "紧急" in ip["risk"]["reason"], ip["risk"])
    check("D19 建议里点出未清零的紧急缺陷",
          any("紧急缺陷" in s and "清零" in s for s in ip["suggestion"]), ip["suggestion"])
else:
    check("D18 有紧急未关闭缺陷时批次 risk=high", True, f"致命 不在紧急集合 {CRIT},跳过")
    check("D19 建议里点出未清零的紧急缺陷", True, "同上")
st, ip2 = impact(project_id=PID, type="plan", id=PL2)
ps2 = {s["key"]: s for s in ip2["sections"]}
check("D20 未圈选批次 note 说明按项目全部用例计入",
      "未圈选范围" in ps2["testcases"]["note"] and ps2["testcases"]["level"] == "warning", ps2["testcases"]["note"])
check("D21 未圈选批次纳入用例数 = 项目全部 3 条",
      {x["label"]: x["value"] for x in ip2["summary"]}["纳入用例"] == 3, ip2["summary"])
check("D22 未圈选批次建议先圈选范围",
      any("圈选" in s for s in ip2["suggestion"]), ip2["suggestion"])
st, ipd = impact(project_id=PID, type="plan", id=PL1, change="delete")
check("D23 删除批次提示连带删除执行记录与轮次",
      any("连带删除" in s and "轮次" in s for s in ipd["suggestion"]), ipd["suggestion"])
check("D24 删除批次建议归档而非删除", any("归档" in s for s in ipd["suggestion"]), ipd["suggestion"])

st, ie = impact(project_id=PID, type="environment", id=E1)
es = {s["key"]: s for s in ie.get("sections", [])}
check("D25 环境影响分析 200 且分组齐全",
      st == 200 and set(es) == {"runs", "testcases", "plans", "defects"}, (st, list(es)))
esm = {x["label"]: x["value"] for x in ie["summary"]}
check("D26 环境 summary 精确",
      esm == {"执行记录": 3, "失败记录": 2, "涉及用例": 2, "涉及批次": 1, "相关缺陷": 2, "未关闭缺陷": 1}, esm)
check("D27 失败记录存在时 level=warning", es["runs"]["level"] == "warning", es["runs"]["level"])
check("D28 涉及用例 = T1/T2", {i["id"] for i in es["testcases"]["items"]} == {T1, T2}, es["testcases"])
check("D29 涉及批次 = PL1", {i["id"] for i in es["plans"]["items"]} == {PL1}, es["plans"])
check("D30 环境相关缺陷经执行记录带出 = D1/D2",
      {i["id"] for i in es["defects"]["items"]} == {D1, D2}, es["defects"])
st, ied = impact(project_id=PID, type="environment", id=E1, change="delete")
check("D31 删除被引用环境 risk=high", ied["risk"]["level"] == "high", ied["risk"])
check("D32 删除被引用环境建议改为停用",
      any("已停用" in s and "删除" in s for s in ied["suggestion"]), ied["suggestion"])
E_NONE = ins("test_environments", project_id=PID, name="SIT-空环境", stage="SIT", status="可用")
st, ie2 = impact(project_id=PID, type="environment", id=E_NONE)
check("D33 无引用环境 risk=low 且提示可安全操作",
      ie2["risk"]["level"] == "low" and any("安全操作" in s for s in ie2["suggestion"]),
      (ie2["risk"], ie2["suggestion"]))
check("D34 无引用环境 note 说明尚无执行记录",
      "尚无执行记录归属该环境" in {s["key"]: s for s in ie2["sections"]}["runs"]["note"], ie2["sections"])

st, idf = impact(project_id=PID, type="defect", id=D1)
ds = {s["key"]: s for s in idf.get("sections", [])}
check("D35 缺陷影响分析 200 且分组齐全",
      st == 200 and set(ds) == {"testcase", "run", "plan", "requirements"}, (st, list(ds)))
check("D36 来源用例/执行/批次精确",
      ds["testcase"]["items"][0]["id"] == T2 and ds["run"]["items"][0]["id"] == RUN2
      and ds["plan"]["items"][0]["id"] == PL1, [s["items"] for s in ds.values()])
dsm = {x["label"]: x["value"] for x in idf["summary"]}
check("D37 缺陷 summary 标出是否计入紧急",
      dsm["严重程度"] == "致命" and dsm["计入紧急"] == ("是" if "致命" in CRIT else "否")
      and dsm["当前状态"] == "新建" and dsm["来源用例"] == "有" and dsm["所属批次"] == "vLIN-1"
      and dsm["影响需求"] == 1, dsm)
if "致命" in CRIT:
    check("D38 未关闭紧急缺陷卡门禁 → risk=high 且批次分组 level=danger",
          idf["risk"]["level"] == "high" and ds["plan"]["level"] == "danger"
          and "卡住准出门禁" in ds["plan"]["note"], (idf["risk"], ds["plan"]["note"]))
    check("D39 建议提示关闭后门禁计数才清零",
          any("准出门禁" in s and "清零" in s for s in idf["suggestion"]), idf["suggestion"])
else:
    check("D38 未关闭紧急缺陷卡门禁", True, f"致命 不在紧急集合 {CRIT},跳过")
    check("D39 建议提示门禁清零", True, "同上")
st, idf2 = impact(project_id=PID, type="defect", id=D3)
ds2 = {s["key"]: s for s in idf2["sections"]}
check("D40 孤儿缺陷提示追溯链缺失",
      ds2["testcase"]["level"] == "warning" and "未关联来源用例" in ds2["testcase"]["note"]
      and ds2["testcase"]["items"] == [], ds2["testcase"])
check("D41 孤儿缺陷 risk=low", idf2["risk"]["level"] == "low", idf2["risk"])
check("D42 孤儿缺陷建议补齐用例关联",
      any("补齐来源用例" in s for s in idf2["suggestion"]), idf2["suggestion"])
st, idf3 = impact(project_id=PID, type="defect", id=D1, change="delete")
check("D43 删除缺陷建议改关闭以留审计痕迹",
      any("关闭" in s and "审计" in s for s in idf3["suggestion"]), idf3["suggestion"])
st, idf4 = impact(project_id=PID, type="defect", id=D2)
check("D44 已关闭的非紧急缺陷 risk 不为 high", idf4["risk"]["level"] != "high", idf4["risk"])
# 缺陷只挂 run 不挂 plan 时,应回溯 run 的批次
D4 = ins("defects", title="仅挂执行记录的缺陷", description="夹具", severity="一般", priority="P2",
         status="新建", testcase_id=None, plan_id=None, run_id=RUN1, project_id=PID, reporter_id=ADMIN_ID)
st, idf5 = impact(project_id=PID, type="defect", id=D4)
check("D45 缺陷未挂批次时从执行记录回溯所属批次",
      st == 200 and {s["key"]: s for s in idf5["sections"]}["plan"]["items"][0]["id"] == PL1,
      (st, idf5.get("sections")))
check("D46 该缺陷来源用例为空但执行记录存在",
      {s["key"]: s for s in idf5["sections"]}["testcase"]["items"] == []
      and {s["key"]: s for s in idf5["sections"]}["run"]["items"][0]["id"] == RUN1, idf5["sections"])

print("\n===== E. 项目血缘体检 =====")
st, ov = api("GET", "/lineage/overview", ADMIN, params={"project_id": PID})
check("E1 overview 200", st == 200, (st, ov))
check("E2 counts 精确",
      ov["counts"] == {"requirement": 2, "testcase": 3, "plan": 2, "run": 4, "defect": 4, "environment": 2},
      ov["counts"])
cov = ov["coverage"]
check("E3 两条需求都被覆盖,覆盖率 100",
      cov["covered_requirements"] == 2 and cov["requirement_coverage"] == 100.0, cov)
check("E4 已关联需求用例数=2,关联率=66.7",
      cov["linked_testcases"] == 2 and cov["testcase_link_rate"] == 66.7, cov)
check("E5 孤儿缺陷数=1(D3;D4 挂了执行记录不算孤儿)", cov["orphan_defects"] == 1, cov)
gaps = {g["text"]: g["level"] for g in ov["gaps"]}
check("E6 报出 1 条用例未关联需求(info)",
      any("1 条用例未关联需求" in t and gaps[t] == "info" for t in gaps), list(gaps.items()))
check("E7 报出 1 个缺陷追溯链断裂(warning)",
      any("1 个缺陷没有来源" in t and gaps[t] == "warning" for t in gaps), list(gaps.items()))
check("E8 报出 1 个批次未圈选范围", any("1 个批次未圈选用例范围" in t for t in gaps), list(gaps))
check("E9 报出 1 条执行记录未归属环境", any("1 条执行记录未归属环境" in t for t in gaps), list(gaps))
check("E10 存在断链时不报 success", not any(v == "success" for v in gaps.values()), gaps)
check("E11 gaps level 取值合法", all(v in ("success", "info", "warning") for v in gaps.values()), gaps)
check("E12 断链共 4 条", len(gaps) == 4, list(gaps))

# 拆掉 R2 的覆盖关系,体检应当报出需求覆盖盲区
exe("DELETE FROM requirement_testcases WHERE requirement_id=:r AND testcase_id=:t", r=R2, t=T1)
st, ovx = api("GET", "/lineage/overview", ADMIN, params={"project_id": PID})
gx = {g["text"]: g["level"] for g in ovx["gaps"]}
check("E13 需求失去覆盖后报出盲区(warning)",
      any("1 条需求没有任何用例覆盖" in t and gx[t] == "warning" for t in gx), list(gx.items()))
check("E14 需求覆盖率随之降到 50.0", ovx["coverage"]["requirement_coverage"] == 50.0, ovx["coverage"])

# 逐项补齐: 需求覆盖 / 用例关联 / 缺陷来源 / 执行环境 / 批次圈选
exe("INSERT INTO requirement_testcases (requirement_id, testcase_id) VALUES (:r,:t)", r=R2, t=T1)
exe("INSERT INTO requirement_testcases (requirement_id, testcase_id) VALUES (:r,:t)", r=R2, t=T3)
exe("UPDATE defects SET testcase_id=:t WHERE id=:d", t=T3, d=D3)
exe("UPDATE testruns SET env_id=:e WHERE id=:r", e=E1, r=RUN4)
exe("INSERT INTO plan_testcases (plan_id, testcase_id, added_by) VALUES (:p,:t,:u)", p=PL2, t=T1, u=ADMIN_ID)
st, ov2 = api("GET", "/lineage/overview", ADMIN, params={"project_id": PID})
check("E15 断链全部补齐后只报 success",
      len(ov2["gaps"]) == 1 and ov2["gaps"][0]["level"] == "success", ov2["gaps"])
check("E16 补齐后覆盖率与关联率均为 100,孤儿缺陷=0",
      ov2["coverage"]["requirement_coverage"] == 100.0
      and ov2["coverage"]["testcase_link_rate"] == 100.0
      and ov2["coverage"]["orphan_defects"] == 0, ov2["coverage"])

print("\n===== F. roots 起点列表 =====")
EXPECT_ROOTS = {
    "requirement": 2, "testcase": 3, "plan": 2, "run": 4, "defect": 4, "environment": 2,
}
for t, n in EXPECT_ROOTS.items():
    st, rr = api("GET", "/lineage/roots", ADMIN, params={"project_id": PID, "type": t, "limit": 50})
    check(f"F1 roots type={t} 条数与库一致且带 type_label",
          st == 200 and len(rr["items"]) == n and rr["type_label"]
          and all(i["name"] and "id" in i and "note" in i for i in rr["items"]),
          (st, len(rr.get("items", [])), n))
st, rr = api("GET", "/lineage/roots", ADMIN, params={"project_id": PID, "type": "testcase", "limit": 2})
check("F2 limit 生效", st == 200 and len(rr["items"]) == 2, (st, len(rr.get("items", []))))
st, rr = api("GET", "/lineage/roots", ADMIN,
             params={"project_id": PID, "type": "testcase", "keyword": "销户", "limit": 50})
check("F3 keyword 过滤用例标题",
      st == 200 and {i["id"] for i in rr["items"]} == {T2}, (st, rr.get("items")))
st, rr = api("GET", "/lineage/roots", ADMIN,
             params={"project_id": PID, "type": "requirement", "keyword": "REQ-LIN-002", "limit": 50})
check("F4 keyword 过滤需求编号", st == 200 and {i["id"] for i in rr["items"]} == {R2}, (st, rr.get("items")))
st, rr = api("GET", "/lineage/roots", ADMIN,
             params={"project_id": PID, "type": "defect", "keyword": "孤儿", "limit": 50})
check("F5 keyword 过滤缺陷标题", st == 200 and {i["id"] for i in rr["items"]} == {D3}, (st, rr.get("items")))
st, rr = api("GET", "/lineage/roots", ADMIN, params={"project_id": PID, "type": "testcase", "keyword": "不存在的关键字"})
check("F6 keyword 无命中返回空列表", st == 200 and rr["items"] == [], (st, rr))
st, body = api("GET", "/lineage/roots", ADMIN, params={"project_id": PID, "type": "bad"})
check("F7 roots type 非法 400", st == 400, (st, body))
st, rr = api("GET", "/lineage/roots", ADMIN, params={"project_id": PID, "type": "run", "limit": 50})
check("F8 执行记录起点 note 带用例标题",
      st == 200 and all(i["note"] for i in rr["items"]), rr.get("items"))

print("\n===== G. 与既有追溯接口口径一致 =====")
st, tr = api("GET", f"/testcases/{T1}/traceability", ADMIN)
check("G1 用例追溯接口 200", st == 200, (st, str(tr)[:120]))
im_t1 = impact(project_id=PID, type="testcase", id=T1)[1]
s_t1 = {s["key"]: s for s in im_t1["sections"]}
check("G2 关联需求与追溯接口一致",
      {r["id"] for r in tr["requirements"]} == {i["id"] for i in s_t1["requirements"]["items"]},
      (tr["requirements"], s_t1["requirements"]["items"]))
check("G3 执行记录数与追溯接口一致",
      len(tr["runs"]) == s_t1["runs"]["count"], (len(tr["runs"]), s_t1["runs"]["count"]))
check("G4 关联缺陷与追溯接口一致(含仅挂执行记录的缺陷)",
      {d["id"] for d in tr["defects"]} == {i["id"] for i in s_t1["defects"]["items"]},
      (tr["defects"], s_t1["defects"]["items"]))
st, dr = api("GET", f"/defects/{D1}/traceability", ADMIN)
im_d1 = impact(project_id=PID, type="defect", id=D1)[1]
s_d1 = {s["key"]: s for s in im_d1["sections"]}
check("G5 缺陷来源接口 200 且来源用例一致",
      st == 200 and (dr.get("testcase") or {}).get("id") == s_d1["testcase"]["items"][0]["id"],
      (st, dr, s_d1["testcase"]["items"]))
st, cm = api("GET", "/requirements/coverage/matrix", ADMIN, params={"project_id": PID})
check("G6 需求覆盖率矩阵 200", st == 200, (st, str(cm)[:120]))
st, dr4 = api("GET", f"/defects/{D4}/traceability", ADMIN)
check("G7 只挂执行记录的缺陷能从执行记录回溯用例与批次",
      st == 200 and (dr4.get("testcase") or {}).get("id") == T1
      and (dr4.get("plan") or {}).get("id") == PL1
      and dr4["testcase"].get("via_run") is True and dr4["plan"].get("via_run") is True,
      (st, dr4))

print("\n===== H. 只读性与清理 =====")
before = one("SELECT COUNT(*) FROM operation_logs")
before_max = one("SELECT COALESCE(MAX(id),0) FROM operation_logs")
graph(project_id=PID, depth=3, max_nodes=500)
for t in ("requirement", "testcase", "plan", "environment", "defect"):
    rid = {"requirement": R1, "testcase": T1, "plan": PL1, "environment": E1, "defect": D1}[t]
    impact(project_id=PID, type=t, id=rid)
    impact(project_id=PID, type=t, id=rid, change="delete")
api("GET", "/lineage/overview", ADMIN, params={"project_id": PID})
api("GET", "/lineage/roots", ADMIN, params={"project_id": PID, "type": "testcase"})
after = one("SELECT COUNT(*) FROM operation_logs")
check("H1 血缘查询不写操作日志(纯只读)", after == before, (before, after))
check("H2 审计链未被血缘查询推进",
      one("SELECT COALESCE(MAX(id),0) FROM operation_logs") == before_max, before_max)
check("H3 血缘查询不改业务数据(用例数不变)",
      one("SELECT COUNT(*) FROM testcases WHERE project_id=:p", p=PID) == 3, None)

cleanup_fixture()
check("H4 夹具项目已删除", one("SELECT COUNT(*) FROM projects WHERE name LIKE :n", n=f"{FIXTURE}%") == 0, None)
check("H5 夹具用例级联清理", one("SELECT COUNT(*) FROM testcases WHERE title='开户成功流程'") == 0, None)
check("H6 夹具缺陷级联清理", one("SELECT COUNT(*) FROM defects WHERE title LIKE '%孤儿缺陷(无来源)%'") == 0, None)
check("H7 夹具环境级联清理",
      one("SELECT COUNT(*) FROM test_environments WHERE name IN ('SIT-主环境','SIT-空环境')") == 0, None)

if uid:
    api("DELETE", f"/users/{uid}", ADMIN)
check("H8 探针账号已清理", one("SELECT COUNT(*) FROM users WHERE username=:u", u=TEST_USER) == 0, None)

print(f"\n===== 结果: 通过 {ok} / 失败 {fail} =====")
sys.exit(1 if fail else 0)
