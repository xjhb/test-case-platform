"""P2-3 数据字典 + 项目模板 自测脚本

用法: PYTHONIOENCODING=utf-8 python test_p23_dict_template.py
依赖: 后端已在 API_BASE(默认 http://127.0.0.1:8001) 启动, 且演示项目 1/3 存在。
账号来自环境变量 ADMIN_USER/ADMIN_PASSWORD, 未设置时回退本地开发种子账号。
"""
import os
import sys

import requests

BASE = os.getenv("API_BASE", "http://127.0.0.1:8001/api")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PWD = os.getenv("ADMIN_PASSWORD", "admin123")
TEST_PWD = os.getenv("DICT_TEST_PASSWORD", "Test123456")
PROJECT_ID = 1          # test1: 有 1 条用例,作为字典联动验证基线
OTHER_PROJECT = 3       # 阶段验证项目
UNAME = "dict_p23_tester"
TPL_NAME = "P2-3自测模板"
TPL_NAME2 = "P2-3自测模板2"
PROJ_NAME = "P2-3自测项目"

ok = 0
fail = 0
fails = []


def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"[OK]   {label}")
    else:
        fail += 1
        fails.append(label)
        print(f"[FAIL] {label} -> {str(extra)[:260]}")


def api(method, path, token=None, **kw):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.request(method, BASE + path, headers=headers, timeout=60, **kw)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, r.text


def detail(resp):
    if isinstance(resp, dict):
        return resp.get("detail", resp)
    if isinstance(resp, list):
        return resp[:3]
    return resp


def login(user, pwd):
    st, body = api("POST", "/auth/login", json={"username": user, "password": pwd})
    return body.get("access_token") if isinstance(body, dict) else None


ADMIN = login(ADMIN_USER, ADMIN_PWD)
if not ADMIN:
    print("[FAIL] 管理员登录失败,后续用例无法执行")
    sys.exit(1)


def find_pid(name):
    for p in api("GET", "/projects", ADMIN)[1]:
        if p["name"] == name:
            return p["id"]
    return None


# ---------- 预清理上次残留 ----------
SCRIPT_LABELS_ANY = ("P9", "PX", "成员项", "成员项改名", "模板模块", "越权全局项",
                     "P2-3临时模块", "P2-3改名", "离职后新增")
BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)  # app.database 从 backend/.env 读取连接配置
from sqlalchemy import text  # noqa: E402
from app.database import engine  # noqa: E402

_label_sql = ",".join("'" + x + "'" for x in SCRIPT_LABELS_ANY)
_builtin_labels = ",".join("'" + x + "'" for x in
                           ("P0", "P1", "P2", "P3", "登录", "交易", "退款", "报表",
                            "致命", "严重", "一般", "提示", "高", "中", "低"))
_tpl_labels = ",".join(f"'{n}'" for n in (TPL_NAME, TPL_NAME2))


def _ids(sql):
    with engine.connect() as c:
        return [r[0] for r in c.execute(text(sql))]


_pids = f"{PROJECT_ID},{OTHER_PROJECT}"
with engine.begin() as conn:
    # 解除模板来源,否则自测模板删不掉
    conn.execute(text(f"UPDATE projects SET template_id=NULL WHERE template_id IN "
                      f"(SELECT id FROM (SELECT id FROM project_templates WHERE name IN ({_tpl_labels})) t)"))
    # 项目级残留:含覆盖内置项用的 P3、需求优先级 紧急,仅限自测项目
    conn.execute(text(f"DELETE FROM dict_items WHERE project_id IN ({_pids}) "
                      f"AND label IN ({_label_sql},'P3','紧急')"))
    # 全局残留:只删非内置的自建项,内置行不动
    conn.execute(text(f"DELETE FROM dict_items WHERE project_id IS NULL AND builtin=0 "
                      f"AND label IN ({_label_sql})"))
    # 旧版重名校验漏判产生的"影子"全局项(与内置 label 同名)
    conn.execute(text(f"DELETE FROM dict_items WHERE project_id IS NULL AND builtin=0 "
                      f"AND label IN ({_builtin_labels})"))
    # 自测模板曾把默认标记顶掉,内置模板需要恢复
    if not conn.execute(text("SELECT id FROM project_templates WHERE is_default=1 LIMIT 1")).fetchone():
        conn.execute(text("UPDATE project_templates SET is_default=1 WHERE name='银行标准三阶段模板'"))

