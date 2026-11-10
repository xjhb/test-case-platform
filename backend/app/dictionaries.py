"""数据字典:可配置枚举项的类型目录与读取/校验工具。

阶段、执行结果状态、评审状态、缺陷状态机不在字典范围内 —— 它们被门禁、
通过率统计、待办路由和状态机直接依赖,允许改名会让报表静默失真。
"""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import DictItem

# (label, color, sort_order, is_urgent) —— 内置默认项,首次启动时写入为全局行
DICT_TYPES = [
    {
        "key": "case_priority",
        "name": "用例优先级",
        "mode": "validate",
        "has_urgent": True,
        "defaults": [
            ("P0", "danger", 1, True),
            ("P1", "warning", 2, True),
            ("P2", "primary", 3, False),
            ("P3", "info", 4, False),
        ],
    },
    {
        "key": "case_module",
        "name": "用例模块",
        "mode": "suggest",
        "has_urgent": False,
        "defaults": [
            ("登录", "info", 1, False),
            ("交易", "info", 2, False),
            ("退款", "info", 3, False),
            ("报表", "info", 4, False),
        ],
    },
    {
        "key": "defect_severity",
        "name": "缺陷严重程度",
        "mode": "validate",
        "has_urgent": True,
        "defaults": [
            ("致命", "danger", 1, True),
            ("严重", "danger", 2, True),
            ("一般", "warning", 3, False),
            ("提示", "info", 4, False),
        ],
    },
    {
        "key": "defect_priority",
        "name": "缺陷优先级",
        "mode": "validate",
        "has_urgent": True,
        "defaults": [
            ("P0", "danger", 1, True),
            ("P1", "warning", 2, True),
            ("P2", "primary", 3, False),
            ("P3", "info", 4, False),
        ],
    },
    {
        "key": "requirement_priority",
        "name": "需求优先级",
        "mode": "validate",
        "has_urgent": False,
        "defaults": [
            ("高", "danger", 1, False),
            ("中", "warning", 2, False),
            ("低", "info", 3, False),
        ],
    },
]

TYPE_KEYS = {t["key"]: t for t in DICT_TYPES}

# 固定枚举:只读展示,方便使用者知道哪些口径不能改
LOCKED_TYPES = [
    {"key": "stage", "name": "测试阶段", "values": ["SIT", "UAT", "PRE"],
     "reason": "阶段推进、门禁规则、报告分阶段统计均按此固定顺序取数"},
    {"key": "run_status", "name": "执行结果", "values": ["未执行", "通过", "失败", "阻塞"],
     "reason": "通过率、执行率与准出门禁直接按这几个值聚合"},
    {"key": "review_status", "name": "用例评审状态", "values": ["草稿", "评审中", "已批准", "已驳回"],
     "reason": "评审计数与「已批准」门禁条件依赖固定状态串"},
    {"key": "defect_status", "name": "缺陷状态", "values": ["新建", "处理中", "已修复", "已验证", "关闭", "重新打开"],
     "reason": "缺陷状态机与待办、通知路由依赖这组状态及其流转关系"},
]


def _spec(dict_key: str) -> dict:
    spec = TYPE_KEYS.get(dict_key)
    if not spec:
        raise ValueError(f"未知的字典类型: {dict_key}")
    return spec


def seed_defaults(db: Session) -> int:
    """把内置默认项写成全局行(project_id 为空),已存在则跳过。返回新增条数。"""
    existing = set(db.execute(
        select(DictItem.dict_key, DictItem.label).where(DictItem.project_id.is_(None))
    ).all())
    added = 0
    for spec in DICT_TYPES:
        for label, color, sort_order, is_urgent in spec["defaults"]:
            if (spec["key"], label) in existing:
                continue
            db.add(DictItem(
                dict_key=spec["key"], project_id=None, label=label, color=color,
                sort_order=sort_order, enabled=True, is_urgent=is_urgent, builtin=True,
            ))
            added += 1
    if added:
        db.flush()
    return added


