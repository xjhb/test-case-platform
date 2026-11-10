import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin, require_can_edit, require_project_access
from ..gates import RULES, STAGES, KINDS
from ..logger import log_op
from ..models import (
    CustomField,
    DictItem,
    Project,
    ProjectTemplate,
    StageGate,
    Tag,
    User,
)
from ..dictionaries import TYPE_KEYS
from ..schemas import TemplateCreate, TemplateOut, TemplateUpdate

router = APIRouter(prefix="/api/project-templates", tags=["项目模板"], dependencies=[Depends(get_current_user)])


def _loads(text: str, default):
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def _to_out(t: ProjectTemplate) -> TemplateOut:
    return TemplateOut(
        id=t.id, name=t.name, description=t.description or "",
        stage_days=_loads(t.stage_days, {}), gates=_loads(t.gates, []),
        custom_fields=_loads(t.custom_fields, []), tags=_loads(t.tags, []),
        dict_items=_loads(t.dict_items, []), is_default=bool(t.is_default),
        created_by=t.created_by, created_at=t.created_at, updated_at=t.updated_at,
    )


def _validate_payload(data: dict):
    for key, value in (data.get("stage_days") or {}).items():
        if key not in ("SIT", "UAT", "PRE"):
            raise HTTPException(status_code=400, detail=f"阶段只能是 SIT/UAT/PRE,收到 {key}")
        if not isinstance(value, int) or value < 1 or value > 365:
            raise HTTPException(status_code=400, detail=f"{key} 天数需为 1-365 的整数")
    for g in data.get("gates") or []:
        if g.get("stage") not in STAGES:
            raise HTTPException(status_code=400, detail=f"门禁阶段非法: {g.get('stage')}")
        if g.get("kind") not in KINDS:
            raise HTTPException(status_code=400, detail=f"门禁类型非法: {g.get('kind')}")
        if g.get("rule") not in RULES:
            raise HTTPException(status_code=400, detail=f"门禁规则非法: {g.get('rule')}")
        try:
            threshold = float(g.get("threshold"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"门禁阈值需为数字: {g.get('threshold')}")
        if threshold < 0:
            raise HTTPException(status_code=400, detail="门禁阈值不能为负数")
    for d in data.get("dict_items") or []:
        if d.get("dict_key") not in TYPE_KEYS:
            raise HTTPException(status_code=400, detail=f"未知字典类型: {d.get('dict_key')}")
        if not str(d.get("label") or "").strip():
            raise HTTPException(status_code=400, detail="字典选项名称不能为空")
    for f in data.get("custom_fields") or []:
        if not str(f.get("name") or "").strip():
            raise HTTPException(status_code=400, detail="自定义字段名不能为空")
        if f.get("field_type", "text") not in ("text", "select", "number", "date"):
            raise HTTPException(status_code=400, detail=f"字段类型非法: {f.get('field_type')}")


def apply_template(db: Session, template: ProjectTemplate, project_id: int) -> dict:
    """把模板内容套用到项目,已存在的同名配置跳过,返回各项写入与跳过条数"""
    stats = {"stage_days": 0, "gates": 0, "custom_fields": 0, "tags": 0, "dict_items": 0, "skipped": 0}
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    days = _loads(template.stage_days, {})
    changed = False
    for key, col in (("SIT", "default_sit_days"), ("UAT", "default_uat_days"), ("PRE", "default_pre_days")):
        if isinstance(days.get(key), int) and getattr(project, col) != days[key]:
            setattr(project, col, days[key])
            changed = True
    if changed:
        stats["stage_days"] = 1

    existing_gates = {(g.stage, g.kind, g.rule) for g in db.execute(
        select(StageGate).where(StageGate.project_id == project_id)).scalars()}
    for g in _loads(template.gates, []):
        sig = (g["stage"], g["kind"], g["rule"])
        if sig in existing_gates:
            stats["skipped"] += 1
            continue
        db.add(StageGate(project_id=project_id, stage=g["stage"], kind=g["kind"], rule=g["rule"],
                         threshold=float(g.get("threshold", 0)), enabled=bool(g.get("enabled", True))))
        existing_gates.add(sig)
        stats["gates"] += 1

    existing_fields = {f.name for f in db.execute(
        select(CustomField).where(CustomField.project_id == project_id)).scalars()}
    for f in _loads(template.custom_fields, []):
        if f["name"] in existing_fields:
            stats["skipped"] += 1
            continue
        opts = f.get("options")
        db.add(CustomField(
            project_id=project_id, name=f["name"], field_type=f.get("field_type", "text"),
            options=json.dumps(opts, ensure_ascii=False) if opts else "",
            required=bool(f.get("required", False)), sort_order=int(f.get("sort_order", 0)),
        ))
        existing_fields.add(f["name"])
        stats["custom_fields"] += 1

    existing_tags = {t.name for t in db.execute(select(Tag).where(Tag.project_id == project_id)).scalars()}
    for t in _loads(template.tags, []):
        name = str(t.get("name") or "").strip()
        if not name or name in existing_tags:
            stats["skipped"] += 1
            continue
        db.add(Tag(project_id=project_id, name=name, color=t.get("color") or "#409EFF"))
        existing_tags.add(name)
        stats["tags"] += 1

    existing_dict = {(d.dict_key, d.label) for d in db.execute(
        select(DictItem).where(DictItem.project_id == project_id)).scalars()}
    for d in _loads(template.dict_items, []):
        sig = (d["dict_key"], d["label"])
        if sig in existing_dict:
            stats["skipped"] += 1
            continue
        spec = TYPE_KEYS[d["dict_key"]]
        db.add(DictItem(
            dict_key=d["dict_key"], project_id=project_id, label=d["label"],
            color=d.get("color") or "", sort_order=int(d.get("sort_order", 0)),
            enabled=bool(d.get("enabled", True)),
            is_urgent=bool(d.get("is_urgent", False)) if spec["has_urgent"] else False,
            builtin=False, remark=d.get("remark") or "",
        ))
        existing_dict.add(sig)
        stats["dict_items"] += 1

    db.commit()
    return stats


@router.get("", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    rows = db.execute(select(ProjectTemplate).order_by(ProjectTemplate.is_default.desc(), ProjectTemplate.id)).scalars()
    return [_to_out(t) for t in rows]


@router.post("", response_model=TemplateOut)
def create_template(payload: TemplateCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_admin(current)
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="模板名称不能为空")
    if db.execute(select(ProjectTemplate).where(ProjectTemplate.name == name)).scalars().first():
        raise HTTPException(status_code=400, detail=f"模板「{name}」已存在")
    data = payload.model_dump()
    _validate_payload(data)
    if payload.is_default:
        for t in db.execute(select(ProjectTemplate)).scalars():
            t.is_default = False
    tpl = ProjectTemplate(
        name=name, description=payload.description or "",
        stage_days=json.dumps(data.get("stage_days") or {}, ensure_ascii=False),
        gates=json.dumps(data.get("gates") or [], ensure_ascii=False),
        custom_fields=json.dumps(data.get("custom_fields") or [], ensure_ascii=False),
        tags=json.dumps(data.get("tags") or [], ensure_ascii=False),
        dict_items=json.dumps(data.get("dict_items") or [], ensure_ascii=False),
        is_default=bool(payload.is_default), created_by=current.id,
    )
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    log_op(db, current, "新增", target=f"模板#{tpl.id} {tpl.name}", detail=_summary(tpl))
    return _to_out(tpl)


def _summary(t: ProjectTemplate) -> str:
    return (f"天数{len(_loads(t.stage_days, {}))}项 门禁{len(_loads(t.gates, []))}条 "
            f"字段{len(_loads(t.custom_fields, []))}个 标签{len(_loads(t.tags, []))}个 "
            f"字典{len(_loads(t.dict_items, []))}项")


@router.put("/{tpl_id}", response_model=TemplateOut)
def update_template(tpl_id: int, payload: TemplateUpdate, db: Session = Depends(get_db),
                    current: User = Depends(get_current_user)):
    require_admin(current)
    tpl = db.get(ProjectTemplate, tpl_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    data = payload.model_dump(exclude_unset=True)
    _validate_payload(data)
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="模板名称不能为空")
        dup = db.execute(select(ProjectTemplate).where(ProjectTemplate.name == name,
                                                      ProjectTemplate.id != tpl_id)).scalars().first()
        if dup:
            raise HTTPException(status_code=400, detail=f"模板「{name}」已存在")
        data["name"] = name
    json_fields = {"stage_days": dict, "gates": list, "custom_fields": list, "tags": list, "dict_items": list}
    for key, default in json_fields.items():
        if key in data:
            value = data.pop(key)
            setattr(tpl, key, json.dumps(value if value is not None else default, ensure_ascii=False))
    if data.get("is_default"):
        for t in db.execute(select(ProjectTemplate).where(ProjectTemplate.id != tpl_id)).scalars():
            t.is_default = False
    for k, v in data.items():
        setattr(tpl, k, v)
    db.commit()
    db.refresh(tpl)
    log_op(db, current, "编辑", target=f"模板#{tpl.id} {tpl.name}", detail=_summary(tpl))
    return _to_out(tpl)


@router.delete("/{tpl_id}")
def delete_template(tpl_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_admin(current)
    tpl = db.get(ProjectTemplate, tpl_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    used = db.execute(select(Project).where(Project.template_id == tpl_id)).scalars().first()
    name = tpl.name
    if used:
        raise HTTPException(status_code=400, detail=f"项目「{used.name}」记录了该模板来源,请先编辑该项目或保留模板")
    was_default = bool(tpl.is_default)
    db.delete(tpl)
    db.commit()
    if was_default:
        # 默认模板被删后要有接替者,否则新建项目失去默认套用来源
        successor = db.execute(select(ProjectTemplate).order_by(ProjectTemplate.id)).scalars().first()
        if successor:
            successor.is_default = True
            db.commit()
    log_op(db, current, "删除", target=f"模板#{tpl_id} {name}", detail="删除项目模板")
    return {"ok": True}


@router.post("/{tpl_id}/apply")
def apply_to_project(tpl_id: int, project_id: int, db: Session = Depends(get_db),
                     current: User = Depends(get_current_user)):
    """把模板套到已有项目:同名配置跳过,不会重复堆叠"""
    tpl = db.get(ProjectTemplate, tpl_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    require_can_edit(project_id, db, current)
    stats = apply_template(db, tpl, project_id)
    project.template_id = tpl_id
    db.commit()
    log_op(db, current, "编辑", target=f"项目#{project_id} {project.name}",
           detail=f"套用模板「{tpl.name}」: 门禁+{stats['gates']} 字段+{stats['custom_fields']} "
                  f"标签+{stats['tags']} 字典+{stats['dict_items']} 跳过{stats['skipped']}")
    return {"template_id": tpl_id, "project_id": project_id, **stats}


@router.get("/collect/{project_id}")
def collect_from_project(project_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """把现有项目的配置整理成模板草稿,供"另存为模板"使用"""
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    require_project_access(project_id, db, current)
    project = db.get(Project, project_id)
    gates = [{"stage": g.stage, "kind": g.kind, "rule": g.rule, "threshold": g.threshold, "enabled": bool(g.enabled)}
             for g in db.execute(select(StageGate).where(StageGate.project_id == project_id).order_by(StageGate.id)).scalars()]
    fields = [{"name": f.name, "field_type": f.field_type, "options": _loads(f.options, []),
               "required": bool(f.required), "sort_order": f.sort_order}
              for f in db.execute(select(CustomField).where(CustomField.project_id == project_id).order_by(CustomField.sort_order, CustomField.id)).scalars()]
    tags = [{"name": t.name, "color": t.color}
            for t in db.execute(select(Tag).where(Tag.project_id == project_id).order_by(Tag.id)).scalars()]
    dicts = [{"dict_key": d.dict_key, "label": d.label, "color": d.color, "sort_order": d.sort_order,
              "enabled": bool(d.enabled), "is_urgent": bool(d.is_urgent)}
             for d in db.execute(select(DictItem).where(DictItem.project_id == project_id).order_by(DictItem.sort_order, DictItem.id)).scalars()]
    return {
        "name": f"{project.name} 模板",
        "description": f"从项目#{project_id} {project.name} 导出的配置",
        "stage_days": {k: v for k, v in {
            "SIT": project.default_sit_days, "UAT": project.default_uat_days,
            "PRE": project.default_pre_days,
        }.items() if isinstance(v, int)},
        "gates": gates, "custom_fields": fields, "tags": tags, "dict_items": dicts,
    }