pid_old = find_pid(PROJ_NAME)
if pid_old:
    api("DELETE", f"/projects/{pid_old}", ADMIN)

for tname in (TPL_NAME, TPL_NAME2):
    for t in api("GET", "/project-templates", ADMIN)[1]:
        if t["name"] == tname:
            api("DELETE", f"/project-templates/{t['id']}", ADMIN)
for tid in _ids(f"SELECT id FROM testcases WHERE project_id IN ({_pids}) AND title LIKE 'P2-3%'"):
    api("DELETE", f"/testcases/{tid}", ADMIN)
for did in _ids(f"SELECT id FROM defects WHERE project_id IN ({_pids}) AND title LIKE 'P2-3%'"):
    api("DELETE", f"/defects/{did}", ADMIN)
for rid in _ids(f"SELECT id FROM requirements WHERE project_id IN ({_pids}) AND req_no LIKE 'P23-REQ%'"):
    api("DELETE", f"/requirements/{rid}", ADMIN)
st, users = api("GET", "/users", ADMIN, params={"page_size": 200})
uid_old = next((u["id"] for u in (users.get("items") if isinstance(users, dict) else users)
               if u.get("username") == UNAME), None)
if uid_old:
    api("DELETE", f"/users/{uid_old}", ADMIN)
# 记录项目原有门禁,收尾只删本次新增的
gates_before = {g["id"] for g in api("GET", "/gates", ADMIN, params={"project_id": PROJECT_ID})[1]
                if isinstance(g, dict)}

# ---------- A. 字典目录与读取 ----------
st, types = api("GET", "/dict/types", ADMIN)
check("A1 字典类型目录", st == 200 and len(types["configurable"]) == 5, detail(types))
check("A2 固定口径只读清单", len(types["locked"]) == 4 and all(x.get("reason") for x in types["locked"]), types)
check("A3 模块为建议模式",
      any(x["key"] == "case_module" and x["mode"] == "suggest" for x in types["configurable"]), types)
st, opts = api("GET", "/dict/options", ADMIN, params={"dict_key": "case_priority", "project_id": PROJECT_ID})
check("A4 优先级默认4项含色值", st == 200 and len(opts) == 4 and opts[0]["label"] == "P0" and opts[0]["color"] == "danger", opts)
check("A5 紧急标记来自字典", {o["label"] for o in opts if o["is_urgent"]} == {"P0", "P1"}, opts)
st, bad = api("GET", "/dict/options", ADMIN, params={"dict_key": "nope"})
check("A6 未知字典类型 400", st == 400 and "未知字典类型" in detail(bad), detail(bad))
st, allk = api("GET", "/dict/effective", ADMIN, params={"project_id": PROJECT_ID})
check("A7 一次性取全类型", st == 200 and set(allk.keys()) == {t["key"] for t in types["configurable"]}, detail(allk))

