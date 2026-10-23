#!/usr/bin/env python3
"""OMSRV 官方服务器（fw01.om-digitalsolutions.net/ww_inform/fcache.do）客户端。

## 已验证的请求格式（2026-10-23 实测）

请求体 `firmware_demand` XML，**`hard_code` 必须是 16 字符**：
`OLYE` + **机型码前 3 位** + 9 个 `0`（例：`OLYE108000000000` 对应机型码 1080）。

`<firmware_version>` = 机身当前版本：
    * < 最新版  → 返回**最新版** + 带签名的直链（`?Expires=&Signature=&Key-Pair-Id=`）
    * ≥ 最新版  → 返回该版本号但 `file_name`/`file_size`/`url` **为空**（无需更新）
⇒ **该接口只提供每个机型的最新版**，无法取到历史版本。

服务器会覆盖响应里的 `<time>`（回填服务器当前时间）并回显 `<mac_address>`；
`<time>`/`<mac_address>` 用非样本值会导致响应退化（只回显版本号、无文件信息）。

## 用法
  omsrv_sweep.py --models 1080,1120,1130      # 查这些机型的最新版 + 签名直链
  omsrv_sweep.py --models 1080 --download DIR  # 并下载签名直链
  omsrv_sweep.py --models 1080 --sweep         # 参数扫描（确认无法指定旧版本）
"""
import subprocess, time, re, sys, itertools, json, os

TPL = """<?xml version="1.0"?>
<firmware_demand>
<revision>{revision}</revision>
<mac_address>00-00-00-00-80-D6</mac_address>
<time>{time}</time>
<language>ENU</language>
<application>{application}</application>
<type>{type}</type>
<version>{version}</version>
<os>WIN</os>
<country_code>0001</country_code>
<hardwares>
<firmup_mode>{firmup_mode}</firmup_mode>
<hardware_info>
<hard_code>{hard_code}</hard_code>
<firmware_version>{firmware_version}</firmware_version>
<serial_no>{serial_no}</serial_no>
<default_languages>
<code>JPN</code><code>ENU</code><code>DEU</code><code>FRA</code><code>ESP</code>
<code>CHS</code><code>CHT</code><code>KOR</code><code>RUS</code><code>NLD</code>
</default_languages>
</hardware_info>
</hardwares>
</firmware_demand>
"""

ENDPOINTS = ["fcache.do", "firmware2.do", "firmware.do", "fcache2.do"]
OUT = "/tmp/omsrv_sweep"

# 官方样本 req_E108.xml 中的其它字段（保持不变，否则响应会退化）
SAMPLE = {
    "revision": "0001", "mac_address": "00-00-00-00-80-D6",
    "time": "20261022215527", "language": "ENU", "application": "FWUT",
    "type": "0000", "version": "00005000", "os": "WIN", "country_code": "0001",
    "firmup_mode": "0", "serial_no": "V5PF30000",
}


def hard_code(model_id):
    """机型码 1080 -> OLYE108000000000（16 字符，机型码只取前 3 位）。"""
    return "OLYE" + str(model_id)[:3].zfill(3) + "0" * 9


def call(endpoint, base, **kw):
    p = dict(SAMPLE)
    p['hard_code'] = hard_code(base)
    p['firmware_version'] = '00001000'
    p.update(kw)
    body = TPL.format(**p)
    fn = os.path.join(OUT, 'req_tmp.xml')
    os.makedirs(OUT, exist_ok=True)
    open(fn, 'w', encoding='utf-8').write(body)
    url = 'https://fw01.om-digitalsolutions.net/ww_inform/' + endpoint
    r = subprocess.run(['curl', '-s', '-L', '--compressed', '-m', '45',
                        '--user-agent', 'Olympus',
                        '--header', 'Content-Type: text/xml; Charset=UTF-8',
                        '--data-binary', '@' + fn, '-w', '\n@@HTTP:%{http_code}', url],
                       capture_output=True, text=True, errors='replace')
    return r.stdout


