# Asynchronous SM64 command-list experiment

Results: [REPORT.md](REPORT.md), [results.json](results.json).

This follows the [live scheduling simulation](../sm64_coupled_20260922/README.md).
It adds a private streaming command-DMA extension to the frozen GPU and two
application command buffers. GPU list fetches traverse the actual Pocket
SDRAM controller and compete with texture, framebuffer, scanout and mixer
traffic. The CPU continues to use qsim's instruction/cache timing model.

This directory and `build/sm64-async-20260922` contain the experiment. Existing
production sources and prior measurement artifacts are preserved. The overlays
are simulator patches, not installable applications; the RTL extension has
not been fitted or qualified for 100 MHz on a physical FPGA.

## Reproduce

The retained fixtures and tools from the preceding simulation are required;
this is not a clean-checkout bootstrap. From the repository root:

```sh
python3 tools/experiments/sm64_async_20260922/build.py
python3 tools/experiments/sm64_async_20260922/build_overlay.py async
python3 tools/experiments/sm64_async_20260922/build_overlay.py chunk
python3 tools/experiments/sm64_async_20260922/build_overlay.py async_audio
python3 tools/experiments/sm64_async_20260922/build_overlay.py chunk_audio
python3 tools/experiments/sm64_async_20260922/build_overlay.py early
python3 tools/experiments/sm64_async_20260922/build_overlay.py early_audio
python3 tools/experiments/sm64_async_20260922/test_dma.py
python3 tools/experiments/sm64_async_20260922/matrix.py
python3 tools/experiments/sm64_async_20260922/analyze.py
```

Build overlays serially because they share a generated include directory.
The run matrix executes up to four separate simulators concurrently.
`control` and `audio` reuse the same-compiler CPU-ring overlays from the
scheduling experiment. `async` uses two 128 KiB lists; `chunk` uses two
32 KiB lists and publishes at capacity. The `_audio` suffix includes the
previously tested audio deadline changes.
`early` uses the full-size lists but publishes clears immediately when the
preceding frame has already retired. It otherwise retains full-list overlap.
The full matrix has 38 cases / 1,072 live rendered frames, including longer
audio-enabled Bowser and castle windows.

For a single live run:

```sh
python3 tools/experiments/sm64_async_20260922/run.py async --scene attract --start 1140 --count 24
python3 tools/experiments/sm64_async_20260922/run.py async_audio --scene intro --start 1040 --count 24 --sound
```

## Implementation

`transport.py` derives the private hardware changes:

- Enable the existing command-DMA hardware, absent from the retained baseline.
- Opt into streaming with bit 31 of `DMA_LEN`; use its low 16 bits as the
  word count. Existing descriptors retain their low-13-bit length and atomic
  publication behavior.
- Reserve ring space for each burst of at most 16 words, publish the received
  words, then release the read bus while waiting for further credits. A full
  command ring must not prevent texture or destination reads from progressing.
- Hold command decoding until the complete payload is present. Individual
  commands must fit inside the ring; a list can wrap around it repeatedly.

The implementation adds one DMA state, descriptor mode bits and wider counters
and reuses the existing 4,096-word ring. It adds no new command-data RAM, but
restoring DMA and changing control logic have unmeasured FPGA resource/timing
costs. A production version needs capability discovery and coherent SDK/RTL
integration; private overlays unconditionally require this experimental core.

`list.inc` implements the application side. Ordinary advisory kicks keep
building the current list. Flip, fence and capacity boundaries publish it.
The previous frame's fence is awaited at publication; framebuffer destinations
are relocated to the newly acquired buffer. The next list can be built while
the GPU consumes the preceding one. At most one previous GPU frame and one CPU
frame context are outstanding, retaining the existing triple-buffer protocol.

Both source buffers are owned until DMA has fetched them. Submission waits
for the preceding descriptor to finish reading before rotating storage. Cached
commands use the existing Pocket cache flush plus same-master readback drain.
Previous-frame texture reuse waits for that frame's flip fence; current-frame
reuse retains the renderer's explicit finish barrier. Capacity flushes occur
at complete command boundaries and preserve stream order and sticky state.

## Checks and artifacts

`test_dma.cpp` links the same Verilated GPU/controller model as the live runs.
It checks every decoded word across legacy transfers, a maximum 65,535-word
stream, a blocked display flip, ring wrap, split payloads, queued descriptors
and a return to legacy DMA. The blocked flip must stop DMA at ring capacity
and resume when the display accepts the swap.

The live simulator snapshots each published source and compares every word
returned by actual DMA against it. Lost words, source reuse before consumption
or incorrect reads abort. Existing checks for framebuffer ownership, SDRAM
protocol errors and CPU-ring overflow remain active. Candidate images are
compared at matching game ticks because the game skips different frames when
performance changes. CPU-ring controls are checked against the previous
experiment's images and presentation rate.

Outputs follow the preceding simulator's layout. Additional files include
`transport.json` per run (DMA submissions, verified words, ring-credit and
payload waits), `gpu_core.patch`, and `test-dma.log`. Probe counters include
functional warm-up; `transport.json` covers only the live window.

Presentation and audio statistics discard the first three presented frames.
Renderer-entry-to-presentation timing is reported separately from FPS and is
not a measurement of input-to-photon latency. Lists can increase this delay
even when throughput improves.

The [previous model limitations](../sm64_coupled_20260922/REPORT.md) still apply:
CPU memory traffic and cache writebacks do not traverse the physical arbiter;
the display queue and mixer OS services are modeled; scanout traffic is a
conservative injection. Synthetic read traffic provides a sensitivity check,
not a calibrated full-system timing prediction.