# ---------- B. 字典维护与权限 ----------
st, forb = api("POST", "/dict", "NOPE_TOKEN", json={"dict_key": "case_priority", "label": "X"})
check("B0 未登录 401", st == 401, st)
st, noname = api("POST", "/dict", ADMIN, json={"dict_key": "case_priority", "label": "  "})
check("B1 空名称 400", st == 400 and "不能为空" in detail(noname), detail(noname))
st, dup = api("POST", "/dict", ADMIN, json={"dict_key": "case_priority", "label": "P0"})
check("B2 全局重名 400", st == 400, detail(dup))
st, g = api("POST", "/dict", ADMIN, json={"dict_key": "case_module", "label": "P2-3临时模块", "color": "info", "sort_order": 90})
check("B3 管理员建全局项", st == 200 and g.get("source") == "global", detail(g))
gid = g.get("id")
st, upd = api("PUT", f"/dict/{gid}", ADMIN, json={"color": "success", "remark": "自测改色"})
check("B4 编辑全局项", st == 200 and upd["color"] == "success", detail(upd))
st, rename = api("PUT", f"/dict/{gid}", ADMIN, json={"label": "P2-3改名"})
check("B5 改名生效", st == 200 and rename["label"] == "P2-3改名", detail(rename))
builtin = next((r for r in api("GET", "/dict", ADMIN, params={"dict_key": "case_priority"})[1] if r["builtin"]), None)
st, rnb = api("PUT", f"/dict/{builtin['id']}", ADMIN, json={"label": "改内置项"})
check("B6 内置项不能改名 400", st == 400 and "不能改名" in detail(rnb), detail(rnb))
st, dl = api("DELETE", f"/dict/{builtin['id']}", ADMIN)
check("B7 内置项不能删除 400", st == 400 and "内置选项" in detail(dl), detail(dl))
st, delok = api("DELETE", f"/dict/{gid}", ADMIN)
check("B8 自建全局项可删除", st == 200, detail(delok))
# 项目级覆盖
st, pi = api("POST", "/dict", ADMIN, json={"dict_key": "case_priority", "project_id": PROJECT_ID,
                                          "label": "P9", "color": "danger", "sort_order": 0, "is_urgent": True})
check("B9 项目级新增选项", st == 200 and pi["source"] == "project", detail(pi))
pid_item = pi["id"]
st, hid = api("POST", "/dict", ADMIN, json={"dict_key": "case_priority", "project_id": PROJECT_ID,
                                            "label": "P3", "enabled": False})
check("B10 项目级覆盖内置项(停用P3)", st == 200 and hid["enabled"] is False, detail(hid))
st, o2 = api("GET", "/dict/options", ADMIN, params={"dict_key": "case_priority", "project_id": PROJECT_ID})
check("B11 覆盖后选项集含P9不含P3",
      {x["label"] for x in o2} == {"P0", "P1", "P2", "P9"} and any(x["is_urgent"] for x in o2 if x["label"] == "P9"), o2)
st, dup2 = api("POST", "/dict", ADMIN, json={"dict_key": "case_priority", "project_id": PROJECT_ID, "label": "P9"})
check("B12 项目内重名 400", st == 400 and "已存在" in detail(dup2), detail(dup2))
st, ou = api("PUT", f"/dict/{pid_item}", ADMIN, json={"sort_order": 77})
check("B13 编辑项目级项", st == 200 and ou["sort_order"] == 77, detail(ou))
st, du = api("DELETE", f"/dict/{pid_item}", ADMIN)
check("B14 删除项目级项", st == 200, detail(du))

# ---------- C. 字典驱动业务校验 ----------
# B14 已删除项目级 P9,这里重新建一次用于校验联动(收尾统一清理项目级项)
st, pi9 = api("POST", "/dict", ADMIN, json={"dict_key": "case_priority", "project_id": PROJECT_ID,
                                            "label": "P9", "color": "danger", "sort_order": 0,
                                            "is_urgent": True})
check("C0 重新建项目级 P9", st == 200, detail(pi9))
st, cases = api("GET", "/testcases", ADMIN, params={"project_id": PROJECT_ID, "page_size": 5})
tc_id = cases["items"][0]["id"]
st, tc = api("GET", f"/testcases/{tc_id}", ADMIN)
orig_priority = tc["priority"]
st, badp = api("PUT", f"/testcases/{tc_id}", ADMIN, json={"priority": "Z9"})
check("C1 非法优先级被拒", st == 400 and "用例优先级只能是" in detail(badp), detail(badp))
st, p9 = api("PUT", f"/testcases/{tc_id}", ADMIN, json={"priority": "P3"})
check("C2 项目内停用值被拒", st == 400 and "用例优先级只能是" in detail(p9) and "P3" not in detail(p9), detail(p9))
st, p9ok = api("PUT", f"/testcases/{tc_id}", ADMIN, json={"priority": "P9"})
check("C3 项目自定义优先级可用", st == 200 and p9ok["priority"] == "P9", detail(p9ok))
st, otherp = api("POST", "/testcases", ADMIN, json={"project_id": OTHER_PROJECT, "title": "P2-3对照用例", "priority": "P9"})
check("C4 自定义项不跨项目串味", st == 400 and "用例优先级只能是" in detail(otherp), detail(otherp))
if st == 200:
    api("DELETE", f"/testcases/{otherp['id']}", ADMIN)
