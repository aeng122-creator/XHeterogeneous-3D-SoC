"""X-Heterogeneous V3.1: cycle-stepped memory-network research proxy.

NOT gem5, GPGPU-Sim, RTL, or an ISA-level CPU/GPU model.
Unbounded queues, complete simple source routes, and synthetic traffic are intentional.
"""
from __future__ import annotations
import argparse
from collections import Counter, OrderedDict, defaultdict, deque
from dataclasses import dataclass, field
from heapq import heappush, heappop
from math import ceil
from pathlib import Path
import json
import random
import statistics
from typing import Optional

CLOCK_HZ = 2_500_000_000
LINE = 64
SCALE = 256
CLASSES = ("P", "E", "GPU", "NPU")
WEIGHTS = {"P": 0.45, "E": 0.125, "GPU": 0.35, "NPU": 0.075}

class Cache:
    def __init__(self, capacity_bytes: int, compress=False):
        self.limit = max(1, capacity_bytes)
        self.entries = OrderedDict()
        self.used = 0
        self.compress = compress
        self.evictions = 0

    @staticmethod
    def size(key: int, compress: bool) -> int:
        # deterministic compressibility used only in the cache proxy, not actual BDI.
        return 32 if compress and ((key * 2654435761) & 7) < 4 else 64

    def get(self, key: int) -> bool:
        if key not in self.entries:
            return False
        self.entries.move_to_end(key)
        return True

    def put(self, key: int):
        if key in self.entries:
            self.entries.move_to_end(key)
            return
        size = self.size(key, self.compress)
        if size > self.limit:
            return
        while self.used + size > self.limit and self.entries:
            _, old_size = self.entries.popitem(last=False)
            self.used -= old_size
            self.evictions += 1
        self.entries[key] = size
        self.used += size

@dataclass
class Request:
    ident: int
    cls: str
    owner: str
    line: int
    streaming: bool
    injection: int
    bank: int
    src: int
    stage: str = "new"

@dataclass
class Packet:
    req_id: int
    phase: str
    src: int
    dst: int
    cls: str
    nbytes: int
    route: list[int] = field(default_factory=list)
    hop: int = 0
    last_hop_cycle: int = 0

