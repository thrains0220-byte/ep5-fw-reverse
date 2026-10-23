#!/usr/bin/env python3
"""扫描 OMSRV 官方服务器（fw01.om-digitalsolutions.net/ww_inform/*）的请求参数，
看能否让服务器返回**指定的历史版本**固件（而不是永远只给最新版）。

服务器会为它返回的文件动态签发带 ?Expires=&Signature=&Key-Pair-Id= 的直链，
因此若能指定版本，就能拿到「修复前基线」固件本体。

用法: omsrv_sweep.py [model_hard_code_prefix] [model_id]
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


def call(endpoint, base, **kw):
    p = dict(revision='0001', time=time.strftime('%Y%m%d%H%M%S'), application='FWUT',
             type='0000', version='00005000', firmup_mode='0',
             hard_code=base + '0000000000', firmware_version='00001000',
             serial_no='V5PF30000')
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
    model = sys.argv[1] if len(sys.argv) > 1 else '1080'
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