def _rows(db: Session, dict_key: str, project_id: int | None) -> list[DictItem]:
    """全局行 + (可选)当前项目行;其他项目的行不能混进来,否则自定义项会跨项目串味"""
    scope = DictItem.project_id.is_(None)
    if project_id:
        scope = or_(DictItem.project_id.is_(None), DictItem.project_id == project_id)
    return list(db.execute(
        select(DictItem).where(DictItem.dict_key == dict_key, scope)
    ).scalars())


def stored_rows(db: Session, dict_key: str, project_id: int | None = None) -> list[DictItem]:
    """配置页取数据库里的真实行(含停用项),内置默认由调用方补齐"""
    return _rows(db, dict_key, project_id)


def effective(db: Session, dict_key: str, project_id: int | None = None) -> list[dict]:
    """全局默认项 + 项目级覆盖项;项目级同名 label 覆盖全局,enabled=False 表示隐藏。"""
    spec = _spec(dict_key)
    rows = _rows(db, dict_key, project_id)
    merged: dict[str, dict] = {}
    for label, color, sort_order, is_urgent in spec["defaults"]:
        merged[label] = {
            "id": None, "label": label, "color": color, "sort_order": sort_order,
            "enabled": True, "is_urgent": is_urgent, "builtin": True, "source": "default",
        }
    for r in sorted(rows, key=lambda x: (x.project_id is not None, x.sort_order or 0)):
        merged[r.label] = {
            "id": r.id, "label": r.label, "color": r.color or "", "sort_order": r.sort_order or 0,
            "enabled": bool(r.enabled), "is_urgent": bool(r.is_urgent), "builtin": bool(r.builtin),
            "source": "project" if r.project_id else "global",
        }
    return sorted(merged.values(), key=lambda x: (x["sort_order"], x["label"]))


def options(db: Session, dict_key: str, project_id: int | None = None) -> list[dict]:
    """下拉框使用的启用项。"""
    return [x for x in effective(db, dict_key, project_id) if x["enabled"]]


def labels(db: Session, dict_key: str, project_id: int | None = None) -> set[str]:
    return {x["label"] for x in options(db, dict_key, project_id)}


def top_label(db: Session, dict_key: str, project_id: int | None = None) -> str:
    """排最前的启用项,用于「最高优先级」这类统计口径,免得把 P0 写死在代码里"""
    items = options(db, dict_key, project_id)
    return items[0]["label"] if items else ""


def urgent_labels(db: Session, dict_key: str, project_id: int | None = None) -> set[str]:
    return {x["label"] for x in options(db, dict_key, project_id) if x["is_urgent"]}


def color_map(db: Session, dict_key: str, project_id: int | None = None) -> dict[str, str]:
    return {x["label"]: x["color"] for x in options(db, dict_key, project_id) if x["color"]}


def normalize(db: Session, dict_key: str, value: str, project_id: int | None = None,
              preferred: str = "") -> str:
    """外部系统/导入来源的值映射到字典项:命中就用,否则退到 preferred 或首个启用项。"""
    allowed = [x["label"] for x in options(db, dict_key, project_id)]
    if value in allowed:
        return value
    if preferred and preferred in allowed:
        return preferred
    return allowed[0] if allowed else (value or preferred)


def check(db: Session, dict_key: str, value: str, project_id: int | None = None,
          current: str | None = None) -> str:
    """校验入库值。suggest 模式不校验;validate 模式允许保留历史值以免旧数据无法编辑。"""
    spec = _spec(dict_key)
    if spec["mode"] != "validate":
        return value
    allowed = labels(db, dict_key, project_id)
    if value in allowed or (current is not None and value == current):
        return value
    raise ValueError(f"{spec['name']}只能是: {'/'.join(sorted(allowed))}")


def check_400(db: Session, dict_key: str, value: str, project_id: int | None = None,
              current: str | None = None) -> str:
    """路由层用的校验:不合法直接 400。"""
    from fastapi import HTTPException

    try:
        return check(db, dict_key, value, project_id, current)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
