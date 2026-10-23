#!/usr/bin/env python3
"""按相机**当前固件版本**向 OM 的 fcache.do 请求，看服务端是否会返回**对应版本**的 .BIN。

依据（第 23 轮实测）:
    firmware_version=00001000 -> 返回 v1.8（最新版）
    firmware_version=00001800 -> file_name 为空（"没有更新的版本"）
⇒ 该字段表示"相机现在装的是哪个版本"，服务端据此决定返回什么。

用法:
    python tools/omsrv_version_probe.py --hard-code OLYE108000000000 --json out.json
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
<firmup_mode>0</firmup_mode>
<hardware_info>
<hard_code>{hard_code}</hard_code>
<firmware_version>{firmware_version}</firmware_version>
<serial_no>V5PF30000</serial_no>
<default_languages><code>JPN</code><code>ENU</code><code>DEU</code></default_languages>
</hardware_info>
</hardwares>
</firmware_demand>
"""


def call(hard_code, fv):
    body = TPL.format(time=time.strftime("%Y%m%d%H%M%S"), hard_code=hard_code,
                      firmware_version=fv)
    req = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "_verprobe_req.xml")
    with open(req, "w", encoding="utf-8") as f:
        f.write(body)
    url = "https://fw01.om-digitalsolutions.net/ww_inform/fcache.do"
    try:
        r = subprocess.run([CURL, "-s", "--max-time", "40", "--ssl-no-revoke",
                            "--user-agent", "Olympus",
                            "--header", "Content-Type: text/xml; Charset=UTF-8",
                            "--data-binary", "@" + req, url],
                           capture_output=True, timeout=60)
        return r.stdout.decode("utf-8", "replace")
    except Exception as e:
        return "ERROR: %s" % e


def field(xml, tag):
    m = re.search(r"<%s>(.*?)</%s>" % (tag, tag), xml, re.S)
    return m.group(1).strip() if m else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hard-code", default="OLYE108000000000")
    ap.add_argument("--versions", default="1800,1700,1600,1500,1400,1300,1200,1100,1000,1900")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    out = []
    for v in args.versions.split(","):
        # 固件版本在 XML 里是 8 位：0000 + 4 位版本（如 1.8 -> 00001800）
        fv = ("0000" + v.strip().zfill(4))[-8:]
        xml = call(args.hard_code, fv)
        fn = field(xml, "file_name")
        fs = field(xml, "file_size")
        up = field(xml, "up_date")
        md = field(xml, "model_name")
        err = field(xml, "error_message")
        print("firmware_version=%s -> file=%-38s size=%-10s up_date=%-12s model=%s%s"
              % (fv, fn or "(空)", fs or "-", up or "-", md or "-",
                 ("  ERR=" + err) if err else ""))
        out.append({"firmware_version": fv, "file_name": fn, "file_size": fs,
                    "up_date": up, "model_name": md, "error": err})
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print("[written] %s" % args.json)


if __name__ == "__main__":
    main()