# 停用项只影响新写入,历史值仍可保留
if orig_priority == "P3":
    st, keep = api("PUT", f"/testcases/{tc_id}", ADMIN, json={"priority": "P3"})
    check("C5 历史值可原样保存", st == 200, detail(keep))
st, legacy = api("PUT", f"/testcases/{tc_id}", ADMIN, json={"title": tc["title"]})
check("C6 仅改标题不受优先级影响", st == 200, detail(legacy))
api("PUT", f"/testcases/{tc_id}", ADMIN, json={"priority": orig_priority})
# 缺陷严重程度
st, dbad = api("POST", "/defects", ADMIN, json={"project_id": PROJECT_ID, "title": "P2-3非法严重度", "severity": "中"})
check("C7 历史严重度「中」不可新建", st == 400 and "严重程度只能是" in detail(dbad), detail(dbad))
st, dft = api("POST", "/defects", ADMIN, json={"project_id": PROJECT_ID, "title": "P2-3致命缺陷", "severity": "致命", "priority": "P0"})
check("C8 致命/一般可新建", st == 200 and dft.get("severity") == "致命", detail(dft))
dft_id = dft.get("id")
st, dgen = api("POST", "/defects", ADMIN, json={"project_id": PROJECT_ID, "title": "P2-3一般缺陷", "severity": "一般"})
check("C9 一般严重度可新建", st == 200, detail(dgen))
dgen_id = dgen.get("id")
if dft_id:
    st, dupd = api("PUT", f"/defects/{dft_id}", ADMIN, json={"severity": "中"})
    check("C10 缺陷改为非法值被拒", st == 400, detail(dupd))
# 需求优先级
st, rq = api("POST", "/requirements", ADMIN, json={"project_id": PROJECT_ID, "req_no": "P23-REQ-1",
                                                   "title": "P2-3需求", "priority": "紧急"})
check("C11 需求非法优先级被拒", st == 400 and "需求优先级只能是" in detail(rq), detail(rq))
st, rdict = api("POST", "/dict", ADMIN, json={"dict_key": "requirement_priority", "project_id": PROJECT_ID,
                                              "label": "紧急", "color": "danger", "sort_order": 0})
check("C12 项目级新增需求优先级", st == 200, detail(rdict))
rq_item_id = rdict.get("id")
st, rq2 = api("POST", "/requirements", ADMIN, json={"project_id": PROJECT_ID, "req_no": "P23-REQ-2",
                                                    "title": "P2-3需求2", "priority": "紧急"})
check("C13 新值立即可用", st == 200, detail(rq2))
rq2_id = rq2.get("id")
st, mod = api("POST", "/testcases", ADMIN, json={"project_id": PROJECT_ID, "title": "P2-3模块用例",
                                                 "module": "任意模块名", "priority": "P1"})
check("C14 模块为建议项不强制校验", st == 200 and mod["module"] == "任意模块名", detail(mod))
mod_id = mod.get("id")

