# qlinties qrate

This local qrate contains one short Qleisli management sample, `src/smoke.qli`, and zero QLT test files. The sample exports the unitary `identity` function, which returns its input unchanged. Its Rust engine, CLI, checker adapter and Rust tests also belong to this qrate and are included in its input identity and build snapshot. Developer Cargo configuration remains outside the qrate; qlirgo does not compile the Rust implementation. The engine can diagnose external Qleisli projects. Empty Qleisli-source checks remain supported and are explicitly reported as not run.

qlinties is part of the standard 0.2.0-beta Rust bundle (qrate base version 0.2.0) alongside qlifmt and qlidoc. Snapshot, diagnostic, identity and syntax utilities come from the neutral Rust modules in `tool-support/`. qlifmt formats Qleisli sources; qlidoc generates Markdown from syntax and doc comments. QLT execution remains unavailable. Qlirgo never substitutes Cargo tests or Rustdoc for Qleisli tools. Build records, lint results, formatting, and generated documentation are metadata, not mathematical evidence.

`qlinties --list-rules --format=json` returns rule catalog version 1 without reading sources or running the checker. `unused_import` belongs to `idiom`; `redundant_repeat_one` and `double_inverse` belong to `complexity`. All remain `advisory` warnings. The empty `resource` group and `checker_candidate`/`theorem_candidate` policies reserve a place for future observations that may be absorbed by Qleisli checking or theorem obligations. Neither classification nor candidate status is evidence. Lint diagnostics retain their existing shape and join to catalog entries by diagnostic ID.

Rust development uses the independent `rust/qlinties/` Cargo workspace with its
own manifest, lockfile and Rust toolchain declaration. Transfer that directory
together with this qrate and the neutral `tool-support/` sources; see [independent development](../../../docs/qrate-development.md)
for extraction, dependency capture and verification without the original checkout.
