# X-Heterogeneous 3D SoC V3.1 — Co-Designed Academic Research Proxy

![Architectural Blueprint](Visual_References/a_detailed_infographic_style_technical_3d_render_o.png)

> **Status:** A runnable, cycle-stepped synthetic memory/network prototype exploring advanced 3D SoC interconnect topologies. *NOT gem5, GPGPU-Sim, RTL, or final silicon characterization.*

---

## 🔬 Hardware Architecture Under Study

This project models a novel heterogeneous multi-tiered processor architecture optimized for multi-threaded workloads, extreme high-reuse cache hierarchies, local AI inference, and 8K multimedia rendering.

### 🧬 Layer 1: Compute Tier (CPU Subsystem)
- **Cores & Threads:** 8 High-Performance P-Cores featuring SMT (16 logical threads) paired with 32 Efficiency E-Cores (32 threads) for a total of **40 physical cores / 48 logical threads**.
- **L1/L2 Cache Topology:** Aggregate 3 MiB L1 cache. The L2 Cache spans 48 MiB, distributed as 2 MiB private L2 per P-core, and shared 4 MiB L2 caches per 4-core E-cluster.
- **Interconnect:** A **2D Mesh Interconnect** functioning as a Clustered E-core topology (8 E-clusters + 8 P-cores). Central routing links are widened (**Fat-Links**) from 128-bit to 256-bit to alleviate center congestion.

### 🧠 Layer 2: Acceleration Tier (GPU, NPU, & Shared L3)
- **Heterogeneous Blocks:** Integrated high-throughput Graphics Processing Unit (GPU) and a dedicated Neural Processing Unit (NPU) for local LLM inference.
- **Shared L3 Pool (112 MiB Total):** Features a **96 MiB Non-inclusive Shared CPU Allocation Pool** with selective stream bypass, combined with a dedicated **16 MiB GPU L3 Cache Sclice** to eliminate memory contention during heavy graphic sweeps.
- **3D Vertical Integration:** Cross-tier data transport via low-latency 3D Vertical Links managed under active **QoS Scheduling** protocols (prioritizing time-critical P-Core and GPU requests).

---

## 📊 Ablation Matrix & Verification Results (Proxy Framework)

The underlying Python simulation proxy verifies network traffic, layout reduction, and active router leakage control across four core configurations:

| Mode | CPU Endpoints | Physical Routers | Topology Configuration | Central Link Width | Network Power Proxy (W) |
|---|---|---|---|---|---|
| **A** | 40 Independent Cores | 54 (6×9) | Unclustered Regular Mesh | All 128-bit links | 5.982 W |
| **B** | 8 P-cores + 8 E-clusters | 28 (4×7) | Clustered Regular Mesh | All 128-bit links | 4.471 W |
| **C** | 40 Independent Cores | 54 (6×9) | Unclustered Fat Mesh | Central 256-bit links | 5.979 W |
| **D** | 8 P-cores + 8 E-clusters | 28 (4×7) | **Clustered Fat Mesh (Winning)** | Central 256-bit links | **4.412 W** |

### 🔑 Critical Architectural Insights:
1. **The Power of Clustering:** Transitioning from an unclustered mesh (A) to a clustered configuration (B/D) reduces the physical router count from 54 to 28 (~48% reduction). This drops active router leakage power by **~25%**, ensuring the NoC layer stays below its strict power limits.
2. **Fat-Links Congestion Mitigation:** Widening central mesh links to 256-bit (Mode D) reduces overall latency bottlenecks, providing a **14.6% improvement in GPU access latency (P95)** over standard links, paving the way for sustained 8K processing.
3. **Starvation Control:** A programmable Quality-of-Service (QoS) output arbiter guarantees E-cores retain a minimum 12.5% execution share under heavy saturation, eliminating task starvation.

---

## 🛠️ Automated Porting and Verification

The repository contains an integrated bridge to specialized academic cycle-accurate simulators:
- `sim/model.py` — The core cycle-stepped synthetic memory network simulation engine.
- `sim/export_topology.py` — Exports multi-mode graph representations to `/topology`.
- `sim/translate_to_gem5.py` — Automatically compiles the abstract proxy network parameters into an executable **gem5 Garnet 2.0 Network Topology** script (`configs/topologies/Mesh_Clustered_Fat.py`).

## ⚖️ License & Intellectual Property
Distributed under the **Apache License 2.0**. Intellectual ownership belongs entirely to the repository creator. Any commercial integration, derivation, or citation in architectural papers must explicitly reference this repository and author credits.