# ---------- D. 项目模板 ----------
st, tpls = api("GET", "/project-templates", ADMIN)
check("D1 模板列表含内置模板", st == 200 and any(t["is_default"] and t["gates"] for t in tpls), detail(tpls))
st, tn = api("POST", "/project-templates", ADMIN, json={"name": " "})
check("D2 空模板名 400", st == 400 and "不能为空" in detail(tn), detail(tn))
st, tdup = api("POST", "/project-templates", ADMIN, json={"name": tpls[0]["name"]})
check("D3 模板重名 400", st == 400, detail(tdup))
st, tbad = api("POST", "/project-templates", ADMIN, json={"name": TPL_NAME, "gates": [{"stage": "SIT", "kind": "准出", "rule": "nope", "threshold": 1}]})
check("D4 非法门禁规则 400", st == 400 and "门禁规则非法" in detail(tbad), detail(tbad))
st, tbad2 = api("POST", "/project-templates", ADMIN, json={"name": TPL_NAME, "stage_days": {"SIT": 0}})
check("D5 非法天数 400", st == 400 and "天数" in detail(tbad2), detail(tbad2))
st, tbad3 = api("POST", "/project-templates", ADMIN, json={"name": TPL_NAME, "dict_items": [{"dict_key": "stage", "label": "X"}]})
check("D6 模板字典类型受限 400", st == 400 and "未知字典类型" in detail(tbad3), detail(tbad3))
tpl_payload = {
    "name": TPL_NAME,
    "description": "P2-3 自测模板",
    "stage_days": {"SIT": 12, "UAT": 4, "PRE": 2},
    "gates": [
        {"stage": "SIT", "kind": "准出", "rule": "pass_rate_min", "threshold": 88, "enabled": True},
        {"stage": "UAT", "kind": "准入", "rule": "executed_rate_min", "threshold": 60, "enabled": True},
    ],
    "custom_fields": [
        {"name": "自测字段", "field_type": "select", "options": ["甲", "乙"], "required": False},
    ],
    "tags": [{"name": "自测标签", "color": "#F56C6C"}],
    "dict_items": [
        {"dict_key": "case_priority", "label": "PX", "color": "warning", "sort_order": 9, "is_urgent": True},
        {"dict_key": "case_module", "label": "模板模块"},
    ],
}
st, tpl = api("POST", "/project-templates", ADMIN, json=tpl_payload)
check("D7 创建模板", st == 200 and tpl["stage_days"]["SIT"] == 12 and len(tpl["gates"]) == 2, detail(tpl))
TPL_ID = tpl.get("id")
st, tplu = api("PUT", f"/project-templates/{TPL_ID}", ADMIN, json={"description": "改过自新", "is_default": True})
check("D8 模板设为默认", st == 200 and tplu["is_default"] and tplu["description"] == "改过自新", detail(tplu))
st, dfl = api("GET", "/project-templates", ADMIN)
check("D9 默认模板唯一", sum(1 for t in dfl if t["is_default"]) == 1, [t["is_default"] for t in dfl])
st, tpl2 = api("POST", "/project-templates", ADMIN, json={"name": TPL_NAME2})
TPL2_ID = tpl2.get("id")
st, tplname2 = api("PUT", f"/project-templates/{TPL2_ID}", ADMIN, json={"name": TPL_NAME})
check("D10 模板改名撞重名 400", st == 400, detail(tplname2))

# 用模板创建项目
st, proj = api("POST", "/projects", ADMIN, json={"name": PROJ_NAME, "project_no": "P23-SELF",
                                                  "template_id": TPL_ID, "description": "P2-3 自测项目"})
