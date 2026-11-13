"""Portable, declarative look assignments; no device access or executable config."""
from dataclasses import dataclass, asdict
import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata


SCHEMA = 1
SLOT_SPECS = (
    ("pop-art-i", "浓郁色调 I", 100, 1), ("soft-focus-i", "柔焦 I", 101, 1),
    ("pale-light-i", "淡化增亮 I", 102, 1), ("light-tone-i", "柔光 I", 103, 1),
    ("grainy-film-i", "怀旧颗粒 I", 104, 1),
    ("pin-hole-i", "针孔 I", 105, 1), ("pin-hole-ii", "针孔 II", 105, 2),
    ("pin-hole-iii", "针孔 III", 105, 3), ("diorama-i", "立体效果 I", 106, 1),
    ("cross-process-i", "负片冲印 I", 107, 1), ("gentle-sepia-i", "柔和怀旧 I", 108, 1),
    ("dramatic-tone-i", "戏剧效果 I", 109, 1),
    ("key-line-i", "线描 I", 119, 1), ("watercolor-i", "水彩 I", 120, 1),
)
SLOTS = {row[0]: dict(id=row[0], label=row[1], picture_mode=row[2], variant=row[3],
                      runtime_verified=False) for row in SLOT_SPECS}


def text(value, maximum=120):
    if not isinstance(value, str):
        raise ValueError("名称必须是文字")
    value = unicodedata.normalize("NFC", value).strip()
    if not value or len(value) > maximum or not value.isprintable():
        raise ValueError(f"名称需为 1–{maximum} 个可显示字符")
    return value


def short_label(value):
    value = text(value, 12)
    if any(ord(c) > 0xffff or 0xd800 <= ord(c) <= 0xdfff for c in value) or len(value.encode("utf-16-le")) > 12:
        raise ValueError("机内短名最多 6 个字符，不支持表情或补充平面字符")
    return value


@dataclass(frozen=True)
class Binding:
    slot_id: str
    look_id: str
    label: str
    amount_q8: int = 256

    def __post_init__(self):
        if self.slot_id not in SLOTS or not isinstance(self.look_id, str) or not re.fullmatch(r"[0-9a-f]{64}", self.look_id):
            raise ValueError("无效的 ART 位置或风格编号")
        if short_label(self.label) != self.label:
            raise ValueError("机内短名不可有首尾空格")
        if type(self.amount_q8) is not int or not 0 <= self.amount_q8 <= 256:
            raise ValueError("风格强度必须在 0–256 范围")


@dataclass(frozen=True)
class Project:
    name: str = "我的 E-P5 风格"
    bindings: tuple[Binding, ...] = ()

    def __post_init__(self):
        if text(self.name) != self.name or not isinstance(self.bindings, tuple) or len(self.bindings) > 32:
            raise ValueError("项目名称或位置数量无效")
        if any(not isinstance(b, Binding) for b in self.bindings):
            raise ValueError("项目包含无效的风格分配")
        if len({b.slot_id for b in self.bindings}) != len(self.bindings):
            raise ValueError("一个 ART 位置不能同时分配两个风格")

    def to_dict(self):
        return dict(application="EP5LUTStudio", schema=SCHEMA, name=self.name,
                    bindings=[asdict(b) for b in self.bindings])

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {"application", "schema", "name", "bindings"}:
            raise ValueError("不是完整的 E-P5 风格项目")
        if value["application"] != "EP5LUTStudio" or type(value["schema"]) is not int or value["schema"] != SCHEMA:
            raise ValueError("不支持的项目版本")
        if not isinstance(value["bindings"], list) or len(value["bindings"]) > 32:
            raise ValueError("项目分配列表无效")
        try:
            rows = tuple(Binding(**r) for r in value["bindings"])
        except (TypeError, KeyError) as err:
            raise ValueError("项目分配字段无效") from err
        return cls(value["name"], rows)


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".ep5-", delete=False) as fp:
            temp = Path(fp.name)
            fp.write(data)
            fp.flush()
            os.fsync(fp.fileno())
        temp.replace(path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def save_project(project, path):
    atomic_write(path, (json.dumps(project.to_dict(), ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def load_project(path):
    with Path(path).open("rb") as fp:
        data = fp.read(131073)
    if len(data) > 131072:
        raise ValueError("项目文件超过 128 KiB")
    try:
        value = json.loads(data.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as err:
        raise ValueError("项目必须为 UTF-8 JSON") from err
    return Project.from_dict(value)
