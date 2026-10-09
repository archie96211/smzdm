"""Summarize bounded observations without confusing content size and disk use."""
import datetime,json,statistics,sys
rows=[json.loads(line) for line in open(sys.argv[1])]
ok=[r for r in rows if 'error' not in r]
cpu=[r['cpu_percent_one_core'] for r in ok if r.get('cpu_percent_one_core') is not None and r['cpu_percent_one_core'] >= 0]
def delta_seconds(a,b):
    return (datetime.datetime.fromisoformat(b)-datetime.datetime.fromisoformat(a)).total_seconds()
def io_total(r,kind):
    return sum(i['value'] for i in (r.get('blockio',{}).get('io_service_bytes_recursive') or []) if i['op']==kind)
result={
 'samples':len(rows),'sample_errors':[r for r in rows if 'error' in r],
 'start_utc':rows[0]['at'],'end_utc':rows[-1]['at'],'duration_seconds':delta_seconds(rows[0]['at'],rows[-1]['at']),
 'cpu_percent_one_core':{'mean':statistics.mean(cpu),'max_5s_sample':max(cpu),'median':statistics.median(cpu)},
 'memory_working_set_mib':{'min':min(r['working_set_bytes'] for r in ok)/1048576,'max':max(r['working_set_bytes'] for r in ok)/1048576,'last':ok[-1]['working_set_bytes']/1048576},
 'memory_including_cache_mib_max':max(r['memory_bytes'] for r in ok)/1048576,
 'block_read_delta_bytes':io_total(ok[-1],'read')-io_total(ok[0],'read'),
 'block_write_delta_bytes':io_total(ok[-1],'write')-io_total(ok[0],'write'),
 'pids_max':max(r.get('pids') or 0 for r in ok),
 'fetch_at_start':ok[0]['fetch'],'fetch_at_end':ok[-1]['fetch'],
 'note':'CPU 100% = one logical core. 5-second interval averages, not instantaneous peak. UI and observation polling included. Fetch metrics reset on app restart.'
}
print(json.dumps(result,ensure_ascii=False,indent=2))
