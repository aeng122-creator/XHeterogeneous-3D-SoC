# X-Heterogeneous 3D SoC V3.1 — Co-Designed Academic Research Proxy

![Architectural Blueprint](./Visual_References/Exploded Chiplet Architecture Infographic.png)





**Status: A RUNNABLE cycle-stepped synthetic memory/network prototype, NOT gem5, GPGPU-Sim, RTL, silicon characterization, or a real 8K rendering engine.**

---

## 🔬 Hardware Architecture Under Study

This project models a novel heterogeneous multi-tiered processor architecture optimized for multi-threaded workloads, extreme high-reuse cache hierarchies, local AI inference, and 8K multimedia rendering.

- **Two Tier Pyramid Layout:** Physical silicon tiers integrated with a custom stepped-water-cooling system (conceptually described, not thermally simulated).
- **🧬 Layer 1 (Compute Tier):** 8 High-Performance P-Cores featuring SMT (16 logical threads) paired with 32 Efficiency E-Cores (32 threads) for a total of **40 physical cores / 48 logical threads**.
- **💾 Hierarchy & L2 Cache:** Aggregate 3 MiB L1 cache. The L2 Cache spans 48 MiB, distributed as 2 MiB private L2 per P-core, and shared 4 MiB L2 caches per 4-core E-cluster (four E-cores per cluster).
- **🧠 Layer 2 (Acceleration Tier):** Integrated GPU, NPU, and an L3 Pool totaling 112 MiB. This pool features a **96 MiB fully shared non-inclusive CPU allocation pool** with selective stream bypass, combined with a dedicated **16 MiB GPU L3 Cache Slice** to eliminate memory contention. *(Non-inclusive is the intended policy; a full coherence directory implementation has not yet been provided).*
- **🌐 Network-on-Chip Interconnect:** E-clusters connect to an advanced on-chip network. Central routing columns feature a **Fat-Link** option widening links from 128-bit to 256-bit to alleviate center network traffic.
- **⚖️ QoS Arbiter:** A programmable, simplified WFQ-like output arbiter guarantees E-cores retain at least a 12.5% execution share under continuous saturation tests. *(This is an isolated arbitration fairness test, not an end-to-end minimum throughput guarantee).*
- **⚡ Power & Memory Interfaces:** Models a per-router leakage/sleep/wake power proxy (not post-layout power estimation). Quad DDR5 and separate GPU VRAM are modeled as simplified finite-bandwidth resources with fixed additional latency.

---

## 🚀 Quick Start

Python **3.10+** required. No external Python dependencies or libraries are needed.

```bash
cd XHeterogeneous_V3_1
python3 -m unittest discover -s tests -v
python3 sim/model.py --cycles 1800 --out results/my_test.json
python3 -m sim.report results/my_test.json results
python3 -m sim.export_topology
```

Windows platform execution:
```cmd
py -3 sim\model.py --cycles 1800 --out results\my_test.json
```

To benchmark under a heavier synthetic workload:
```bash
python3 sim/model.py --cycles 1100 --intensity 1.75 --out results/stress_custom.json
```
*Note: When `--intensity` increases, the model injects more parallel requests per cycle. The exact same trace is replayed consistently in every mode during that specific execution.*

---

## 📊 A/B/C/D Ablation Matrix & Verification Results

The proxy engine framework evaluates layout reduction, central bandwidth tuning, and active leakage control across four core configurations:

| Mode | CPU Endpoints | Physical Routers | Topology Configuration | Link Width Specification | Network Power Proxy (W) |
|---|---:|---:|---|---|---|
| **A** | 40 Independent Cores | 54 (6×9) | Unclustered Regular Mesh | All 128-bit links | 5.982 W |
| **B** | 8 P cores + 8 E clusters | 28 (4×7) | Clustered Regular Mesh | All 128-bit links | 4.471 W |
| **C** | 40 Cores | 54 (6×9) | Unclustered Fat Mesh | Center 256-bit / Edges 128-bit | 5.979 W |
| **D** | 8 P cores + 8 E clusters | 28 (4×7) | **Clustered Fat Mesh (Winning)** | Center 256-bit / Edges 128-bit | **4.412 W** |

**Caution:** The router count and mesh dimensions change together between A and B, so an A→B difference is not strictly attributable to router count alone. A real physical floorplan is required for placement comparisons. Fat-link widths are a *logical* cycle-stepped abstraction. GEM5 Garnet implementation of mixed-width links will require checking the selected version's bridge and link support.

