from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin, require_can_edit, require_project_access
from ..dictionaries import DICT_TYPES, LOCKED_TYPES, TYPE_KEYS, effective, options, stored_rows
from ..logger import log_op
from ..models import DictItem, Project, User
from ..schemas import DictItemCreate, DictItemOut, DictItemUpdate

router = APIRouter(prefix="/api/dict", tags=["数据字典"], dependencies=[Depends(get_current_user)])


def _to_out(row: DictItem) -> DictItemOut:
    return DictItemOut(
        id=row.id, dict_key=row.dict_key, project_id=row.project_id, label=row.label,
        color=row.color or "", sort_order=row.sort_order or 0, enabled=bool(row.enabled),
        is_urgent=bool(row.is_urgent), builtin=bool(row.builtin), remark=row.remark or "",
        source="project" if row.project_id else "global",
    )


def _check_key(dict_key: str) -> dict:
    spec = TYPE_KEYS.get(dict_key)
    if not spec:
        raise HTTPException(status_code=400, detail=f"未知字典类型: {dict_key}")
    return spec


@router.get("/types")
def list_types():
    """字典类型目录:configurable 为可维护项,locked 为固定口径及原因"""
    return {
        "configurable": [
            {"key": t["key"], "name": t["name"], "mode": t["mode"], "has_urgent": t["has_urgent"],
             "defaults": [d[0] for d in t["defaults"]]}
            for t in DICT_TYPES
        ],
        "locked": LOCKED_TYPES,
    }


@router.get("/options")
def list_options(dict_key: str, project_id: int | None = None, db: Session = Depends(get_db),
                 current: User = Depends(get_current_user)):
    """下拉框取值:启用项 + 标签色,已按 sort_order 排好序"""
    _check_key(dict_key)
    if project_id:
        if not db.get(Project, project_id):
            raise HTTPException(status_code=404, detail="项目不存在")
        require_project_access(project_id, db, current)
    return options(db, dict_key, project_id)


@router.get("", response_model=list[DictItemOut])
def list_items(dict_key: str, project_id: int | None = None, db: Session = Depends(get_db),
               current: User = Depends(get_current_user)):
    """配置页视图:含被停用的项与来源标记"""
    _check_key(dict_key)
    if project_id:
        if not db.get(Project, project_id):
            raise HTTPException(status_code=404, detail="项目不存在")
        require_project_access(project_id, db, current)
    rows = stored_rows(db, dict_key, project_id)
    out = [_to_out(r) for r in sorted(rows, key=lambda x: (x.sort_order or 0, x.label))]
    stored = {r.label for r in rows}
    spec = TYPE_KEYS[dict_key]
    for label, color, sort_order, is_urgent in spec["defaults"]:
        if label in stored:
            continue
        out.append(DictItemOut(
            id=None, dict_key=dict_key, project_id=None, label=label, color=color,
            sort_order=sort_order, enabled=True, is_urgent=is_urgent, builtin=True, remark="",
            source="default",
        ))
    return sorted(out, key=lambda x: (x.sort_order, x.label))


@router.post("", response_model=DictItemOut)
def create_item(payload: DictItemCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    spec = _check_key(payload.dict_key)
    label = (payload.label or "").strip()
    if not label:
        raise HTTPException(status_code=400, detail="选项名称不能为空")
    if payload.project_id is None and current.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员能维护全局默认项")
    if payload.project_id:
        if not db.get(Project, payload.project_id):
            raise HTTPException(status_code=404, detail="项目不存在")
        require_can_edit(payload.project_id, db, current)
        dup = db.execute(select(DictItem).where(
            DictItem.dict_key == payload.dict_key,
            DictItem.project_id == payload.project_id,
            DictItem.label == label,
        )).scalars().first()
        if dup:
            raise HTTPException(status_code=400, detail=f"该项目下选项「{label}」已存在")
    elif db.execute(
        select(DictItem).where(DictItem.dict_key == payload.dict_key,
                               DictItem.project_id.is_(None), DictItem.label == label)
    ).scalars().first():
        raise HTTPException(status_code=400, detail=f"全局选项「{label}」已存在")

    row = DictItem(
        dict_key=payload.dict_key, project_id=payload.project_id, label=label,
        color=payload.color or "", sort_order=payload.sort_order, enabled=payload.enabled,
        is_urgent=payload.is_urgent if spec["has_urgent"] else False,
        builtin=False, remark=payload.remark or "",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    scope = "全局" if not payload.project_id else f"项目#{payload.project_id}"
    log_op(db, current, "新增", target=f"字典#{row.id} {spec['name']}/{label}",
           detail=f"{scope}; 色:{row.color or '默认'}; 紧急:{'是' if row.is_urgent else '否'}")
    return _to_out(row)


@router.put("/{item_id}", response_model=DictItemOut)
def update_item(item_id: int, payload: DictItemUpdate, db: Session = Depends(get_db),
                current: User = Depends(get_current_user)):
    row = db.get(DictItem, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="字典项不存在")
    if row.project_id:
        require_can_edit(row.project_id, db, current)
    else:
        require_admin(current)
    data = payload.model_dump(exclude_unset=True)
    label = (data.get("label") or "").strip() if "label" in data else row.label
    if not label:
        raise HTTPException(status_code=400, detail="选项名称不能为空")
    if label != row.label:
        spec = _check_key(row.dict_key)
        if row.builtin:
            raise HTTPException(status_code=400, detail=f"内置选项「{row.label}」不能改名,请新增项目级选项覆盖")
        dup = db.execute(select(DictItem).where(
            DictItem.dict_key == row.dict_key,
            DictItem.project_id.is_(None) if row.project_id is None else DictItem.project_id == row.project_id,
            DictItem.label == label,
        )).scalars().first()
        if dup:
            raise HTTPException(status_code=400, detail=f"选项「{label}」已存在")
    if "is_urgent" in data and not TYPE_KEYS[row.dict_key]["has_urgent"]:
        data.pop("is_urgent")
    for k, v in data.items():
        setattr(row, k, label if k == "label" else v)
    db.commit()
    db.refresh(row)
    log_op(db, current, "编辑", target=f"字典#{row.id} {row.dict_key}/{row.label}",
           detail=f"变更字段: {', '.join(sorted(data))}")
    return _to_out(row)


@router.delete("/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    row = db.get(DictItem, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="字典项不存在")
    if row.project_id:
        require_can_edit(row.project_id, db, current)
    else:
        require_admin(current)
    if row.builtin:
        raise HTTPException(
            status_code=400,
            detail=f"「{row.label}」是内置选项,不能删除;如需停用请置为不启用,或在项目下新增同名选项覆盖",
        )
    label, key = row.label, row.dict_key
    db.delete(row)
    db.commit()
    log_op(db, current, "删除", target=f"字典#{item_id} {key}/{label}", detail="删除自定义字典项")
    return {"ok": True}


@router.get("/effective")
def list_effective(project_id: int | None = None, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """一次取回全部字典类型的有效项,前端启动时缓存,避免逐个类型请求;不传项目则按全局口径"""
    if project_id:
        if not db.get(Project, project_id):
            raise HTTPException(status_code=404, detail="项目不存在")
        require_project_access(project_id, db, current)
    return {t["key"]: effective(db, t["key"], project_id) for t in DICT_TYPES}
