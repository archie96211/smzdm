"""Bounded Docker sampling; no extra packages, no process in the app container."""
import argparse, datetime, http.client, json, pathlib, socket, time, urllib.request

class DockerConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect('/var/run/docker.sock')

def docker(path):
    c = DockerConnection('localhost', timeout=10)
    c.request('GET', '/v1.47' + path)
    r = c.getresponse(); data = r.read(); c.close()
    if r.status != 200: raise RuntimeError(f'Docker {r.status}: {data[:200]}')
    return json.loads(data)

def main():
    p=argparse.ArgumentParser(); p.add_argument('--seconds',type=int,default=330); p.add_argument('--out',default='observation.jsonl')
    args=p.parse_args(); end=time.monotonic()+args.seconds; previous=None
    with open(args.out,'w',buffering=1) as f:
        while True:
            started=time.monotonic()
            try:
                s=docker('/containers/smzdm-monitor-1/stats?stream=false&one-shot=true')
                mem=s['memory_stats']; cpu=s['cpu_stats']; use=cpu['cpu_usage']['total_usage']; now=time.monotonic()
                row={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'memory_bytes':mem.get('usage',0),
                     'working_set_bytes':mem.get('usage',0)-mem.get('stats',{}).get('inactive_file',0),
                     'cpu_total_ns':use,'pids':s.get('pids_stats',{}).get('current'),
                     'networks':s.get('networks'), 'blockio':s.get('blkio_stats'),
                     'cpu_percent_one_core':((use-previous[1])/(now-previous[0])/1e7) if previous else None}
                previous=(now,use)
                with urllib.request.urlopen('http://192.168.31.35:18085/api/metrics',timeout=5) as r:
                    row['fetch']=json.load(r)['data']
            except Exception as e:
                row={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'error':str(e)}
            f.write(json.dumps(row,ensure_ascii=False)+'\n')
            if time.monotonic() >= end: break
            time.sleep(max(0,min(5-(time.monotonic()-started),end-time.monotonic())))
    print(json.dumps({'output':args.out,'seconds':args.seconds}))
if __name__=='__main__': main()
