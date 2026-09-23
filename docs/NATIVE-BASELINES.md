# Optional native article baselines

The Python simulation, batch CLI and GUI work without C++ binaries. These optional
baselines supply actual EECBS and CBSH2-RTC implementations; the existing Python
`EECBS` identifier still means simplified focal CBS and must not be relabelled.

## License boundary

EECBS and CBSH2-RTC retain USC's research/non-profit license terms. They are not included in this project's MIT grant, and commercial use requires permission from the upstream rights holder. Read the [pinned license texts](licenses/native.txt) before obtaining or redistributing their source, binaries or source-derived patches.

## Source and semantics

The build recipe pins [the author's EECBS fork](https://github.com/erancihan/EECBS)
at `3f5048495c74c57661b332a0c1d33829a973e601` for stay-at-target and
`39adefc048a46f4e2da2d361452931643a68994f` for its separate
`Disappear-at-target` branch. Setting a CMake banner on the stay branch does not
implement disappearance. EECBS runs with the source defaults, all default
improvements, and explicit weight 1.0 or 1.1. The solver seeds its search with zero.

[CBSH2-RTC](https://github.com/Jiaoyang-Li/CBSH2-RTC) is pinned at
`0d53fa9c62a47d23768429c675e82f893285c49a`, the period-matched upstream revision.
It supplies settings 1/2 only and takes no `--suboptimality` argument. Its seed is
zero. The historical archive contains Windows binaries, without matching source
receipts; this build is an explicitly corrected source reconstruction, not a claim
of byte-identical historical executable recovery.

The recipe exports source trees without editing the clones and records every
change as a unified patch. The patches address concrete qualification failures:

- EECBS deletes polymorphic high-level nodes through a base class without a
  virtual destructor. Add the required destructor; contemporary Clang builds
  otherwise trap during cleanup on many small instances.
- Both stay-at-target implementations allow a premature goal visit followed by
  departure. Stop expanding such states to implement the modern absorbing first
  arrival contract. Historical final-arrival MAPF paths remain separate evidence.
- Add a compile-time no-wait path-construction mode to CBSH2-RTC for setting 1.
- Backport the upstream `getDegree` fix for location zero.
- Make heap comparisons strict and stable: equal keys compare false, including
  self-comparison. Remove coin flips made during individual comparisons, which
  violate the heap ordering contract. This changes historical tie behavior and is
  explicitly part of the corrected native variant.
- Check the path/MDD depth contract before strengthened rectangle reasoning.
  EECBS may cache a relaxed shortest MDD that is shorter than its current feasible
  absorbing-goal path. Indexing that MDD by the path length caused a native
  segmentation fault on a 40-agent article instance. A mismatch now returns to
  ordinary CBS conflict splitting. Clipping indices or treating the relaxed MDD
  as the actual path would not establish a sound strengthened constraint. The
  guard also rejects missing paths/MDDs and out-of-range conflict times. Matching
  paths still use rectangle reasoning; its positive control is tested.
- Bound CBSH2's generalized corridor scan by visited locations: a degree-two cycle
  has no corridor endpoints and must fall back to the ordinary conflict split.
- Reject the generalized corridor-target strengthening when both starts and both
  goals lie in that corridor. An independent witness has optimal cost 10 while the
  historical strengthening eliminates that solution and returns 11 as optimal.
  Ordinary CBS conflict splitting remains available in this case; other default
  improvements remain enabled. This guarded implementation is labelled modified.

The fixture suite uses an independent finite joint-state Dijkstra search, separate
trajectory checks, rectangular grids, obstacles, all settings and both EECBS
weights. It compares action cost and the native reported CSV cost. A finite pass
does not prove universal optimality, a global weighted bound or historical score
equivalence. Retain every qualification receipt with a scientific run.

## Isolated build

Use a separate local directory, CMake and a C++14 compiler. Preserve upstream
licenses in the exported trees: the native projects have their own USC research
license; they are not relicensed by this Python project's MIT license.

Clone the two repositories into `NATIVE_ROOT/EECBS` and `NATIVE_ROOT/CBSH2-RTC`.
Install Boost program_options, filesystem and system **inside**
`NATIVE_ROOT/boost-install`. The audited dependency is Boost 1.78.0; its official
[archive checksum](https://archives.boost.io/release/1.78.0/source/boost_1_78_0.tar.bz2.json)
is `8681f175d4bdb26c52222665793eef08490d7758529330f98d3b29dd0735bccc`.
From the extracted Boost directory, run its `bootstrap.sh` with those three
libraries and your absolute prefix, then `./b2 -j4 link=static threading=multi
variant=release cxxstd=14 --with-program_options --with-filesystem --with-system
--prefix=ABSOLUTE_NATIVE_ROOT/boost-install install`. No global package upgrade
is needed. Record compiler, CMake, dependency and executable hashes.

From this repository:

```bash
.venv/bin/python scripts/native/build_native.py --root /absolute/native-root --stage historical
.venv/bin/python scripts/native/qualify_native.py --root /absolute/native-root --stage historical
# Historical failures are evidence; the command deliberately exits nonzero.
.venv/bin/python scripts/native/build_native.py --root /absolute/native-root --stage corrected
.venv/bin/python scripts/native/qualify_native.py --root /absolute/native-root --stage corrected
.venv/bin/python scripts/native/qualify_rectangle.py --catalog /absolute/native-root/corrected-catalog.json --output /absolute/native-root/rectangle-qualification
.venv/bin/python scripts/native/emit_catalog.py --root /absolute/native-root
```

The rectangle check compiles the actual rectangle source and a boundary harness
with AddressSanitizer and UndefinedBehaviorSanitizer, then links the other existing
build objects. It is a focused check, not whole-solver instrumentation. Keep its
receipt together with the independent joint-state oracle qualification and a
replay of any observed large-instance failure. A clean finite suite cannot exclude
all future solver defects. Rebuild in a new directory after changing corrections;
preserve the old executable and its measurements as superseded evidence.

## Ordinary batch/API integration

Set `MAPF_NATIVE_SOLVER_CATALOG=/absolute/native-root/application-catalog.json`
for the local planner or server. The catalog is local administrator configuration;
job requests select its solver IDs and cannot supply executable paths. Profiles
appear in the normal capabilities registry. For example, use
`solver_id: Native-EECBS-S4`, `setting: SETTING_4`, `suboptimality: 1.1`, and an
explicit `timeout_sec` up to 600 in an ordinary [experiment spec](EXPERIMENTS.md).

Planning freezes the executable hash, physical setting, coordinate convention,
source revision, patch hash and qualification receipt hash into the effective
configuration and definition digest. Execution uses that frozen profile even if
the catalog subsequently changes or disappears. A changed executable is rejected.
Replan under a new identity after rebuilding. Keep all artifacts with the manifest;
a hash records identity but is not evidence that a third-party receipt is truthful.

Each job owns a private POSIX process group. Cancellation, deadline, worker failure
and supervisor disappearance stop its native descendants as well as its Python
worker. Native statistics and reported costs survive export alongside independently
recomputed trajectory costs; reported search limits remain distinct from crashes
and from externally enforced wall timeouts.