---

## ⏱️ What One Cycle Means

The simulation framework operates strictly in **2.5 GHz nominal mesh clock cycles**. 

- **Serialization Packet Cost:** Computed as `ceil(bytes / (link_bits / 8))` cycles per link. Each completed link traversal adds exactly 1 cycle.
- **Memory Latency Target:** Main DRAM and GDDR/VRAM add a simplified fixed latency budget (DDR 85 cycles; GPU VRAM 65 cycles) plus a finite-bandwidth queue penalty.
- **Cache Lookup Overhead:** On L3 cache hits, the engine injects a 14-cycle tag/data/ECC lookup and decompression budget.
- **Power Savings assumption:** Router sleep gates after 50 continuous idle cycles and wakes in 4 cycles (illustrative tunable proxy metrics).

*Synthetic requests from all 40 cores plus GPU and NPU are emitted on static schedules. L1 and L2 are small scaled representations; L3 capacities and trace working sets are scaled down by a factor of 256. The model does not execute raw 8K shading or ray-path tracing.*

**NOTE:** This is a packet-level simulation advanced in discrete clock cycles, NOT a microarchitecture/RTL cycle-accurate simulator. Its queues are unbounded and packets take precomputed simple source routes. This avoids artificial deadlocks but cannot predict finite-buffer VC backpressure, credit timing, full cache coherence, memory ordering, or GPU instruction cycles.

---

## 📂 Project Repository Files

- `sim/model.py` — Core cycle-stepped CPU/GPU/NPU synthetic traffic engine, cache maps, mesh routing, allocation arbitration, and router sleep proxy.
- `sim/report.py` — Automatic CSV and Markdown metrics compiler.
- `sim/export_topology.py` — Graph exporter mapping A-D JSON network topologies (porting aid).
- `sim/translate_to_gem5.py` — Automatically compiles abstract proxy parameters into an executable **gem5 Garnet 2.0 Topology script** (`configs/topologies/Mesh_Clustered_Fat.py`).
- `hardware_spec.json` — Formal architectural specification agreements.
- `tests/test_model.py` — Complete unit verification environment containing seven passing tests.
- `results/` — Houses historical measurement outcomes (`standard.json`, `stress.json`, `light.json`) alongside corresponding markdown reports.
- `integration/GEM5_GPU_PORTING.md` — Notes remaining integration work and engineering constraints.

---

## ⚠️ Known Architectural Gaps Before a Credible 8K Benchmark

To turn this research proxy into a sign-off production-ready silicon design, the following engineering gaps must be bridged within a cycle-accurate environment (such as gem5 + Accel-Sim):

1. **Instruction Ingestion:** Integration of actual hardware CPU ISA execution and instruction traces, real OS P/E thread scheduling, and hardware simultaneous multithreading (SMT).
2. **GPU Execution Engine:** GPU SM/kernel execution pipelines and shared-data semantics; *no GPU silicon area, FLOPS or shader throughput proof is validated by this python proxy.*
3. **Cache Coherence Enforcement:** Cycle-level cache hierarchy with fully implemented MSHRs, directory coherence, cross-tier invalidations, writeback race resolution, and active ECC timing.
4. **Memory Subsystem Realism:** Realistic DRAM and GDDR/HBM cycle timings accounting for refresh cycles, precharge overhead, and structural bank conflicts.
5. **Physical Floorplan Design:** Physical routing placement, cross-tier 3D link TSV count/density, thermal RC/FEA/CFD boundaries, power distribution networks (PDN), and global clock trees.
6. **Energy Sign-off:** Silicon characterized SRAM cell models, compressor hardware pipelines, router switches, and wakeup circuit energy. *The 120W/140W targets are purely projective and are not validated by this model.*
7. **Unified Storage Boundary:** GPU L3 is 16MiB, not VRAM; GPU requires an explicit external memory model or a real unified memory architecture (UMA) framework.

---

## ⚖️ License & Verification Statement

Distributed under the **Apache License 2.0**. Intellectual ownership belongs entirely to the repository creator. Any commercial implementation, derivation, or architectural citation must explicitly reference this repository and author credits.

No fabricated benchmarks. All numerical outcomes in `results/` come from the Python prototype described here. The actual gem5+GPGPU-Sim combined simulator is **not installed or executed** in this environment, so no gem5/Accel-Sim benchmark is claimed.
