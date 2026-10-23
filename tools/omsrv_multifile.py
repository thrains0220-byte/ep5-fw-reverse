#!/usr/bin/env python3
"""重查 OM Digital Solutions 的 MSRV 固件接口，检查响应里是否有**多个**文件。

背景（第二十轮）:
    第十七轮的 `sweep.py` 用 `re.search` 只取响应里**第一个** `<file_name>`，
    因此「每型号只返回一个文件」这个结论**可能是正则的盲区**。
    而响应结构 `<firmwares><firmware_info>…</firmware_info></firmwares>` 本身是列表。

本脚本:
    1. 对多个机型 / 多个 `firmup_mode` / 多个端点调用接口；
    2. 统计每个响应里 `<firmware_info>` 的**个数**，并列出**全部** file_name / file_size / up_date；
    3. 若某型号返回 ≥2 个文件 ⇒ 官方确实另发第二个文件（很可能是机身 mask ROM 映像）。

用法:
    python tools/omsrv_multifile.py [--proxy http://127.0.0.1:7890] [--out out.json]
"""
import argparse
import json
import os
import re
import subprocess
import time

CURL = r"C:\Windows\System32\curl.exe"
TPL = """<?xml version="1.0"?>
<firmware_demand>
<revision>0001</revision>
<mac_address>00-00-00-00-80-D6</mac_address>
<time>{time}</time>
<language>ENU</language>
<application>FWUT</application>
<type>0000</type>
<version>00005000</version>
<os>WIN</os>
<country_code>0001</country_code>
<hardwares>
<firmup_mode>{firmup_mode}</firmup_mode>
<hardware_info>
<hard_code>{hard_code}</hard_code>
<firmware_version>{firmware_version}</firmware_version>
<serial_no>V5PF30000</serial_no>
<default_languages>
<code>JPN</code><code>ENU</code><code>DEU</code>
</default_languages>
</hardware_info>
</hardwares>
</firmware_demand>
"""

# 机型码 -> (名称, hard_code 前缀)
MODELS = [
    ("E-P5", "1080", "OLYE108"),
    ("E-M5", "0970", "OLYE097"),
    ("E-M10", "1130", "OLYE113"),
    ("E-M1", "1090", "OLYE109"),
    ("E-M10II", "1200", "OLYE120"),
    ("PEN-F", "1220", "OLYE122"),
    ("E-M1III", "1390", "OLYE139"),
    ("E-M5II", "1180", "OLYE118"),
    ("E-M5III", "1370", "OLYE137"),
    ("E-PL9", "1330", "OLYE133"),
]


def call(endpoint, proxy, **kw):
    p = dict(revision="0001", time=time.strftime("%Y%m%d%H%M%S"), application="FWUT",
             type="0000", version="00005000", firmup_mode="0",
             hard_code="OLYE108000000000", firmware_version="00001000",
             serial_no="V5PF30000")
    p.update(kw)
    body = TPL.format(**p)
    req = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_omsrv_req.xml")
    with open(req, "w", encoding="utf-8") as f:
        f.write(body)
    url = "https://fw01.om-digitalsolutions.net/ww_inform/" + endpoint
    cmd = [CURL]
    if proxy:
        cmd += ["--proxy", proxy]
    cmd += ["-s", "-L", "--compressed", "-m", "45", "--user-agent", "Olympus",
            "--header", "Content-Type: text/xml; Charset=UTF-8",
            "--data-binary", "@" + req, "-w", "\n@@HTTP:%{http_code}", url]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    return r.stdout


def parse(xml):
    """完整解析：返回所有 firmware_info 的列表。"""
    infos = []
    for blk in re.findall(r"<firmware_info>(.*?)</firmware_info>", xml, re.S):
        d = {}
        for tag in ("maker_code", "model_name", "model_id", "version",
                    "file_name", "file_size", "up_date", "detail_url", "url",
                    "extension_comment", "comment"):
            m = re.search(r"<%s>(.*?)</%s>" % (tag, tag), blk, re.S)
            if m:
                d[tag] = m.group(1).replace("&amp;", "&")[:200]
        infos.append(d)
    http = re.search(r"@@HTTP:(\d+)", xml)
    return infos, (http.group(1) if http else "?")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy", default="http://127.0.0.1:7890")
    ap.add_argument("--out", default=None)
    ap.add_argument("--endpoints", default="fcache.do,firmware2.do")
    ap.add_argument("--modes", default="0,1,2,3")
    args = ap.parse_args()

    eps = [e.strip() for e in args.endpoints.split(",") if e.strip()]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]

    print("端点: %s   firmup_mode: %s\n" % (eps, modes))
    print("%-9s %-7s %-9s %-7s %-5s %s" % ("机型", "端点", "mode", "HTTP", "文件数", "file_name (size)"))
    print("-" * 118)
    results = []
    multi = []
    for name, mid, hc in MODELS:
        for ep in eps:
            for fm in modes:
                xml = call(ep, args.proxy, hard_code=hc + "000000000",
                           firmware_version="00001000", firmup_mode=fm)
                infos, http = parse(xml)
                names = ["%s (%s)" % (i.get("file_name"), i.get("file_size")) for i in infos]
                mark = ""
                if len(infos) >= 2:
                    mark = "  ★★ 多文件"
                    multi.append({"model": name, "endpoint": ep, "mode": fm,
                                  "http": http, "files": infos})
                print("%-9s %-7s %-9s %-7s %-5d %s%s" % (
                    name, ep, fm, http, len(infos), "; ".join(names)[:70], mark))
                results.append({"model": name, "endpoint": ep, "mode": fm,
                                "http": http, "n": len(infos), "files": infos})
                sys_out = True
    print()
    print("=== 返回 ≥2 个文件的组合 ===")
    if multi:
        for m in multi:
            print("  ★ %s  %s  mode=%s  HTTP=%s" % (m["model"], m["endpoint"], m["mode"], m["http"]))
            for i in m["files"]:
                print("      %s  size=%s  up_date=%s" % (
                    i.get("file_name"), i.get("file_size"), i.get("up_date")))
    else:
        print("  （无）")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"results": results, "multi_file": multi}, f, ensure_ascii=False, indent=1)
        print("\n[written] %s" % args.out)


if __name__ == "__main__":
    main()
