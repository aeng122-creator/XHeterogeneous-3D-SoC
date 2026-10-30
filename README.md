# X-Heterogeneous 3D SoC V3.1 — Reproducible Research Proxy

**Status: a RUNNABLE cycle-stepped synthetic memory/network prototype, NOT gem5, GPGPU-Sim, RTL, silicon characterization or a real 8K rendering engine.**

تم بناء نموذج بايثون قابل للتشغيل لاختبار الاتجاهات المعمارية الأساسية. الهدف منه اختبار تصميم الشبكة مبكرًا، وليس إصدار أرقام أداء فعلية لمعالج لم يُصنع.

## Hardware under study

- Two pyramid-shaped physical silicon tiers with a custom stepped-water-cooling system **described, not thermally simulated**.
- Tier 1: 8 P-cores (16 logical threads) + 32 E-cores (32 threads); **40 physical cores / 48 logical threads**.
- Aggregate L1 3 MiB; L2 48 MiB with one 2 MiB private P-cache each, and eight 4 MiB E-cluster caches (four E-cores per cluster).
- Tier 2: GPU, NPU, and L3 = 112 MiB, with a 96 MiB fully shared non-inclusive CPU allocation + 16 MiB GPU allocation. ("Non-inclusive" is the intended policy; a full coherence implementation has **not** yet been provided.)
- The L3 proxy has 8 physical slices, selective stream bypass, simple weighted-entry compression, and LRU replacement. Data ECC is specified but **not functionally simulated**.
- Clusters connect to a network-on-chip; the fat-link option widens links around the central columns from 128 to 256 bits.
- A simplified WFQ-like output arbiter allocates E traffic at least 12.5% in a continuously saturated two-class arbitration test; this is **not an end-to-end minimum throughput guarantee**.
- Per-router leakage/sleep/wake **power proxy**, not post-layout power estimation.
- Quad DDR5 and separate GPU VRAM are modeled as simplified finite-bandwidth resources with fixed additional latency; no hardware GPU SMs, threads, shader kernels, memory controller timing banks, or functional CPU ISA are modeled.

## Quick start

Python **3.10+**, no external Python dependencies required.

```bash
cd XHeterogeneous_V3_1
python3 -m unittest discover -s tests -v
python3 sim/model.py --cycles 1800 --out results/my_test.json
python3 -m sim.report results/my_test.json results
python3 -m sim.export_topology
```

Windows: `py -3 sim\model.py --cycles 1800 --out results\my_test.json`.

Try a heavier load:

```bash
python3 sim/model.py --cycles 1100 --intensity 1.75 --out results/stress_custom.json
```

When `--intensity` increases, the model injects more requests per cycle. The *same* trace is replayed in every mode in that execution.

## A/B/C/D ablation matrix

| Mode | CPU endpoints | Routers | Topology | Link width |
|---|---:|---:|---|---|
| A | 40 cores | 54 (6×9) | Unclustered mesh | all 128-bit |
| B | 8 P cores + 8 E clusters | 28 (4×7) | Clustered mesh | all 128-bit |
| C | 40 cores | 54 (6×9) | Unclustered mesh | center 256-bit, edges 128-bit |
| D | 8 P cores + 8 E clusters | 28 (4×7) | Clustered mesh | center 256-bit, edges 128-bit |

**Caution:** The router count and mesh dimensions change together between A and B, so an A→B difference is not strictly attributable to router count alone. A real floorplan is required for placement comparisons. Fat-link widths are a *logical* cycle-stepped abstraction. GEM5 Garnet implementation of mixed-width links will require checking the selected version's bridge and link support.

## What one cycle means

The model operates in **2.5 GHz nominal mesh clock cycles**. Packet serialization is `ceil(bytes/(link_bits/8))` cycles per link. Each completed link traversal adds 1 cycle. Memory responses add a simplified fixed latency (DDR 85 cycles; GPU VRAM 65 cycles) plus a finite-bandwidth queue. On L3 hits the model adds a 14-cycle lookup/decompression budget. Router sleep after 50 idle cycles and wake in 4 cycles are tunable *illustrative* assumptions.

Synthetic requests from all 40 cores plus GPU and NPU are emitted on schedules. L1 and L2 are small scaled representations; L3 capacities and trace working sets are scaled down by 256. **The model does not execute 8K shading or path tracing.**

**NOTE:** This is a packet-level simulation advanced in discrete clock cycles, NOT a microarchitecture/RTL cycle-accurate simulator. Its queues are unbounded and packets take precomputed simple source routes. This avoids artificial deadlocks but cannot predict finite-buffer VC backpressure, credit timing, full cache coherence, memory ordering, or GPU instruction cycles.

## Files

- `sim/model.py` — runnable cycle-stepped CPU/GPU/NPU synthetic traffic, caches, mesh links, arbitration, congestion-dependent source routing, finite bandwidth memory, router sleep proxy.
- `sim/report.py` — CSV + Markdown metrics extractor.
- `sim/export_topology.py` — exported A-D JSON network graphs (porting aid; NOT runnable gem5 config).
- `hardware_spec.json` — agreed architecture specification.
- `tests/test_model.py` — seven passing tests.
- `results/standard.json`, `results/stress.json`, `results/light.json` — completed measurements of this program only.
- `results/*_summary.csv`, `results/*_report.md` — comparisons.
- `integration/GEM5_GPU_PORTING.md` — actual integration work remaining and constraints.

## Known architectural gaps before a credible 8K benchmark

1. Actual CPU ISA and instruction traces; real P/E scheduling and simultaneous multithreading.
2. GPU SM/kernel execution and shared-data semantics; **no GPU silicon area, FLOPS or shader throughput proof**.
3. Cycle-level cache hierarchy with proper MSHRs, directory coherence, invalidations, writeback, 64-byte line races and ECC timing.
4. Realistic DRAM timing and GDDR/HBM timings under refresh and bank conflicts.
5. Physical route placement, cross-tier 3D link count/density, thermal RC/FEA/CFD, power distribution and clock trees.
6. Silicon characterized SRAM, compressor, router, link and wakeup energy. **120W/140W targets are not validated by this model.**
7. GPU L3 is 16MiB, not VRAM; GPU requires external memory or a real unified memory architecture.

## Verification statement

No fabricated benchmarks. All numerical outcomes in `results/` come from the Python prototype described here. The actual gem5+GPGPU-Sim combined simulator is **not installed or executed** in this environment, so no gem5/Accel-Sim benchmark is claimed.