check("D11 模板创建项目", st == 200 and proj["template_id"] == TPL_ID, detail(proj))
NEW_PID = proj.get("id")
st, gates = api("GET", "/gates", ADMIN, params={"project_id": NEW_PID})
check("D12 门禁复制到项目", st == 200 and {g["rule"] for g in gates} == {"pass_rate_min", "executed_rate_min"}, detail(gates))
st, cf = api("GET", f"/p2/custom-fields/{NEW_PID}", ADMIN)
check("D13 自定义字段复制", st == 200 and any(f["name"] == "自测字段" for f in (cf if isinstance(cf, list) else cf.get("items", []))), detail(cf))
st, tg = api("GET", f"/p2/tags/{NEW_PID}", ADMIN)
check("D14 标签复制", st == 200 and any(t["name"] == "自测标签" for t in (tg if isinstance(tg, list) else [])), detail(tg))
st, dopts = api("GET", "/dict/options", ADMIN, params={"dict_key": "case_priority", "project_id": NEW_PID})
check("D15 字典项复制并生效", st == 200 and any(x["label"] == "PX" and x["is_urgent"] for x in dopts), dopts)
st, dmod = api("GET", "/dict/options", ADMIN, params={"dict_key": "case_module", "project_id": NEW_PID})
check("D16 建议项一并复制", any(x["label"] == "模板模块" for x in dmod), dmod)
st, tcnew = api("POST", "/testcases", ADMIN, json={"project_id": NEW_PID, "title": "P2-3模板用例", "priority": "PX"})
check("D17 模板字典立即可用", st == 200, detail(tcnew))
NEW_TC = tcnew.get("id")
st, tcbad = api("POST", "/testcases", ADMIN, json={"project_id": NEW_PID, "title": "P2-3模板反例", "priority": "P0"})
check("D18 项目1的停用不影响新项目", st == 200, detail(tcbad))
if tcbad.get("id"):
    api("DELETE", f"/testcases/{tcbad['id']}", ADMIN)
# 项目级天数进入计划时间推算
st, plan = api("POST", "/plans", ADMIN, json={"project_id": NEW_PID, "version": "P2-3模板批次"})
check("D19 新项目建计划", st == 200, detail(plan))
PLAN_ID = plan.get("id")
def _dt(val):
    from datetime import datetime
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


if plan.get("sit_start") and plan.get("pre_end"):
    sit_days = (_dt(plan["sit_end"]) - _dt(plan["sit_start"])).days
    pre_days = (_dt(plan["pre_end"]) - _dt(plan["uat_end"])).days
    check("D20 计划阶段天数取模板值", sit_days == 12 and pre_days == 2, (sit_days, pre_days, plan))
else:
    check("D20 计划阶段天数取模板值", False, plan)
# 重复套用不堆叠
st, re1 = api("POST", f"/project-templates/{TPL_ID}/apply", ADMIN, params={"project_id": NEW_PID})
check("D21 重复套用全部跳过", st == 200 and re1["gates"] == 0 and re1["custom_fields"] == 0 and re1["skipped"] >= 5, re1)
st, gates2 = api("GET", "/gates", ADMIN, params={"project_id": NEW_PID})
check("D22 门禁未重复堆叠", len(gates2) == 2, len(gates2))
# 套到已有项目
st, re2 = api("POST", f"/project-templates/{TPL_ID}/apply", ADMIN, params={"project_id": PROJECT_ID})
check("D23 套用至已有项目", st == 200 and re2["gates"] == 2, detail(re2))
st, collect = api("GET", f"/project-templates/collect/{PROJECT_ID}", ADMIN)
check("D24 从项目反建模板草稿", st == 200 and collect["custom_fields"] and "stage_days" in collect, detail(collect))
st, collect404 = api("GET", "/project-templates/collect/999999", ADMIN)
check("D25 收集不存在项目 404", st == 404, detail(collect404))
st, apply404 = api("POST", f"/project-templates/{TPL_ID}/apply", ADMIN, params={"project_id": 999999})
check("D26 套用不存在项目 404", st == 404, detail(apply404))
st, delused = api("DELETE", f"/project-templates/{TPL_ID}", ADMIN)
check("D27 被引用模板不能删除", st == 400 and "记录了该模板来源" in detail(delused), detail(delused))
st, clr = api("PUT", f"/projects/{PROJECT_ID}", ADMIN, json={"template_id": None})
check("D28 项目可解除模板来源", st == 200 and clr["template_id"] is None, detail(clr))
st, clrbad = api("PUT", f"/projects/{NEW_PID}", ADMIN, json={"template_id": 999999})
check("D29 来源指向不存在模板 400", st == 400 and "模板" in detail(clrbad), detail(clrbad))

# ---------- E. 权限与日志 ----------
st, u = api("POST", "/users", ADMIN, json={"username": UNAME, "password": TEST_PWD,
                                            "display_name": "字典自测员", "role": "user"})
