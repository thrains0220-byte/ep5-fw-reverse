import subprocess, os, time, re, sys, itertools

CURL = r'C:\Windows\System32\curl.exe'
PROXY = 'http://127.0.0.1:7890'
OM = r'D:\0_Project\01Test\fw-work\xdel_notes\omsrv'
os.makedirs(OM, exist_ok=True)

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

def call(endpoint, **kw):
    p = dict(revision='0001', time=time.strftime('%Y%m%d%H%M%S'), application='FWUT',
             type='0000', version='00005000', firmup_mode='0', hard_code='OLYE108000000000',
             firmware_version='00001000', serial_no='V5PF30000')
    p.update(kw)
    body = TPL.format(**p)
    req = os.path.join(OM, 'req_tmp.xml')
    open(req, 'w', encoding='utf-8').write(body)
    url = 'https://fw01.om-digitalsolutions.net/ww_inform/' + endpoint
    r = subprocess.run([CURL, '--proxy', PROXY, '-s', '-L', '--compressed', '-m', '45',
                        '--user-agent', 'Olympus', '--header', 'Content-Type: text/xml; Charset=UTF-8',
                        '--data-binary', '@' + req, '-w', '\n@@HTTP:%{http_code}', url],
                       capture_output=True, text=True, errors='replace')
    return r.stdout

def fields(xml):
    out = {}
    for tag in ('model_name', 'model_id', 'version', 'file_name', 'file_size', 'up_date', 'detail_url', 'url'):
        m = re.search(r'<%s>(.*?)</%s>' % (tag, tag), xml, re.S)
        if m:
            out[tag] = m.group(1).replace('&amp;', '&')[:150]
    return out

print('=' * 110)
print('A) endpoint / parameter sweep for E-P5 (1080)')
print('=' * 110)
trials = []
for ep in ('fcache.do', 'firmware2.do'):
    for fm in ('0', '1', '2'):
        trials.append((ep, dict(firmup_mode=fm)))
for t in ('0000', '0001', '0002'):
    trials.append(('fcache.do', dict(type=t)))
for fv in ('00000000', '00001700', '00001800', '00001000'):
    trials.append(('fcache.do', dict(firmware_version=fv)))
for hc in ('OLYE108000000000', 'OLYE108017000000000', 'OLYE108000170000000'):
    trials.append(('fcache.do', dict(hard_code=hc)))

for ep, kw in trials:
    out = call(ep, **kw)
    http = re.search(r'@@HTTP:(\d+)', out)
    f = fields(out)
    desc = ' '.join('%s=%s' % (k, v) for k, v in kw.items())
    print('  %-14s %-42s HTTP:%s -> %s' % (ep, desc, http.group(1) if http else '?',
          ' '.join('%s=%s' % (k, f.get(k)) for k in ('version', 'file_name', 'file_size')) if f else out[-180:].replace('\n', ' ')))
    sys.stdout.flush()
