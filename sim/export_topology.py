"""Export graph descriptions for manual gem5 topology porting (not gem5 configs)."""
from pathlib import Path
import json
from .model import Mesh

def export(root):
    dest=Path(root); dest.mkdir(parents=True,exist_ok=True)
    modes=[('A',False,False),('B',True,False),('C',False,True),('D',True,True)]
    for name,cl,ft in modes:
        net=Mesh(cl,ft)
        data={
            'schema':'xh_v3_1_mesh_graph_v1',
            'NOT_A_GEM5_CONFIG':True,
            'configuration':name,'clustered':cl,'fat_center_links':ft,
            'clock_hz':2_500_000_000,
            'rows':net.rows,'cols':net.cols,'router_count':net.n,
            'routers':[{'id':i,'x':i%net.cols,'y':i//net.cols} for i in range(net.n)],
            'endpoints':net.endpoint,
            'directed_links':[{'src':a,'dst':b,'width_bits':bits,'latency_cycles':1}
                              for (a,b),bits in sorted(net.links.items())]
        }
        (dest/f'{name}_mesh_graph.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
if __name__=='__main__':
    export(Path(__file__).resolve().parents[1]/'topology')
    print('Exported graph descriptions for A, B, C and D')
