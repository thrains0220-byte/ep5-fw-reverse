"""Rasterize the C wheel draw-test trace using a local font for host review."""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("font", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    cell, line = 16, 32
    img = Image.new("RGB", (42*cell, 13*line))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(args.font), 24)
    for operation in args.trace.read_text("ascii").splitlines():
        kind, x, y, *tokens = operation.split()
        x, y = int(x)*cell, int(y)*line
        if kind == "F":
            w, h, color = int(tokens[0])*cell, int(tokens[1])*line, "#" + tokens[2]
            draw.rectangle((x,y,x+w-1,y+h-1),fill=color)
        elif kind == "T":
            text = "".join(chr(int(word,16)) for word in tokens[1:])
            draw.text((x,y+line//2),text,font=font,fill="#" + tokens[0],anchor="lm")
        else:
            raise ValueError(f"unknown operation {kind}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    img.save(args.out)


if __name__ == "__main__":
    main()
