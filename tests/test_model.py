"""Run: python3 -m unittest discover -s tests -v"""
import sys,unittest
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sim.model import Mesh,Simulation,Packet,Cache,make_trace,WEIGHTS

class HardwareShapeTests(unittest.TestCase):
    def test_router_counts_and_endpoint_groups(self):
        base=Mesh(False,False); clustered=Mesh(True,False)
        self.assertEqual((base.n,clustered.n),(54,28))
        self.assertEqual(len(base.endpoint),52)
        self.assertEqual(len(clustered.endpoint),28)
        self.assertEqual(clustered.node('E0'),clustered.node('E3'))
        self.assertNotEqual(clustered.node('E3'),clustered.node('E4'))
    def test_fat_links_exactly_center(self):
        reg=Mesh(True,False);fat=Mesh(True,True)
        self.assertTrue(all(w==128 for w in reg.links.values()))
        widths=Counter(fat.links.values())
        self.assertGreater(widths[256],0)
        self.assertGreater(widths[128],0)
    def test_adaptive_routes_are_simple_and_valid(self):
        m=Mesh(True,True)
        for src in range(m.n):
            for dst in range(m.n):
                path=m.path(src,dst,64,True)
                self.assertEqual((path[0],path[-1]),(src,dst))
                self.assertEqual(len(set(path)),len(path))
                for a,b in zip(path,path[1:]):self.assertIn((a,b),m.links)
    def test_cache_capacity_compression(self):
        c=Cache(256,True)
        for i in range(100):c.put(i)
        self.assertLessEqual(c.used,256)
        self.assertLessEqual(len(c.entries)*32,256)
    def test_e_wfq_not_starved(self):
        m=Mesh(True,False);edge=next(iter(m.links));u,v=edge
        for _ in range(4000):
            for cl in ('P','E'):
                m.queues[edge][cl].append(Packet(0,'lookup',u,v,cl,16))
        taken=Counter(m.arbitrate(edge).cls for _ in range(2000))
        self.assertGreaterEqual(taken['E']/2000,0.125)

class EndToEndTests(unittest.TestCase):
    def test_deterministic_trace(self):
        self.assertEqual(make_trace(17,40),make_trace(17,40))
    def test_all_modes_complete(self):
        trace=make_trace(1,100)
        for clustered,fat in [(False,False),(True,False),(False,True),(True,True)]:
            s=Simulation(clustered,fat,trace=trace,max_cycles=30000)
            r=s.run()
            self.assertEqual(r['completed'],r['trace_requests'])
            self.assertEqual(r['unfinished'],0)
            self.assertGreater(r['noc_energy_proxy_J'],0)
            self.assertGreaterEqual(r['router_wake_events'],1)

if __name__=='__main__':unittest.main()
