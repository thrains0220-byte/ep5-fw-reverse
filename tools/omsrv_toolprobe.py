#!/usr/bin/env python3
"""系统性地改变 OM Digital Solutions `fcache.do` 请求里的**非机型字段**，
看服务器是否会返回**更新器包**（OlympusUpdater.exe）而不是机身固件 `.BIN`。

背景（第 23 轮）:
    第二十轮的 `omsrv_multifile.py` 只变了 `firmup_mode` 与端点，
    其余字段固定为：
        application=FWUT  type=0000  version=00005000  os=WIN  country_code=0001
    而 2025-12 起 OM 改了下载方式：直链 `.BIN` 需先向
    `https://fw01.om-digitalsolutions.net/ww_inform/fcache.do` 提交 XML，
    换取带签名/过期时间的 URL。
    `OlympusUpdater.exe`（约 15.7 MB）本身也要下载，**很可能由同一服务按
    `application` / `type` / `version` / `os` 区分下发**。

本脚本:
    1. 以 E-P5（hard_code OLYE108000000000）为基准；
    2. 逐一变化 application / type / version / os / country_code / language /
       firmware_version / firmup_mode；
    3. 每个组合记录返回的 **全部** `<firmware_info>` 条目（file_name / file_size /
       up_date / url / model_name）；
    4. 只要出现**多于 1 个**条目，或 file_name 不是 `*.BIN`，就标红输出。

用法:
    python tools/omsrv_toolprobe.py [--out out.json] [--only E-P5]
"""
import argparse
import json
import os
import re
import subprocess
import time

CURL = r"C:\Windows\System32\curl.exe"
ENDPOINT = "fcache.do"

TPL = """<?xml version="1.0"?>
<firmware_demand>
<revision>{revision}</revision>
<mac_address>00-00-00-00-80-D6</mac_address>
<time>{time}</time>
<language>{language}</language>
<application>{application}</application>
<type>{type}</type>
<version>{version}</version>
<os>{os}</os>
<country_code>{country_code}</country_code>
<hardwares>
<firmup_mode>{firmup_mode}</firmup_mode>
<hardware_info>
<hard_code>{hard_code}</hard_code>
<firmware_version>{firmware_version}</firmware_version>
<serial_no>{serial_no}</serial_no>
<default_languages>
<code>JPN</code><code>ENU</code><code>DEU</code>
</default_languages>
</hardware_info>
</hardwares>
</firmware_demand>
"""

BASE = dict(revision="0001", time=time.strftime("%Y%m%d%H%M%S"),
            language="ENU", application="FWUT", type="0000",
            version="00005000", os="WIN", country_code="0001",
            firmup_mode="0", hard_code="OLYE108000000000",
            firmware_version="00001000", serial_no="V5PF30000")


def parse(xml):
    """把响应里的每一个 <firmware_info> 块解析成 dict。"""
    out = []
    for blk in re.findall(r"<firmware_info>(.*?)</firmware_info>", xml, re.S):
        rec = {}
        for k in ("file_name", "file_size", "up_date", "url", "model_name",
                  "file_type", "comment", "version"):
            m = re.search(r"<%s>(.*?)</%s>" % (k, k), blk, re.S)
            if m:
                rec[k] = m.group(1).strip()
        out.append(rec)
    return out


def call(**kw):
    p = dict(BASE)
    p["time"] = time.strftime("%Y%m%d%H%M%S")
    p.update(kw)
    body = TPL.format(**p)
    req = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_toolprobe_req.xml")
    with open(req, "w", encoding="utf-8") as f:
        f.write(body)
    url = "https://fw01.om-digitalsolutions.net/ww_inform/" + ENDPOINT
    try:
        r = subprocess.run([CURL, "-s", "--max-time", "40", "--ssl-no-revoke",
                            "--user-agent", "Olympus",
                            "--header", "Content-Type: text/xml; Charset=UTF-8",
                            "--data-binary", "@" + req, url],
                           capture_output=True, timeout=60)
        return r.stdout.decode("utf-8", "replace")
    except Exception as e:
        return "ERROR: %s" % e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    variants = []
    # 1) 单独变化每个字段
    for app in ("FWUT", "FWUD", "DCU", "DCUD", "OLYMPUS", "APP", ""):
        variants.append({"application": app})
    for ty in ("0000", "0001", "0002", "0003", "0100"):
        variants.append({"type": ty})
    for ver in ("00005000", "00010000", "00020000", "00003000", "00000000",
                "00001000", "00005100"):
        variants.append({"version": ver})
    for os_ in ("WIN", "MAC", "OSX", "LIN"):
        variants.append({"os": os_})
    for cc in ("0001", "0002", "0000", "0091"):
        variants.append({"country_code": cc})
    for lang in ("ENU", "JPN", "CHS"):
        variants.append({"language": lang})
    for fm in ("0", "1", "2", "3", "4"):
        variants.append({"firmup_mode": fm})
    for fv in ("00001000", "00001800", "00002000", "00000000"):
        variants.append({"firmware_version": fv})
    # 2) 组合：把 type/version 改成「工具」语义
    variants += [
        {"application": "DCU", "type": "0001"},
        {"application": "FWUT", "type": "0001"},
        {"application": "FWUT", "version": "00010000"},
        {"os": "MAC", "application": "FWUT"},
        {"type": "0001", "version": "00010000"},
    ]

    results = []
    seen = set()
    for v in variants:
        key = tuple(sorted(v.items()))
        if key in seen:
            continue
        seen.add(key)
        xml = call(**v)
        infos = parse(xml)
        tag = "".join("%s=%s " % (k, x) for k, x in sorted(v.items()))
        mark = "  <<<" if (len(infos) != 1 or
                          (infos and not infos[0].get("file_name", "").upper().endswith(".BIN"))) else ""
        print("[%-34s] -> %d 条%s" % (tag.strip(), len(infos), mark))
        for r in infos:
            print("      file_name=%s size=%s up_date=%s model=%s" %
                  (r.get("file_name"), r.get("file_size"),
                   r.get("up_date"), r.get("model_name")))
            u = r.get("url", "")
            if u:
                print("      url=%s" % u[:160])
        if not infos:
            print("      (无 firmware_info) resp=%s" % xml[:160].replace("\n", " "))
        results.append({"variant": v, "count": len(infos), "infos": infos,
                        "raw_head": xml[:400]})

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
        print("\n[written] %s" % args.out)


if __name__ == "__main__":
    main()
