"""Read a developed photo in the display space used by the SD look library."""
import io
from PIL import Image, ImageCms, ImageOps


class NeedsProfile(ValueError):
    pass


def load_preview(path, assume_srgb=False, *, max_size=(1200, 900)):
    with Image.open(path, formats=("JPEG", "PNG")) as source:
        if source.width * source.height > 70_000_000:
            raise ValueError("照片超过 7000 万像素，请使用较小的预览副本")
        exif = source.getexif()
        exif_ifd = exif.get_ifd(34665)
        space = exif_ifd.get(40961, exif.get(40961))
        icc = source.info.get("icc_profile")
        interp = exif.get_ifd(40965).get(1, "") if 40965 in exif_ifd else ""
        if isinstance(interp, bytes):
            interp = interp.decode("ascii", errors="replace").rstrip("\0")
        if not icc and (space == 2 or interp == "R03"):
            raise ValueError("照片标记为 Adobe RGB，但缺少可转换的 ICC；请先导出带配置的 sRGB 副本")
        if not icc and space != 1 and "srgb" not in source.info and not assume_srgb:
            raise NeedsProfile("照片没有可用的 sRGB 标记。")
        image = ImageOps.exif_transpose(source)
        if max_size:
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
        if icc:
            try:
                converted = ImageCms.profileToProfile(image, ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                                                      ImageCms.createProfile("sRGB"), outputMode="RGB")
            except (ImageCms.PyCMSError, ValueError, OSError) as exc:
                raise ValueError("无法转换照片的 ICC 配置；请先导出 sRGB 的 JPG/PNG") from exc
            return converted, "ICC → sRGB"
        return image.convert("RGB"), "按 sRGB 预览" if assume_srgb else "sRGB"