check("E0 创建普通用户", st == 200, detail(u))
uid = u.get("id")
MEM = login(UNAME, "Test123456")
st, gd = api("GET", "/dict", MEM, params={"dict_key": "case_priority"})
check("E1 普通用户可读全局字典", st == 200 and len(gd) >= 4, detail(gd))
st, gt = api("GET", "/dict/types", MEM)
check("E2 普通用户可读类型目录", st == 200, detail(gt))
st, gg = api("POST", "/dict", MEM, json={"dict_key": "case_priority", "label": "越权全局项"})
check("E3 非管理员建全局项 403", st == 403 and "管理员" in detail(gg), detail(gg))
st, gt2 = api("POST", "/project-templates", MEM, json={"name": "越权模板"})
check("E4 非管理员建模板 403", st == 403, detail(gt2))
st, gp = api("GET", f"/dict/options", MEM, params={"dict_key": "case_priority", "project_id": NEW_PID})
check("E5 非项目成员读项目字典 403", st == 403, detail(gp))
st, gc = api("POST", "/dict", MEM, json={"dict_key": "case_priority", "project_id": PROJECT_ID, "label": "成员项"})
check("E6 非项目成员改项目字典 403", st == 403, detail(gc))
st, join = api("POST", f"/p2/roles/{PROJECT_ID}", ADMIN, json={"user_id": uid, "role": "tester"})
check("E7 加入项目", st == 200, detail(join))
st, gc2 = api("POST", "/dict", MEM, json={"dict_key": "case_priority", "project_id": PROJECT_ID, "label": "成员项", "sort_order": 50})
check("E8 成员可加项目级选项", st == 200, detail(gc2))
member_item = gc2.get("id")
st, gc3 = api("PUT", f"/dict/{member_item}", MEM, json={"label": "成员项改名"})
check("E9 成员可改自己的项", st == 200, detail(gc3))
st, gb = api("DELETE", f"/dict/{builtin['id']}", MEM)
check("E10 成员不能删全局内置项 403", st == 403 and "管理员" in detail(gb), detail(gb))
st, grn = api("PUT", f"/dict/{builtin['id']}", MEM, json={"enabled": False})
check("E10b 成员不能改全局内置项 403", st == 403, detail(grn))
st, still = api("GET", "/dict", MEM, params={"dict_key": "case_priority"})
check("E10c 内置项未受影响", any(x.get("id") == builtin["id"] and x["enabled"] for x in still), still)
api("DELETE", f"/p2/roles/{PROJECT_ID}/{uid}", ADMIN)
st, after_leave = api("POST", "/dict", MEM, json={"dict_key": "case_priority", "project_id": PROJECT_ID, "label": "离职后新增"})
check("E10d 移出项目后不能再改项目字典", st == 403, detail(after_leave))
st, lg = api("GET", "/logs", ADMIN, params={"action": "新增", "page_size": 60})
check("E11 字典操作写日志", any("字典#" in str(x.get("target", "")) for x in lg["items"]), lg.get("total"))
check("E12 模板操作写日志", any("模板#" in str(x.get("target", "")) for x in lg["items"]), lg.get("total"))
st, lg2 = api("GET", "/logs", ADMIN, params={"action": "创建", "page_size": 60})
check("E13 项目创建日志记录模板", any("套用模板" in str(x.get("detail", "")) for x in lg2["items"]),
      [x["detail"] for x in lg2["items"][:3]])
st, lg3 = api("GET", "/logs", ADMIN, params={"action": "编辑", "page_size": 60})
check("E14 套用模板留痕", any("套用模板「" in str(x.get("detail", "")) for x in lg3["items"]),
      [x["detail"] for x in lg3["items"][:3]])
api("DELETE", f"/users/{uid}", ADMIN)

