# Autonomy and Vision

## Modes

### `native-ai`

Uses BeamNG's built-in AI with target speed, lane behavior, aggression, waypoint, chase, flee, or
traffic configuration. This is the best first smoke test because it does not depend on external
model weights. Moving modes are accepted only through leased `autonomy_start`; the standalone AI
configuration tool can disable or stop AI but cannot bypass the engine deadman.

### `vision-lane`

Creates a vehicle-mounted streaming shared-memory camera and runs the local perception/controller
supervisor. Steering is derived from lane geometry; speed is reduced by low confidence, curvature,
and hazards.

### `hybrid`

Uses camera perception together with BeamNG vehicle state and the simulator control path. The
current alpha controller disables native AI before applying direct controls so two controllers do
not fight. Route-planner fusion is on the roadmap.

Both camera-driven modes use BeamNGpy's production `Camera` path and therefore require BeamNG.tech
on the tested 0.38 generation. Retail BeamNG.drive 0.38.6 rejects that sensor with an explicit Tech
license error. The repository's opt-in retail GPU smoke uses a test-only Lua RenderView fixture to
exercise rendering plus local inference; it is removed afterward and is not a supported retail
fallback for `vision-lane` or `hybrid` control.

## Backends

### Classical OpenCV

- no model weights
- deterministic and easy to test
- HLS/edge/Hough lane geometry
- sensitive to lighting, road texture, occlusion, and non-marked roads

Use it to validate camera placement, rate, controls, and watchdog behavior—not as a claim of robust
general autonomy.

### Hugging Face SegFormer

- lazy import and model load
- local-only by default
- CUDA/FP16 configuration for the RTX 5090
- Cityscapes road and hazard class mapping supplied by the service

The default identifier is `nvidia/segformer-b0-finetuned-cityscapes-512-1024`. Review the model
card and license before enabling downloads or redistribution. Domain shift from Cityscapes to a
particular BeamNG map is expected; fine-tune or replace the model for serious evaluation.

### ONNX Runtime

- accepts a semantic-segmentation ONNX model
- provider order: TensorRT, CUDA, CPU
- FP16 TensorRT option
- configurable GPU memory and TensorRT workspace ceilings
- engine/cache files intentionally excluded from git

`beamng-mcp doctor --json` reports the installed PyTorch CUDA status and ONNX Runtime provider
list. Provider preference is not proof that TensorRT initialized for a given model; confirm the
active provider in `autonomy_status` after backend warmup.

The backend accepts common NCHW/NHWC input and output layouts, normalizes RGB data, and converts
class logits/labels into drivable and hazard masks.

## Why MCP is outside the loop

MCP calls can include model inference, client scheduling, user approvals, and network latency.
Those are incompatible with a deadline-sensitive steering loop. `autonomy_start` is a coarse
command that launches a local supervisor; `autonomy_status` observes it, and `autonomy_stop` or
`emergency_stop` terminates it.

No frame is sent to an LLM. A future VLM advisor can run asynchronously at a low rate for semantic
explanations or high-level goals, but it must not own braking or steering deadlines.

## Engine-side lease and deadman

Autonomy has two independent software safety layers:

1. The Python supervisor watchdog detects stale frames, failed inference, and failed control
   delivery.
2. A real-time lease inside GELua expires and brakes the selected vehicle if healthy Python-side
   progress no longer renews it.

`autonomy_start` first disables native AI, applies full brake, and warms the selected perception
backend on a synthetic frame. Only after that safe preparation succeeds does it arm the
authenticated bridge for the exact vehicle. Failure to arm aborts the start and attempts a brake
through both BeamNGpy and GELua. The initial arm uses a bounded startup grace for camera attachment
and first control delivery; later renewals use the normal lease window:

```toml
[lua]
safety_lease_seconds = 1.0
safety_startup_grace_seconds = 5.0
```

Both values must be between 0.25 and 5 seconds. Native AI receives an immediate post-start renewal
only after a bounded BeamNGpy vehicle-state heartbeat, and every later renewal repeats that health
check. Vision-lane and hybrid runs renew only after a recently delivered BeamNG control command;
autonomy control is rejected when the local view of the engine lease is no longer authorized. A
renewal error stops the local supervisor, requests a GELua brake, and leaves engine expiry as the
fail-closed fallback.

