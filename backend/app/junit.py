"""JUnit XML 解析

支持 CI 产出的标准 JUnit 格式(单个或多个 testsuite),把用例结果映射到平台状态:
failure/error → 失败, skipped → 阻塞, 其余 → 通过。
"""
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

MAX_XML_BYTES = 10 * 1024 * 1024  # 单文件 10MB
MAX_CASES = 2000  # 防止异常大文件拖垮请求
MAX_MESSAGE = 1000


class JUnitParseError(ValueError):
    pass


@dataclass
class JUnitCase:
    name: str
    classname: str = ""
    suite: str = ""
    status: str = "通过"  # 通过/失败/阻塞
    time_seconds: float = 0.0
    message: str = ""
    file_name: str = ""
    testcase_id: int | None = None  # 导入时匹配到的平台用例ID

    @property
    def duration_seconds(self) -> int:
        return int(round(self.time_seconds))


@dataclass
class JUnitReport:
    cases: list[JUnitCase] = field(default_factory=list)
    suites: list[dict] = field(default_factory=list)

    @property
    def by_status(self) -> dict[str, int]:
        out = {"通过": 0, "失败": 0, "阻塞": 0}
        for c in self.cases:
            out[c.status] = out.get(c.status, 0) + 1
        return out


def _attr(el: ET.Element, key: str) -> str:
    return (el.get(key) or "").strip()


def _text(el: ET.Element) -> str:
    return " ".join((el.text or "").split())


def _time(el: ET.Element) -> float:
    raw = _attr(el, "time")
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


def _message(case: ET.Element) -> tuple[str, str]:
    """返回 (状态, 失败信息);一个 testcase 可能有多个 failure(参数化用例)"""
    for child in case:
        tag = child.tag.lower()
        if tag in ("failure", "error"):
            msg = _attr(child, "message") or _text(child)
            detail = _text(child)
            combined = f"{msg}: {detail}" if msg and detail and msg != detail else (msg or detail)
            return "失败", combined[:MAX_MESSAGE]
        if tag == "skipped":
            return "阻塞", (_attr(child, "message") or _text(child))[:MAX_MESSAGE]
    return "通过", ""


def _parse_suite(suite: ET.Element, file_name: str, report: JUnitReport) -> None:
    suite_name = _attr(suite, "name")
    report.suites.append({
        "name": suite_name,
        "tests": int(_attr(suite, "tests")) if _attr(suite, "tests").isdigit() else 0,
        "failures": _attr(suite, "failures"),
        "errors": _attr(suite, "errors"),
        "skipped": _attr(suite, "skipped"),
        "time": _attr(suite, "time"),
    })
    for case in suite.findall("testcase"):
        name = _attr(case, "name")
        if not name:
            continue
        status, message = _message(case)
        report.cases.append(
            JUnitCase(
                name=name,
                classname=_attr(case, "classname"),
                suite=suite_name,
                status=status,
                time_seconds=_time(case),
                message=message,
                file_name=file_name,
            )
        )
        if len(report.cases) > MAX_CASES:
            raise JUnitParseError(f"用例数超过上限 {MAX_CASES},请检查产出文件是否正确")


def parse_junit(data: bytes, file_name: str = "") -> JUnitReport:
    if len(data) > MAX_XML_BYTES:
        raise JUnitParseError("XML 文件超过 10MB 上限")
    if not data.strip():
        raise JUnitParseError("XML 文件内容为空")

    root = _parse_root(data)
    report = JUnitReport()

    if root.tag.lower() == "testsuite":
        suites = [root]
    elif root.tag.lower() == "testsuites":
        suites = root.findall("testsuite")
        if not suites:
            # 少数工具把 testcase 直接挂在 testsuites 下
            suites = [root]
    else:
        raise JUnitParseError(f"不是 JUnit XML 格式,根节点为 <{root.tag}>")

    for suite in suites:
        _parse_suite(suite, file_name, report)
    return report


def _parse_root(data: bytes) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        # CI 机器上常用 GBK 输出但漏写声明,按 UTF-8 → GBK 依次回退
        for enc in ("utf-8-sig", "gbk"):
            try:
                return ET.fromstring(data.decode(enc).encode("utf-8"))
            except (UnicodeDecodeError, ET.ParseError):
                continue
        raise JUnitParseError("XML 解析失败,文件可能不是合法 XML 或编码无法识别")
