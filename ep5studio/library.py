"""Content-addressed LUT originals, compiled data and explicit colour declarations."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import math

from .cube import parse_cube, compile_rgb17
from .preview import resample_report
from .project import atomic_write, text

ENCODINGS = {"unknown", "srgb", "rec709", "vlog"}
from .wire import TABLE_BYTES


def default_library():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share"))
    return base / "EP5LUTStudio" / "Library"


def sha(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Look:
    id: str
    title: str
    side: int
    input_encoding: str
    output_encoding: str
    source_filename: str
    source_url: str
    notes: str
    table_sha256: str
    resample: dict

    @property
    def directly_compatible(self):
        return self.input_encoding == self.output_encoding == "srgb"


class Library:
    def __init__(self, root=None):
        self.root = Path(root or default_library()).expanduser().resolve()
        self._check_storage()
        (self.root / "looks").mkdir(parents=True, exist_ok=True)
        self.errors = []

    def _check_storage(self):
        path = self.root / "looks"
        if path.is_symlink() or path.resolve() != path:
            raise ValueError("风格库存储目录不能是重定向链接")

    def folder(self, look_id):
        self._check_storage()
        if not isinstance(look_id, str) or not re.fullmatch(r"[0-9a-f]{64}", look_id):
            raise ValueError("无效的风格编号")
        return self.root / "looks" / look_id

    def get(self, look_id):
        folder = self.folder(look_id)
        for path in (folder, folder / "look.json", folder / "source.cube", folder / "table.rgb16le"):
            if path.is_symlink() or path.resolve() != path:
                raise ValueError("风格库条目不能是重定向链接")
        metadata = folder / "look.json"
        if metadata.stat().st_size > 131072:
            raise ValueError("风格元数据过大")
        value = json.loads(metadata.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or type(value.get("schema")) is not int or value.pop("schema", None) != 1:
            raise ValueError("不支持的风格库版本")
        try:
            look = Look(**value)
        except TypeError as err:
            raise ValueError("风格元数据字段无效") from err
        if (look.id != look_id or not isinstance(look.input_encoding, str) or not isinstance(look.output_encoding, str)
                or look.input_encoding not in ENCODINGS or look.output_encoding not in ENCODINGS):
            raise ValueError("风格身份或颜色声明无效")
        text(look.title)
        if (type(look.side) is not int or not 2 <= look.side <= 65 or not isinstance(look.table_sha256, str)
                or not re.fullmatch(r"[0-9a-f]{64}", look.table_sha256) or not isinstance(look.resample, dict)
                or not isinstance(look.source_filename, str) or not isinstance(look.source_url, str)
                or not isinstance(look.notes, str)):
            raise ValueError("风格元数据类型无效")
        for field in ("max_rgb8_error", "mean_rgb8_error"):
            value = look.resample.get(field)
            if type(value) not in (int, float) or not 0 <= value <= 255 or not math.isfinite(value):
                raise ValueError("风格误差记录无效")
        source = folder / "source.cube"
        table = folder / "table.rgb16le"
        if source.stat().st_size > 32 * 1024 * 1024 or table.stat().st_size != TABLE_BYTES:
            raise ValueError("风格数据尺寸无效")
        if sha(source.read_bytes()) != look_id or sha(table.read_bytes()) != look.table_sha256:
            raise ValueError("风格库校验失败，请重新导入原始 LUT")
        return look

    def source(self, look_id):
        self.get(look_id)
        return (self.folder(look_id) / "source.cube").read_bytes()

    def table(self, look_id):
        self.get(look_id)
        return (self.folder(look_id) / "table.rgb16le").read_bytes()

    def list_looks(self):
        result, self.errors = [], []
        for folder in (self.root / "looks").iterdir():
            if not re.fullmatch(r"[0-9a-f]{64}", folder.name):
                continue
            try:
                result.append(self.get(folder.name))
            except (OSError, ValueError, KeyError) as err:
                self.errors.append(f"{folder.name[:8]}：{err}")
        return sorted(result, key=lambda look: (look.title.casefold(), look.id))

    def import_file(self, path, *, input_encoding="unknown", output_encoding="unknown", source_url="", notes=""):
        path = Path(path)
        if path.suffix.lower() != ".cube":
            raise ValueError("请选择 .cube 文件")
        with path.open("rb") as fp:
            data = fp.read(32 * 1024 * 1024 + 1)
        return self.import_bytes(data, filename=path.name, input_encoding=input_encoding,
                                 output_encoding=output_encoding, source_url=source_url, notes=notes)

    def import_bytes(self, data, *, filename="look.cube", input_encoding="unknown", output_encoding="unknown", source_url="", notes=""):
        if input_encoding not in ENCODINGS or output_encoding not in ENCODINGS:
            raise ValueError("不支持的颜色声明")
        if not isinstance(data, bytes) or len(data) > 32 * 1024 * 1024:
            raise ValueError("LUT 文件超过 32 MiB")
        look_id = sha(data)
        folder = self.folder(look_id)
        if folder.exists():
            return self.get(look_id)
        cube = parse_cube(data)
        compiled = compile_rgb17(cube)
        if len(compiled) != TABLE_BYTES:
            raise ValueError("17³ 编译器输出长度无效")
        look = Look(look_id, text(cube.title or Path(filename).stem), cube.side,
                    input_encoding, output_encoding, Path(filename).name[:255], source_url[:2048],
                    notes[:4096], sha(compiled), resample_report(cube, compiled))
        with tempfile.TemporaryDirectory(dir=self.root / "looks", prefix=".import-") as tmp:
            stage = Path(tmp) / "look"
            stage.mkdir()
            (stage / "source.cube").write_bytes(data)
            (stage / "table.rgb16le").write_bytes(compiled)
            metadata = dict(schema=1, **look.__dict__)
            (stage / "look.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            # Windows can briefly hold a just-closed file open for scanning;
            # retry the atomic directory publish instead of failing the import.
            for attempt in range(10):
                try:
                    stage.rename(folder)
                    break
                except FileExistsError:
                    return self.get(look_id)
                except PermissionError:
                    if attempt == 9:
                        raise
                    time.sleep(0.05 * (attempt + 1))
        return self.get(look_id)

    def set_encodings(self, look_id, input_encoding, output_encoding):
        look = self.get(look_id)
        if input_encoding not in ENCODINGS or output_encoding not in ENCODINGS:
            raise ValueError("不支持的颜色声明")
        value = dict(schema=1, **look.__dict__)
        value.update(input_encoding=input_encoding, output_encoding=output_encoding)
        atomic_write(self.folder(look_id) / "look.json", (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        return self.get(look_id)

    def seed_defaults(self):
        from .builtins import default_cubes
        from .filmlooks import LOOK_SPECS
        notes_by_file = {name + ".cube": note for name, _t, _f, note in LOOK_SPECS}
        results = []
        for name, data in default_cubes():
            note = notes_by_file.get(name, "项目原创实验风格；未经机身校色，不声称复刻胶片。")
            results.append(self.import_bytes(data, filename=name, input_encoding="srgb", output_encoding="srgb",
                                             notes="项目原创程序化风格（胶片类型取向）；" + note))
        return results