class Mesh:
    def __init__(self, clustered=False, fat=False):
        self.clustered, self.fat = clustered, fat
        self.rows, self.cols = (4, 7) if clustered else (6, 9)
        self.n = self.rows * self.cols
        self.links = {}
        self.adj = defaultdict(list)
        self._build_links()
        self.endpoint = self._place_endpoints()
        self.queues = {link: {cl: deque() for cl in CLASSES} for link in self.links}
        self.wfq_finish = {link: {cl: 0.0 for cl in CLASSES} for link in self.links}
        self.link_busy_until = {edge: 0 for edge in self.links}
        self.link_packets = Counter()
        self.link_bytes = Counter()
        self.router_activity = Counter()
        self.router_last_use = [-10**9] * self.n
        self.router_wake_until = [0] * self.n
        self.wakeup_count = 0
        self.wakeup_energy = 0.0
        self.byte_hops = 0
        self.packet_hops = 0

    def _build_links(self):
        for y in range(self.rows):
            for x in range(self.cols):
                u = y * self.cols + x
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < self.cols and 0 <= yy < self.rows:
                        v = yy * self.cols + xx
                        # nonuniform central channels, with the same frequency
                        wide = self.fat and (dy == 0 and min(x, xx) in ((self.cols - 1)//2-1, (self.cols-1)//2))
                        self.links[(u, v)] = 256 if wide else 128
                        self.adj[u].append(v)

    def _place_endpoints(self):
        # Functional floorplan proxy, not a certified place-and-route result.
        coords = [(i, i % self.cols, i // self.cols) for i in range(self.n)]
        cx, cy = (self.cols - 1)/2, (self.rows - 1)/2
        inner = sorted(coords, key=lambda t: (abs(t[1]-cx)+abs(t[2]-cy), t[0]))
        used=set(); mapping={}
        def take(name, order):
            for i,_,_ in order:
                if i not in used:
                    used.add(i); mapping[name]=i; return
            raise RuntimeError('Not enough router nodes')
        take('GPU',inner)
        take('NPU',inner)
        for k in range(8):take(f'L3_{k}',inner)
        left=sorted(coords,key=lambda t:(t[1], abs(t[2]-cy),t[0]))
        right=sorted(coords,key=lambda t:(-t[1],abs(t[2]-cy),t[0]))
        take('DDR',left);take('VRAM',right)
        perimeter=sorted(coords,key=lambda t:(min(t[1],self.cols-1-t[1],t[2],self.rows-1-t[2]), abs(t[1]-cx), t[0]))
        for k in range(8):take(f'P{k}',perimeter)
        for k in range(8 if self.clustered else 32):
            take(f'E{k}',perimeter)
        return mapping

    def node(self, name):
        if name.startswith('E') and self.clustered:
            return self.endpoint['E'+str(int(name[1:])//4)]
        return self.endpoint[name]

    def cost(self, u,v, nbytes=64, adaptive=False):
        tx = ceil(nbytes / (self.links[(u,v)]//8))
        load = sum(len(q) for q in self.queues[(u,v)].values())
        # congestion-aware but uses non-negative costs, preventing route loops
        return 1+tx + (min(30,load)*tx*1.4 if adaptive else 0)

    def path(self, src,dst, nbytes, adaptive=False):
        if src==dst:return [src]
        pq=[(0.0,src)]; best={src:0.0}; prev={}
        while pq:
            dist,u=heappop(pq)
            if dist!=best[u]:continue
            if u==dst:break
            for v in sorted(self.adj[u]):
                c=self.cost(u,v,nbytes,adaptive)
                d=dist+c
                if d<best.get(v,float('inf')):
                    best[v]=d;prev[v]=u;heappush(pq,(d,v))
        if dst not in prev:raise RuntimeError('Disconnected path')
        rev=[dst];u=dst
        while u!=src:
            u=prev[u];rev.append(u)
        return list(reversed(rev))

    def queue_packet(self, packet:Packet, now:int, adaptive=False):
        packet.route=self.path(packet.src,packet.dst,packet.nbytes,adaptive)
        packet.hop=0
        packet.last_hop_cycle=now
        if len(packet.route)>1:
            u,v=packet.route[:2]
            self.queues[(u,v)][packet.cls].append(packet)

    def arbitrate(self,edge):
        candidates=[cl for cl,q in self.queues[edge].items() if q]
        if not candidates:return None
        # WFQ-like normalized service fairness, all packet weights equal.
        cl=min(candidates,key=lambda k:(self.wfq_finish[edge][k],CLASSES.index(k)))
        pkt=self.queues[edge][cl].popleft()
        m=min(self.wfq_finish[edge].values())
        # prevent idle classes retaining unrealistic past credit
        self.wfq_finish[edge][cl]=max(self.wfq_finish[edge][cl],m)+1/WEIGHTS[cl]
        return pkt

    def max_backlog(self):
        return max((sum(len(q) for q in cls_q.values()) for cls_q in self.queues.values()),default=0)


def make_trace(seed:int=117, cycles:int=1800, intensity:float=1.0):
    rng=random.Random(seed)
    # 40 CPU request sources, one simulated GPU, one NPU.
    starts=[]
    for j in range(8):starts.append(('P',f'P{j}',max(1,round(18/intensity)), j*2 % max(1,round(18/intensity))))
    for j in range(32):starts.append(('E',f'E{j}',max(1,round(40/intensity)), j*7 % max(1,round(40/intensity))))
    starts.extend([('GPU','GPU',max(1,round(3/intensity)),0),('NPU','NPU',max(1,round(22/intensity)),5)])
    trace=[]; rid=0
    for t in range(cycles):
        for cls,owner,period,phase in starts:
            if t%period!=phase:continue
            r=rng.random()
            if cls in ('P','E'):
                if r<0.47:
                    # local high-reuse lines, shared within E cluster
                    group=int(owner[1:])//4 if cls=='E' else int(owner[1:])
                    base=(group*350) % 2600
                    line=base+rng.randrange(175)
                    stream=False
                elif r<0.78:
                    line=5000+rng.randrange(8500)
                    stream=False
                else:
                    line=40000+rid*5
                    stream=True
            elif cls=='GPU':
                if r<0.37:
                    line=700000+rng.randrange(2500);stream=False
                elif r<0.56:
                    line=702500+rng.randrange(1700);stream=False
                else:
                    line=1_100_000+rid*7;stream=True
            else:
                if r<0.65:
                    line=1_500_000+rng.randrange(500);stream=False
                else:
                    line=1_600_000+rid*3;stream=True
            trace.append((t,cls,owner,line,stream))
            rid+=1
    return trace

class Simulation:
    def __init__(self,clustered=False,fat=False,trace=None,seed=117,max_cycles=110_000):
        self.mesh=Mesh(clustered,fat)
        self.trace=trace if trace is not None else make_trace(seed)
        self.max_cycles=max_cycles
        self.events=[];self.serial=0;self.nextreq=0
        self.requests={}
        self.l1={f'P{i}':Cache(128*1024//SCALE) for i in range(8)}
        self.l1.update({f'E{i}':Cache(64*1024//SCALE) for i in range(32)})
        self.l2={f'P{i}':Cache(2*1024*1024//SCALE) for i in range(8)}
        self.l2.update({f'E{i}':Cache(4*1024*1024//SCALE) for i in range(8)})
        self.l3_cpu=[Cache(12*1024*1024//SCALE,compress=True) for _ in range(8)]
        self.l3_gpu=[Cache(2*1024*1024//SCALE,compress=True) for _ in range(8)]
        self.stats=Counter()
        self.completed_lat=defaultdict(list)
        self.network_lat=defaultdict(list)
        self.completed_cycle=0
        self.mem_next={'DDR':0,'VRAM':0}
        self.mem_traffic=Counter()
        self.mem_overutil_cycles=Counter()
        self.router_sleep_cycle=0
        self.router_active_cycle=0
        self.simulated_until=0
        self.invalid_timeouts=0

    def add_event(self,at,kind,payload):
        self.serial+=1
        heappush(self.events,(at,self.serial,kind,payload))

    def bank_for(self,line):
        return (line ^ (line>>7) ^ (line>>13)) & 7

    def l2_for(self,owner):
        return owner if owner.startswith('P') else 'E'+str(int(owner[1:])//4)

    def emit(self,req,stage,now):
        m=self.mesh
        bank=m.node('L3_'+str(req.bank))
        if stage=='lookup':src,dst,nb=req.src,bank,16
        elif stage=='memory_req':src,dst,nb=bank,m.node('VRAM' if req.cls=='GPU' else 'DDR'),16
        elif stage=='memory_return':src,dst,nb=m.node('VRAM' if req.cls=='GPU' else 'DDR'),bank,LINE
        elif stage=='response':src,dst,nb=bank,req.src,LINE
        else:raise ValueError(stage)
        pkt=Packet(req.ident,stage,src,dst,req.cls,nb)
        if src==dst:self.add_event(now+1,'arrival',pkt)
        else:m.queue_packet(pkt,now,adaptive=True)

    def finish(self,req,now,level):
        self.stats['complete_'+req.cls]+=1
        self.stats['complete_'+level]+=1
        self.completed_lat[req.cls].append(now-req.injection)
        self.completed_cycle=max(now,self.completed_cycle)
        if req.cls in ('P','E'):
            self.l1[req.owner].put(req.line)
            if level not in ('L1','L2'):
                self.l2[self.l2_for(req.owner)].put(req.line)

    def start(self,t,cl,owner,line,stream):
        rid=self.nextreq;self.nextreq+=1
        b=self.bank_for(line)
        req=Request(rid,cl,owner,line,stream,t,b,self.mesh.node(owner))
        self.requests[rid]=req
        self.stats['issued_'+cl]+=1
        if cl in ('P','E'):
            if self.l1[owner].get(line):
                self.stats['L1_hit']+=1
                self.add_event(t+4,'local_complete',(rid,'L1'))
                return
            l2=self.l2[self.l2_for(owner)]
            if l2.get(line):
                self.stats['L2_hit']+=1
                self.add_event(t+13,'local_complete',(rid,'L2'))
                return
        self.stats['L3_probe_'+cl]+=1
        self.emit(req,'lookup',t)

    def arrive(self,pkt,now):
        req=self.requests[pkt.req_id]
        if pkt.phase=='lookup':
            arr=self.l3_gpu if req.cls=='GPU' else self.l3_cpu
            cache=arr[req.bank]
            hit=cache.get(req.line)
            if hit:
                self.stats['L3_hit_'+req.cls]+=1
                # 13 cycles tag/data/ECC + 1 cycle decompression proxy
                self.emit(req,'response',now+14)
            else:
                self.stats['L3_miss_'+req.cls]+=1
                self.emit(req,'memory_req',now+14)
        elif pkt.phase=='memory_req':
            name='VRAM' if req.cls=='GPU' else 'DDR'
            # DDR quad: 179.2 GB/s peak, simplified sustained 140; VRAM: 350 GB/s.
            rate=140 if name=='DDR' else 350
            bytes_per_cycle=rate*1e9/CLOCK_HZ
            service=ceil(LINE/bytes_per_cycle)
            start=max(now,self.mem_next[name])
            self.mem_next[name]=start+service
            fixed=85 if name=='DDR' else 65
            self.mem_traffic[name]+=LINE
            self.add_event(start+service+fixed,'memory_ready',req.ident)
        elif pkt.phase=='memory_return':
            if not req.streaming:
                arr=self.l3_gpu if req.cls=='GPU' else self.l3_cpu
                arr[req.bank].put(req.line)
            else:self.stats['bypassed_stream']+=1
            self.emit(req,'response',now+1)
        elif pkt.phase=='response':
            self.finish(req,now,'L3_or_DRAM')
        else:raise RuntimeError(pkt.phase)

    def process_link(self,edge,now):
        m=self.mesh
        if m.link_busy_until[edge]>now:return
        if not any(m.queues[edge][cl] for cl in CLASSES):return
        u,v=edge
        # Sleep only after 50 cycles of inactivity. Waking costs four cycles.
        if now-m.router_last_use[u]>50 and now>=m.router_wake_until[u]:
            m.router_wake_until[u]=now+4
            m.router_last_use[u]=now
            m.wakeup_count+=1
            m.wakeup_energy+=2e-9  # illustrative 2 nJ per wake event
        if now<m.router_wake_until[u]:return
        pkt=m.arbitrate(edge)
        if pkt is None:return
        if pkt.route[pkt.hop]!=u or pkt.route[pkt.hop+1]!=v:
            raise AssertionError('Invalid route state')
        serialization=ceil(pkt.nbytes/(m.links[edge]//8))
        m.link_busy_until[edge]=now+serialization
        m.link_packets[edge]+=1
        m.link_bytes[edge]+=pkt.nbytes
        m.byte_hops+=pkt.nbytes
        m.packet_hops+=1
        m.router_activity[u]+=1
        m.router_last_use[u]=now
        pkt.hop+=1
        pkt.last_hop_cycle=now
        self.add_event(now+serialization+1,'packet_hop',pkt)

    def run(self):
        t_idx=0;N=len(self.trace)
        last_injection=max(t for t,*_ in self.trace) if self.trace else 0
        m=self.mesh
        active_links=list(m.links)
        now=0
        for now in range(self.max_cycles):
            while t_idx<N and self.trace[t_idx][0]==now:
                self.start(*self.trace[t_idx]);t_idx+=1
            while self.events and self.events[0][0]<=now:
                _,_,kind,payload=heappop(self.events)
                if kind=='local_complete':
                    rid,level=payload;self.finish(self.requests[rid],now,level)
                elif kind=='memory_ready':
                    req=self.requests[payload];self.emit(req,'memory_return',now)
                elif kind=='arrival':self.arrive(payload,now)
                elif kind=='packet_hop':
                    pkt=payload
                    if pkt.hop==len(pkt.route)-1:self.arrive(pkt,now)
                    else:
                        a,b=pkt.route[pkt.hop:pkt.hop+2]
                        m.queues[(a,b)][pkt.cls].append(pkt)
                else:raise RuntimeError(kind)
            for edge in active_links:self.process_link(edge,now)
            # leakage proxy for active vs gated routers; no wake latency in this model.
            asleep=sum(now-lu>50 for lu in m.router_last_use)
            self.router_sleep_cycle+=asleep
            self.router_active_cycle+=m.n-asleep
            if t_idx>=N and not self.events and not any(any(q for q in clsq.values()) for clsq in m.queues.values()):
                break
        self.simulated_until=now+1
        delivered=sum(self.stats[f'complete_{cl}'] for cl in CLASSES)
        self.invalid_timeouts=N-delivered
        return self.report()

    def report(self):
        m=self.mesh
        N=len(self.trace)
        cycles=max(1,self.simulated_until)
        def quant(xs,p):
            if not xs:return None
            return float(sorted(xs)[min(len(xs)-1,int((len(xs)-1)*p))])
        def group_stats(cl):
            xs=self.completed_lat[cl]
            return dict(issued=self.stats['issued_'+cl],completed=self.stats['complete_'+cl],mean_cycles=round(statistics.mean(xs),2) if xs else None,p95_cycles=quant(xs,0.95),p99_cycles=quant(xs,0.99))
        active_duration=max(1,max((t for t,*_ in self.trace),default=0)+1)
        sim_sec=cycles/CLOCK_HZ
        traffic_energy=m.byte_hops*4e-12 # illustrative, joules / byte-hop
        # awake leakage 25 mW/router, gated 4 mW/router
        leakage_j=(self.router_active_cycle*0.025+self.router_sleep_cycle*0.004)/CLOCK_HZ
        model_noc_power=(traffic_energy+leakage_j+m.wakeup_energy)/sim_sec
        directed=m.links
        cut=(m.cols-1)//2
        mid_edges=[(u,v) for (u,v) in directed if min(u%m.cols,v%m.cols)==cut and abs(u-v)==1]
        busy_mid=sum(m.link_bytes[e] for e in mid_edges)
        hot_edges=sorted(((f'{u}->{v}',n) for (u,v),n in m.link_packets.items()),key=lambda x:-x[1])[:6]
        res={
            'mode':('clustered' if m.clustered else 'unclustered')+(' + fat' if m.fat else ' + regular'),
            'clustered':m.clustered,'fat_center_links':m.fat,
            'routers':m.n,'rows':m.rows,'cols':m.cols,
            'cycles':cycles,'trace_requests':N,'completed':N-self.invalid_timeouts,
            'unfinished':self.invalid_timeouts,'drain_cycles':max(0,cycles-active_duration),
            'CPU_P':group_stats('P'),'CPU_E':group_stats('E'),
            'GPU':group_stats('GPU'),'NPU':group_stats('NPU'),
            'L1_hits':self.stats['L1_hit'],'L2_hits':self.stats['L2_hit'],
            'L3_hits':sum(self.stats['L3_hit_'+k] for k in CLASSES),
            'L3_misses':sum(self.stats['L3_miss_'+k] for k in CLASSES),
            'L3_miss_ratio_of_probes':round(sum(self.stats['L3_miss_'+k] for k in CLASSES)/max(1,sum(self.stats['L3_probe_'+k] for k in CLASSES)),4),
            'bypassed_stream_lines':self.stats['bypassed_stream'],
            'mem_DDR_MB':round(self.mem_traffic['DDR']/1e6,4),'mem_VRAM_MB':round(self.mem_traffic['VRAM']/1e6,4),
            'network_byte_hops':m.byte_hops,'network_packet_hops':m.packet_hops,
            'center_cut_bytes':busy_mid,
            'max_link_packets':hot_edges,
            'noc_energy_proxy_J':traffic_energy+leakage_j+m.wakeup_energy,
            'noc_energy_per_request_nJ':round((traffic_energy+leakage_j+m.wakeup_energy)*1e9/max(1,N),3),
            'router_wake_events':m.wakeup_count,
            'noc_power_proxy_W':round(model_noc_power,3),
            'noc_router_leakage_proxy_W':round(leakage_j/sim_sec,3),
            'noc_energy_model_notes':'4 pJ per byte-hop; 25/4 mW active/gated router; 2 nJ / wake; 4-cycle wake, 50-cycle idle threshold. Synthetic power proxy, NOT signoff.',
            'simulator_limitations':'Unbounded router queues; atomic packets serialized per link; no backpressure/VC/deadlock/coherence/ISA/GPU SM modeling; source-route adaptive paths; no real workload tracing; DDR response latency fixed.'
        }
        return res


def run_modes(cycles=1800,seed=117,intensity=1.0,max_cycles=110000):
    trace=make_trace(seed,cycles,intensity)
    return {tag:Simulation(clustered=c,fat=f,trace=trace,max_cycles=max_cycles).run() for tag,c,f in
        [('A_unclustered_regular',False,False),('B_clustered_regular',True,False),('C_unclustered_fat',False,True),('D_clustered_fat',True,True)]}

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--cycles',type=int,default=1800)
    a.add_argument('--intensity',type=float,default=1.)
    a.add_argument('--seed',type=int,default=117)
    a.add_argument('--max-cycles',type=int,default=110_000)
    a.add_argument('--out',type=Path,default=Path('results/results.json'))
    args=a.parse_args()
    data={'metadata':{'clock_hz':CLOCK_HZ,'seed':args.seed,'injection_cycles':args.cycles,
           'intensity':args.intensity,'trace_type':'synthetic_8k_like_memory_traffic',
           'model':'cycle-stepped network/cache proxy; not gem5/GPGPU-Sim'},
           'results':run_modes(args.cycles,args.seed,args.intensity,args.max_cycles)}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(data,indent=2),encoding='utf-8')
    for name,stat in data['results'].items():
        print(f"{name:26} routers={stat['routers']:2} done={stat['completed']:5}/{stat['trace_requests']} CPU-P P95={stat['CPU_P']['p95_cycles']} GPU P95={stat['GPU']['p95_cycles']} NoC proxy={stat['noc_power_proxy_W']} W")
    print(f"Saved {args.out}")
if __name__=='__main__':main()
