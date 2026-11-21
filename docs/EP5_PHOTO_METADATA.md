# 在样片中记录 E-P5 胶片风格

宿主导出的 JPEG 带有标准 EXIF `UserComment`。它记录风格短名、分组、强度、色表编号和 CRC，以及 ART 模式和变体。短名支持现有索引允许的六个 BMP 字符，例如「柯达金」。从 SD 索引选择同名风格时，用分组和色表 CRC 区分。

`ep5studio.photo_metadata.build_photo_exif` 生成一次 JPEG 编码所需的 EXIF 字节。`read_photo_metadata` 可从导出的 JPEG 核对选择。强度使用与 SD 索引一致的 `0–256` 整数，分别对应 `0–100%`。写入时生成独立的 EXIF 段，原始照片和相机 MakerNotes 保持原样。

结合生成 JPEG 的测试使用同一张样图分别有标识和无标识地编码。移除带标识图片的 EXIF 段后，两份 JPEG 逐字节一致。这项验证适用于宿主处理链路，机身生成 JPEG 时写入标识仍待接入。
