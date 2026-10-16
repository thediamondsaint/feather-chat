#!/usr/bin/env python3
"""Offline measurements; no tokens, network requests, or production data."""
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

project=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(project/'src'))
from backend import Store

def process_tree(pid):
    pids=[pid]
    try:
        for child in Path(f'/proc/{pid}/task/{pid}/children').read_text().split(): pids.extend(process_tree(int(child)))
    except OSError: pass
    return pids

def sample(pid):
    rss=ticks=0
    for child in process_tree(pid):
        try:
            status=Path(f'/proc/{child}/status').read_text().splitlines()
            rss+=int(next(line for line in status if line.startswith('VmRSS:')).split()[1])
            stat=Path(f'/proc/{child}/stat').read_text().split(') ',1)[1].split()
            ticks+=int(stat[11])+int(stat[12])
        except (OSError,StopIteration): pass
    return rss,ticks

with tempfile.TemporaryDirectory(prefix='feather-bench-') as tmp:
    temp=Path(tmp)
    store=Store(temp/'data')
    with store.db:
        store.db.executemany('INSERT INTO chats VALUES(?,?,NULL,?)',[(str(i),f'Conversation {i}',i) for i in range(5000)])
        store.db.executemany("INSERT INTO messages(chat_id,role,content) VALUES(?,'user',?)",[(str(i//4),f'Laptop research message {i}') for i in range(20000)])
    def median_ms(fn):
        samples=[]
        for _ in range(30):
            start=time.perf_counter(); fn(); samples.append((time.perf_counter()-start)*1000)
        return round(statistics.median(samples),2)
    report={'history_fixture':{'conversations':5000,'messages':20000},'history_list_median_ms':median_ms(store.listing),'history_search_median_ms':median_ms(lambda:store.listing('research'))}
    store.db.close()
    shutil.copytree(project/'src',temp/'src',ignore=shutil.ignore_patterns('__pycache__'))
    path=temp/'src/shell.qml'
    path.write_text(path.read_text().replace('case "ready": ready = true; break;','case "ready": ready = true; console.log("BENCH_READY"); break;'))
    runtime=temp/'runtime'; runtime.mkdir(mode=0o700)
    env={**os.environ,'XDG_RUNTIME_DIR':str(runtime),'FEATHER_DATA_DIR':str(temp/'data'),'QT_QPA_PLATFORM':'offscreen','QT_QPA_PLATFORMTHEME':'generic','QT_QUICK_CONTROLS_STYLE':'Basic','QT_QUICK_BACKEND':'software'}
    env.pop('DISPLAY',None); env.pop('WAYLAND_DISPLAY',None)
    start=time.perf_counter()
    proc=subprocess.Popen(['qs','-p',str(temp/'src'),'--no-color'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    try:
        for line in proc.stdout:
            if 'BENCH_READY' in line:
                report['startup_ready_ms']=round((time.perf_counter()-start)*1000,1)
                break
        else: raise RuntimeError('UI did not become ready')
        time.sleep(.4)
        first=sample(proc.pid)
        idle_start=time.perf_counter()
        time.sleep(2)
        second=sample(proc.pid)
        elapsed=time.perf_counter()-idle_start
        report['combined_idle_rss_mib']=round(second[0]/1024,1)
        report['idle_cpu_percent_one_core']=round((second[1]-first[1])/os.sysconf('SC_CLK_TCK')/elapsed*100,2)
        report['conditions']='Offscreen Qt software renderer; warm filesystem cache; frontend plus Python service; 5000 conversations/20000 messages. Live Wayland and authenticated model latency were not measured.'
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait()
    print(json.dumps(report,indent=2))
    (project/'previews/benchmark.json').write_text(json.dumps(report,indent=2)+'\n')