On expiry, GELua uses game-engine real time to disable AI, set throttle to zero, and apply full
service plus parking brake. `autonomy_stop` first cancels renewal and revokes direct-control
authorization, then stops/brakes locally and through GELua, and only then disarms the lease.
`emergency_stop` attempts its available BeamNGpy, supervisor, and GELua brake paths concurrently
before attempting disarm.

`autonomy_status` exposes the lease state as:

- `engine_deadman_armed`
- `engine_deadman_control_authorized`
- `engine_deadman_lease_seconds`
- `engine_deadman_expires_in_ms`
- `engine_deadman_last_renewal_age_ms`
- `engine_deadman_last_error`

For vision runs it also exposes lane `confidence`, `hazard_score`, watchdog latch/trip state, and
the active `perception_device` / `perception_providers` reported by the warmed backend. Use those
fields to verify CUDA or TensorRT rather than inferring acceleration from configured preference.

The engine lease protects automated runs while BeamNG's Lua update loop is alive. It does not make
the controller suitable for a real vehicle, cannot brake a frozen game process, and does not
replace an operator-controlled stop path.

The standalone `vehicle_control` tool is deliberately outside the automated-run lease. It sends a
complete one-shot input and BeamNG may retain that input until a later control command. It is
blocked while autonomy is starting or active, but callers remain responsible for sending a neutral
or braking follow-up.

## Watchdog and control constraints

The supervisor brakes when:

- frame acquisition times out
- a frame is older than the maximum age
- frame sequence is non-monotonic
- perception latency makes the frame stale
- consecutive inference failures cross the threshold
- command delivery fails
- the supervisor is stopped or shut down

The lane controller limits steering magnitude and rate. The speed governor clamps throttle and
service brake, slows for curvature, lowers speed as lane confidence falls, and escalates for high
hazard scores. Emergency commands use full braking and parking brake.

## RTX 5090 deployment profile

The detected RTX 5090 is a Blackwell device with 32 GB VRAM. BeamNG and inference contend for the
same compute, memory bandwidth, VRAM, power, and thermals. A sensible first profile is:

| Setting | Initial value |
| --- | --- |
| Game renderer | DX11 first; compare Vulkan separately |
| Game FPS cap | 60–90 |
| Camera | 640×360 RGB, 15–20 Hz |
| Precision | FP16 |
| Inference memory cap | 4 GB |
| TensorRT workspace | 2 GB |
| Frame maximum age | 300–350 ms for bring-up; tighten after measurement |
| Target speed | 5–12 m/s until the map/model is characterized |

NVIDIA documents special simultaneous-compute-and-graphics constraints for TensorRT-RTX. On
Blackwell, select tactics that remain valid while graphics is active and benchmark with the game
running—not from an isolated inference test.

Relevant primary references:

- [BeamNGpy camera and sensor API](https://documentation.beamng.com/api/beamngpy/v1.35/beamngpy.html)
- [TensorRT-RTX simultaneous compute and graphics](https://docs.nvidia.com/deeplearning/tensorrt-rtx/latest/inference-library/compute-graphics.html)
- [TensorRT-RTX RTX 5090 precision support](https://docs.nvidia.com/deeplearning/tensorrt-rtx/latest/getting-started/support-matrix-1/1.0.html)
- [ONNX Runtime TensorRT execution provider](https://onnxruntime.ai/docs/execution-providers/TensorRT-ExecutionProvider.html)
- [CUDA Blackwell compatibility](https://docs.nvidia.com/cuda/blackwell-compatibility-guide/)

## Evaluation protocol

Measure complete episodes, not screenshots:

- frame acquisition latency
- inference latency p50/p95/p99
- observation-to-actuation latency
- achieved control rate and dropped frames
- lane departures per kilometer
- collisions and damage
- emergency-stop count/reason
- route completion
- minimum time-to-collision
- BeamNG FPS and GPU/VRAM utilization

Use deterministic pause/step runs for regression and real-time runs for concurrency. Keep map,
weather, vehicle config, seed, model hash, precision, provider, and game version in every result.
