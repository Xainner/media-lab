# Independent GPU execution

Saturno runs two separate ComfyUI processes on two RTX 3090 GPUs. Each process
has its own input, output and user volumes; only read-only model assets are shared.
The runtime scheduler serializes all work within each GPU and respects account
concurrency quotas. Independent image, edit, music, H3 and Director jobs can run
on both GPUs simultaneously when workers and account limits allow it.

H3 formerly used one global Python lock. A second video claimed the other worker
and then waited for the first video, consuming its worker slot without submitting
anything to ComfyUI. That also left subsequent image/edit jobs queued. H3 now uses
one lock per worker, shared by direct video and Director scene rendering.

ComfyUI 0.37 with comfy-aimdo and PyTorch 2.12 uses DynamicVRAM model allocations
outside the ordinary torch allocator. Subtracting `torch_vram_total` from device
usage cannot distinguish these model allocations from foreign processes, even when
sampling grows torch's allocator beyond 128 MiB. The guard skips that unreliable
estimate for reported Aimdo/DynamicVRAM configurations. External Image Lab and
Comfy queue guards still apply, as do per-GPU serialization, account quotas and
ComfyUI's native NVML memory-pressure management. An unknown allocation source
is not proof of a foreign process. Legacy configurations retain their existing
best-effort allocator estimate.

Regression tests exercise concurrent H3 Base/Turbo, Director/video independence,
scoped cancellation, and DynamicVRAM accounting with growing torch reserves.
Mocks replace physical generation, while real scheduler/locking logic remains.
Deployments must drain active jobs before restarting the runtime: current startup
marks unfinished jobs interrupted and does not transparently reattach to GPU work.
