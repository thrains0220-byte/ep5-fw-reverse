"""Versioned style data; intentionally cannot manufacture an unqualified firmware."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo
import zlib

from .cube import parse_cube, compile_rgb17
from .preview import resample_report
from .project import Project
from .wire import (TABLE_BYTES, LUT_HEADER, INDEX_HEADER, SLOT_RECORD,
                   pack_lut, unpack_lut, pack_index, unpack_index)


RUNTIME_READY = False
NOTICE = (
    "E-P5 LUT Studio — 开发用风格数据包\n"
    "此 ZIP 没有相机升级固件，官方 E-P5 1.8 不会加载这些 LUT。\n"
    "通用机内 SD 加载器尚未发布；不得改文件名为 BIN 或放进 DCOLYMP 当作升级使用。\n"
    "所有 ART 分配目前是拟用配置，需配套机内接入验证。\n"
    "保留原始 .cube 及其来源/许可。预览与重采样误差不等于相机校色。\n"
).encode("utf-8")


def _files(project, library):
    if not isinstance(project, Project) or not project.bindings:
        raise ValueError("请先分配至少一个 ART 位置")
    ids = list(dict.fromkeys(b.look_id for b in project.bindings))
    if len(ids) > 16:
        raise ValueError("每个数据包最多包含 16 个不同风格")
    numbers = {look_id: i + 1 for i, look_id in enumerate(ids)}
    manifest = dict(application="EP5LUTStudio", schema=1, project=project.to_dict(),
                    camera_ready=False, firmware_file_created=False,
                    purpose="development style data, not installable firmware",
                    required_runtime="E-P5 SD LUT index protocol 2 (not released)",
                    looks=[])
    files, checksums = {}, {}
    for look_id, number in numbers.items():
        look = library.get(look_id)
        if not look.directly_compatible:
            raise ValueError(f"「{look.title}」需先确认输入、输出都是 sRGB 照片；Log 或未声明基底不能直接导出")
        name = f"EP5LUT/L{number:07d}.LUT"
        original = f"SOURCE/L{number:07d}.cube"
        table, source = library.table(look_id), library.source(look_id)
        cube = parse_cube(source)
        if (compile_rgb17(cube) != table or cube.side != look.side
                or resample_report(cube, table) != look.resample):
            raise ValueError("风格编译表或误差记录与原始 LUT 不一致，请重新导入")
        checksums[look_id] = zlib.crc32(table)
        files[name] = pack_lut(number, table)
        files[original] = source
        manifest["looks"].append(dict(id=look_id, number=number, title=look.title,
                                      file=name, source=original, source_url=look.source_url,
                                      notes=look.notes, source_side=look.side,
                                      input_encoding=look.input_encoding, output_encoding=look.output_encoding,
                                      table_sha256=look.table_sha256, resample=look.resample))
    files["EP5LUT/INDEX.EP5"] = pack_index(project, numbers, checksums)
    files["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    files["NOT_A_FIRMWARE.txt"] = NOTICE
    return files


def validate_style_archive(path):
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) > 36 or len(names) != len(set(names)) or "manifest.json" not in names:
            raise ValueError("重复或缺失的数据包条目")
        for info in archive.infolist():
            if (info.is_dir() or stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG)
                    or info.flag_bits & 1):
                raise ValueError("数据包不能含链接、特殊文件或加密条目")
        if ("NOT_A_FIRMWARE.txt" not in names
                or archive.getinfo("NOT_A_FIRMWARE.txt").file_size != len(NOTICE)
                or archive.read("NOT_A_FIRMWARE.txt") != NOTICE):
            raise ValueError("数据包用途说明缺失或已被改写")
        info = archive.getinfo("manifest.json")
        if info.file_size > 262144:
            raise ValueError("数据包清单过大")
        manifest = json.loads(archive.read(info).decode("utf-8"))
        if (not isinstance(manifest, dict) or manifest.get("application") != "EP5LUTStudio"
                or type(manifest.get("schema")) is not int or manifest.get("schema") != 1 or
                manifest.get("camera_ready") is not False or manifest.get("firmware_file_created") is not False):
            raise ValueError("不是已声明开发用途的风格包")
        project = Project.from_dict(manifest.get("project"))
        looks = manifest.get("looks")
        if not isinstance(looks, list) or not 1 <= len(looks) <= 16:
            raise ValueError("风格列表无效")
        expected = {"manifest.json", "NOT_A_FIRMWARE.txt", "EP5LUT/INDEX.EP5"}
        numbers, ids, checksums = {}, {}, {}
        for look in looks:
            if not isinstance(look, dict):
                raise ValueError("风格元数据无效")
            n, look_id = look.get("number"), look.get("id")
            if (type(n) is not int or not 1 <= n <= 16 or n in numbers
                    or not isinstance(look_id, str) or not re.fullmatch(r"[0-9a-f]{64}", look_id) or look_id in ids):
                raise ValueError("重复或无效的风格编号")
            if look.get("input_encoding") != "srgb" or look.get("output_encoding") != "srgb":
                raise ValueError("数据包颜色基底未确认")
            file, source = f"EP5LUT/L{n:07d}.LUT", f"SOURCE/L{n:07d}.cube"
            if look.get("file") != file or look.get("source") != source or file not in names or source not in names:
                raise ValueError("风格路径与编号不符")
            if archive.getinfo(file).file_size != TABLE_BYTES + LUT_HEADER.size or archive.getinfo(source).file_size > 32 * 1024 * 1024:
                raise ValueError("数据包内容尺寸无效")
            number, table = unpack_lut(archive.read(file))
            if number != n or hashlib.sha256(table).hexdigest() != look.get("table_sha256"):
                raise ValueError("风格内容与清单校验不符")
            original = archive.read(source)
            if hashlib.sha256(original).hexdigest() != look["id"]:
                raise ValueError("原始 LUT 校验不符")
            cube = parse_cube(original)
            if (type(look.get("source_side")) is not int or cube.side != look["source_side"]
                    or compile_rgb17(cube) != table or resample_report(cube, table) != look.get("resample")):
                raise ValueError("编译表或误差说明与原始 LUT 不一致")
            expected.update((file, source))
            numbers[n], ids[look["id"]] = look, n
            checksums[look["id"]] = zlib.crc32(table)
        if set(names) != expected:
            raise ValueError("数据包包含未声明的额外文件")
        if ("EP5LUT/INDEX.EP5" not in names or
                archive.getinfo("EP5LUT/INDEX.EP5").file_size > INDEX_HEADER.size + 32 * SLOT_RECORD.size):
            raise ValueError("位置索引过大")
        index = unpack_index(archive.read("EP5LUT/INDEX.EP5"))
        if {b.look_id for b in project.bindings} != set(ids) or archive.read("EP5LUT/INDEX.EP5") != pack_index(project, ids, checksums):
            raise ValueError("二进制位置配置与项目清单不一致")
    return dict(status="verified_development_data", camera_ready=False, firmware_file_created=False,
                looks=len(looks), bindings=len(index), project=project.name)


def export_project(project, library, path):
    path = Path(path)
    if path.suffix.lower() != ".zip":
        raise ValueError("风格数据包必须以 .zip 结尾，不能作为 BIN 固件保存")
    if path.exists():
        raise FileExistsError("文件已存在，请使用新的数据包名称")
    files = _files(project, library)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent, prefix=".ep5-export-") as folder:
        stage = Path(folder) / "data.zip"
        with ZipFile(stage, "x") as archive:
            for name, value in files.items():
                info = ZipInfo(name)
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, value, compress_type=ZIP_DEFLATED)
        report = validate_style_archive(stage)
        if os.name == "nt":
            stage.rename(path)
        else:
            os.link(stage, path)
    return report


def build_firmware(*args, **kwargs):
    raise RuntimeError("通用 SD LUT 机内模块尚未完成接入验证，没有生成可刷固件")
