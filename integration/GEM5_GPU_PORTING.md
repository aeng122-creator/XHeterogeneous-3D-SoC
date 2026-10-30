# Technical integration plan — gem5 Ruby/Garnet + GPGPU-Sim/Accel-Sim

## What exists now

This package provides a tested, standalone Python cycle-stepped packet/network model and the four directed graphs under `topology/`.

**It does not provide a verified gem5 configuration or binary and does not implement a GPU simulator connection.** The combined simulator has not been built in this environment.

## Step 1: Select and pin versions

Clone a chosen gem5 commit and an Accel-Sim/GPGPU-Sim commit into a separate reproducible build machine. Document compiler, OS, GPU trace requirements, ISA, Ruby protocol, and any patches. Do not assume that the historical Wisconsin gem5–GPGPU-Sim shared-memory integration runs with current upstream versions.

## Step 2: gem5 CPU + Ruby

- Implement 8 P-core and 32 E-core performance assumptions explicitly. gem5's stock cores are not equivalent to actual Intel/AMD hybrid CPU designs, so separate detailed/in-order core models are *proxies* until calibrated.
- Add 8 private 2-MiB P L2 banks and 8 shared 4-MiB E L2 controllers.
- Configure 3MiB aggregate L1 according to 8×128KiB + 32×64KiB; L1 I/D split and tags matter.
- L3 96MiB shared CPU + 16MiB GPU allocation must be implemented using the selected Ruby protocol and compression policy; do not assume allocating parameters provides fully non-inclusive cache coherence.

## Step 3: Garnet graph / link microarchitecture

- Import `topology/[A-D]_mesh_graph.json` as a graph specification and create Ruby `Router`, `ExtLink` and `IntLink` objects for the chosen gem5 version.
- Pass correct `src_outport` and `dst_inport` to enable custom routing.
- Standard Garnet uses a fixed flit width per network (`ni_flit_size`/`bandwidth_factor`); per-link 128/256-bit mixed widths may require version-specific NetworkBridge support, link flit-serialization modeling, or an explicit C++ extension. Confirm before benchmarking.
- Implement adaptive shortest/non-minimal routing with a deadlock-free escape virtual channel, credit flow control, and destination-ordering guarantees. The Python proxy uses precomputed simple source routes and unbounded queues, which are insufficient for signoff.
- For Clustered Mesh, four E-cores must share an L2 and NI/Router interface with local arbitration and an actual injection queue.
- Measure throughput, cycle-level latency (P50/P95/P99) and bisection utilization under identical workloads.

## Step 4: GPU integration

Two routes:
1. Adapt the **historical Wisconsin gem5 + GPGPU-Sim** bridge, in which two independent processes synchronize with shared memory and gem5 services GPGPU-Sim memory requests. This is research infrastructure and must be ported/validated against the pinned versions.
2. Write a new trace/tick bridge between Accel-Sim and a gem5 Ruby controller, with per-memory-request transaction IDs, timestamps, request/response queues, address translation, and a coherent/non-coherent DMA split.

Required interface per transaction:
```
(request_id, gpu_cycle, address, length_bytes, read_or_write,
 stream_id, memory_scope, synchronization_epoch)
```
On completion return `(request_id, response_cycle, status)` and synchronize clocks explicitly. A cycle-rate conversion or physical clock domains must be defined.

Ensure CPU and GPU can share buffers without stale lines: specify coherence domain, directory ownership, barriers, GPU writes and DMA completion.

## Step 5: Physical power/thermal

Use a calibrated router/cache energy methodology (e.g. CACTI plus characterized RTL netlist/PDK data) and model actual HBM/DDR package power separately. Then apply heat flux and tier-to-tier thermal properties to a 3D CFD/FEA model of the user's stepped copper liquid-cooled heat spreader. An analytic 120W budget is **not a measurement**.

## Step 6: Benchmark acceptance

- Same trace, seed, clock domain, CPU/GPU work and DRAM for all A/B/C/D variants.
- Reference kernel: 8K-sized tiled geometry/textures with documented memory footprint, write/read sharing, compression ratios and barrier semantics; validate it against a real 8K renderer separately.
- Record IPC/SM occupancy, kernel duration, delivered GB/s, NoC P95/P99, queue depths, hot links, power and per-tier peak temperatures.
- Verify no loss/duplication of requests and correct stale-data prevention; check E-class service floor under persistent contention.
- Publish variance over several seeds and both low- and high-pressure scenarios.

## Authoritative documentation

- gem5 Ruby/Garnet: https://www.gem5.org/documentation/general_docs/ruby/garnet-2/
- gem5 network topology: https://www.gem5.org/documentation/general_docs/ruby/interconnection-network/
- historical integrated gem5/GPGPU-Sim: https://cpu-gpu-sim.ece.wisc.edu/GEM5-GPGPUSim.html
- Accel-Sim framework: https://github.com/accel-sim/accel-sim-framework
