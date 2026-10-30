"""Render benchmark comparison into reproducible CSV and Markdown reports."""
import csv,json,sys
from pathlib import Path

def report(source, dest):
    src=Path(source); folder=Path(dest);folder.mkdir(parents=True,exist_ok=True)
    d=json.loads(src.read_text(encoding='utf-8'))
    data=d['results']; columns=['mode','routers','completed','unfinished','CPU_P_p95_cycles','CPU_E_p95_cycles','GPU_p95_cycles',
      'GPU_p99_cycles','NPU_p95_cycles','L3_miss_ratio_of_probes','noc_power_proxy_W','noc_energy_per_request_nJ','center_cut_bytes',
      'router_wake_events','drain_cycles']
    rows=[]
    for name,r in data.items():
        rows.append(dict(mode=name,routers=r['routers'],completed=r['completed'],unfinished=r['unfinished'],
          CPU_P_p95_cycles=r['CPU_P']['p95_cycles'],CPU_E_p95_cycles=r['CPU_E']['p95_cycles'],
          GPU_p95_cycles=r['GPU']['p95_cycles'],GPU_p99_cycles=r['GPU']['p99_cycles'],
          NPU_p95_cycles=r['NPU']['p95_cycles'],L3_miss_ratio_of_probes=r['L3_miss_ratio_of_probes'],
          noc_power_proxy_W=r['noc_power_proxy_W'],noc_energy_per_request_nJ=r['noc_energy_per_request_nJ'],
          center_cut_bytes=r['center_cut_bytes'],router_wake_events=r['router_wake_events'],drain_cycles=r['drain_cycles']))
    with (folder/(src.stem+'_summary.csv')).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(rows)
    p=folder/(src.stem+'_report.md')
    ar=['# X-Heterogeneous V3.1 — تقرير '+src.stem,
      '', '**تنبيه:** نموذج أحداث/حزم بخطوة زمنية (network/cache proxy)، وليس محاكاة gem5+GPGPU-Sim أو نتائج أداء سيليكون.',
      '',f"الطلبات الاصطناعية: **{next(iter(data.values()))['trace_requests']}**؛ تردد الشبكة المفترض **2.5GHz**.",
      '', '| التجربة | الموجهات | P-Core P95 (cycle) | E-Core P95 (cycle) | GPU P95 (cycle) | طاقة الشبكة (W، نموذج افتراضي) |',
      '|---|---:|---:|---:|---:|---:|']
    for r in rows:
        ar.append(f"| {r['mode']} | {r['routers']} | {r['CPU_P_p95_cycles']} | {r['CPU_E_p95_cycles']} | {r['GPU_p95_cycles']} | {r['noc_power_proxy_W']} |")
    ar+=['','## كيفية تفسير النتائج',
      '- **P95** هو المئين الخامس والتسعين لزمن الطلب المكتمل داخل النموذج؛ ليس زمن تنفيذ التعليمة أو زمن الرندر.',
      '- تعديل التجميع يغير عدد الموجهات والطوبولوجيا معًا. المقارنة ليست إثباتًا مستقلًا لأثر الموجه وحده.',
      '- نموذج القدرة الافتراضي يحسب المرور والتسريب والتفعيل. لا يشمل CPU/GPU وSRAM وDRAM ومنظومة التبريد كاملة.',
      '- تدفق البيانات مصطنع وبارد نسبيًا، ومعدل إخفاق L3 يعتمد بشدة على الاختيار الاصطناعي للأحمال.',
      '- الذاكرة الخارجية والأحمال قد تهيمن على تأخير CPU؛ لذلك لا يُنتظر أن تتحسن P95 بالتناسب مع عرض الروابط المركزية.',
      '- مسارات التوجيه ثابتة لكل حزمة بعد حساب طريق ازدحام-واعٍ؛ والصفوف غير محدودة، فلا توجد محاكاة ائتمانات VC أو Deadlock.',
      '', '## الخطوة التالية',
      'نقل رسم الطوبولوجيا إلى gem5 Ruby/Garnet وتفعيل بروتوكول تماسك فعلي، ثم توصيل Accel-Sim/GPGPU-Sim عبر ناقل طلبات ذاكرة متزامن.',
      '']
    p.write_text('\n'.join(ar),encoding='utf-8')
    print('Wrote',p)

if __name__=='__main__':
    if len(sys.argv)<3:raise SystemExit('Usage: python3 -m sim.report results/standard.json results/')
    report(sys.argv[1],sys.argv[2])