def info_blocks(xml):
    """取出全部 <firmware_info>...</firmware_info> 块。"""
    return re.findall(r'<firmware_info>(.*?)</firmware_info>', xml, re.S)


def fields(xml):
    """只从第一个 firmware_info 块里取字段（避免抓到请求回显的 <version>）。"""
    blocks = info_blocks(xml)
    if not blocks:
        return {}
    b = blocks[0]
    out = {}
    for tag in ('model_name', 'model_id', 'version', 'file_name', 'file_size',
                'up_date', 'detail_url'):
        m = re.search(r'<%s>(.*?)</%s>' % (tag, tag), b, re.S)
        if m:
            out[tag] = m.group(1)[:120]
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="1080", help="逗号分隔的机型码")
    ap.add_argument("--download", default=None, help="下载目录")
    ap.add_argument("--sweep", action="store_true", help="参数扫描")
    args = ap.parse_args()

    if not args.sweep:
        for mid in args.models.split(','):
            mid = mid.strip()
            xml = call("fcache.do", mid)
            b = info_blocks(xml)
            if not b:
                print(f"{mid}: 无 firmware_info"); continue
            f = fields(xml)
            print(f"{mid} -> {f.get('model_name')} ver={f.get('version')} "
                  f"{f.get('file_name')} size={f.get('file_size')} date={f.get('up_date')}")
            u = re.search(r'<url>(.*?)</url>', b[0], re.S)
            if u and u.group(1).strip():
                url = u.group(1).replace('&amp;', '&').strip()
                if args.download:
                    out = os.path.join(args.download, f.get('file_name') or f"m{mid}.BIN")
                    os.makedirs(args.download, exist_ok=True)
                    print(f"   下载 {url[:90]}...")
                    subprocess.run(['curl', '-sL', '-C', '-', '--max-time', '300',
                                    '-o', out, url])
                    print(f"   → {out}  {os.path.getsize(out) if os.path.exists(out) else 0} B")
            time.sleep(1)
        return

    model = '1080'
    base = 'OLYE%s' % model
    trials = []
    for ep in ENDPOINTS:
        trials.append((ep, {}))
    for fv in ('00001000', '00001200', '00001400', '00001500', '00001600',
               '00001700', '00001800', '00002000'):
        trials.append(('fcache.do', dict(firmware_version=fv)))
    for fm in ('0', '1', '2', '3'):
        trials.append(('fcache.do', dict(firmup_mode=fm)))
    for t in ('0000', '0001', '0002'):
        trials.append(('fcache.do', dict(type=t)))
    for hc in (base + '0000000000', base + '017000000000',
               base + '018000000000', base + '170000000000'):
        trials.append(('fcache.do', dict(hard_code=hc)))
    for ver in ('00005000', '00001000', '00001700'):
        trials.append(('fcache.do', dict(version=ver)))

    seen = {}
    for ep, kw in trials:
        out = call(ep, base, **kw)
        http = re.search(r'@@HTTP:(\d+)', out)
        f = fields(out)
        blocks = info_blocks(out)
        if len(blocks) > 1:
            print(f"      >> 响应含 {len(blocks)} 个 firmware_info 块")
            for bb in blocks:
                bf = {}
                for t in ('version', 'file_name', 'file_size', 'up_date'):
                    mm = re.search(r'<%s>(.*?)</%s>' % (t, t), bb, re.S)
                    if mm: bf[t] = mm.group(1)[:60]
                print("      >>   ", bf)
        key = (f.get('file_name'), f.get('file_size'))
        desc = ' '.join(f'{k}={v}' for k, v in kw.items()) or '(默认)'
        print(f"  {ep:<14} {desc:<34} HTTP:{http.group(1) if http else '?'} "
              f"-> ver={f.get('version')} file={f.get('file_name')} "
              f"size={f.get('file_size')} date={f.get('up_date')}")
        if key[0]:
            seen.setdefault(key[0], []).append((ep, desc))
        sys.stdout.flush()

    print("\n=== 出现过的不同文件 ===")
    for fn, where in seen.items():
        print(f"  {fn}  ({len(where)} 次)")


if __name__ == '__main__':
    main()