# ---------- F. 数据库结构 ----------
with engine.connect() as conn:
    fk = conn.execute(text(
        "SELECT rc.REFERENCED_TABLE_NAME, rc.DELETE_RULE "
        "FROM information_schema.REFERENTIAL_CONSTRAINTS rc "
        "JOIN information_schema.KEY_COLUMN_USAGE k "
        "  ON k.CONSTRAINT_SCHEMA=rc.CONSTRAINT_SCHEMA AND k.CONSTRAINT_NAME=rc.CONSTRAINT_NAME "
        "WHERE rc.CONSTRAINT_SCHEMA=DATABASE() AND k.TABLE_NAME='projects' AND k.COLUMN_NAME='template_id'")).fetchone()
    check("F1 projects.template_id 外键存在", bool(fk) and fk[0] == "project_templates", fk)
    check("F2 外键规则 SET NULL", bool(fk) and fk[1] == "SET NULL", fk)
    for tbl in ("dict_items", "project_templates"):
        ex = conn.execute(text("SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() "
                               f"AND TABLE_NAME='{tbl}'")).fetchone()
        check(f"F3 {tbl} 表已建", bool(ex))
    sev = conn.execute(text("SELECT COLUMN_DEFAULT FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                             "AND TABLE_NAME='defects' AND COLUMN_NAME='severity'")).fetchone()
    check("F4 缺陷严重程度默认值改为一般", sev and str(sev[0]) == "一般", sev)
    dk = conn.execute(text("SELECT COUNT(*) FROM dict_items WHERE project_id IS NULL AND builtin=1")).scalar()
    check("F5 内置字典默认项已播种", dk >= 19, dk)

# ---------- 清理 ----------
if NEW_PID:
    api("DELETE", f"/projects/{NEW_PID}", ADMIN)
st, gates_after = api("GET", "/gates", ADMIN, params={"project_id": NEW_PID})
check("G1 项目删除级联清理门禁", st in (200, 404) and (not isinstance(gates_after, list) or len(gates_after) == 0), gates_after)
for item_id in [x for x in [rq_item_id] if x]:
    api("DELETE", f"/dict/{item_id}", ADMIN)
st, rows = api("GET", "/dict", ADMIN, params={"dict_key": "case_priority", "project_id": PROJECT_ID})
if isinstance(rows, list):
    for r in rows:
        if r.get("id") and r.get("source") == "project":
            api("DELETE", f"/dict/{r['id']}", ADMIN)
for did in [d for d in [dft_id, dgen_id] if d]:
    api("DELETE", f"/defects/{did}", ADMIN)
for rid in [r for r in [rq2_id] if r]:
    api("DELETE", f"/requirements/{rid}", ADMIN)
if mod_id:
    api("DELETE", f"/testcases/{mod_id}", ADMIN)
if NEW_TC:
    api("DELETE", f"/testcases/{NEW_TC}", ADMIN)
# 只删除本次模板套用新增的门禁,原有门禁保持不动
st, gates_left = api("GET", "/gates", ADMIN, params={"project_id": PROJECT_ID})
if isinstance(gates_left, list):
    for g in gates_left:
        if g.get("id") not in gates_before:
            api("DELETE", f"/gates/{g['id']}", ADMIN)
st, gates_after2 = api("GET", "/gates", ADMIN, params={"project_id": PROJECT_ID})
check("G4 项目原有门禁未受影响", isinstance(gates_after2, list)
      and {g["id"] for g in gates_after2} == gates_before, gates_after2)
st, tpl_del = api("DELETE", f"/project-templates/{TPL_ID}", ADMIN)
check("G2 项目删除后模板可删", st == 200, detail(tpl_del))
if TPL2_ID:
    api("DELETE", f"/project-templates/{TPL2_ID}", ADMIN)
st, final = api("GET", "/dict/options", ADMIN, params={"dict_key": "case_priority", "project_id": PROJECT_ID})
check("G3 自测字典项已清理", {x["label"] for x in final} == {"P0", "P1", "P2", "P3"}, final)

print()
print(f"PASS {ok} / FAIL {fail}")
if fails:
    print("FAILED:", "; ".join(fails))
sys.exit(1 if fail else 0)
