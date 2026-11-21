# qlirgo / qlinties naming migration

Status: functional qlirgo 0.2.0-beta preparation, not a publication. The GitHub
repository is MGYamada/qlirgo. The root package and private Rust component versions
are 0.2.0-beta, while bundled qrate manifests retain base version 0.2.0; the four tools are qlirgo, qlinties, qlifmt and qlidoc. qrate remains
unchanged. The root library is qlirgo_tools and the engines share the neutral Rust sources in
`tool-support/`. Root CLI/test adapters remain wiring only.

## Transitional manifests

Qlirgo.toml is preferred by qlirgo. Qargo.toml is a supported legacy fallback.
At the nearest directory containing either name, capture both entries through
one held directory, reject nonregular/symlinked entries, invalid UTF-8 and
manifests over 65536 bytes, and compare exact bytes when both exist. Differences
produce manifest_conflict without choosing an older manifest or ancestor.
All selected manifests still require schema-version = 2 and explicit string
[qrate].edition = "2026". There is no inferred/default edition.

Explicit --manifest-path names a real file and retains support for arbitrary
filenames. Missing explicit paths fail. The parent directory's standard-name
pair is validated even for explicit selection; neither spelling bypasses a
conflict. Standard-name selection prefers Qlirgo.toml after equality checking.
Managed source-root manifests override the owning fallback; nested manifests
retain nearest-directory precedence. Standalone lint inherits only the nearest
actual ancestor pair when there is no source-root manifest. Ancestor entries,
including absence of either name, and descriptor ancestry are revalidated.
Invalid nearer configuration never falls back. Raw and normalized captures
retain the existing aggregate budgets, including duplicate manifest bytes.

Bundled qrates carry identical Qlirgo.toml and Qargo.toml files; developer audits
and CI require both ordinary files and their byte equality. There is no automatic
user-manifest rewrite. User files, root and nested, remain byte-exact raw inputs.

## Separate identities and materializations

input_id hashes the complete raw qrate inventory with actual manifest filenames,
including both names when present, using qlirgo.qrate.v1. Build snapshots preserve
that inventory. An explicitly selected custom filename remains its actual name.

Effective source configuration selects each validated pair and normalizes its
label to Qlirgo.toml. Its source_configuration_id uses
qlirgo.source-configuration.v1 and this canonical relative map, including nested
paths and exact selected bytes. Identical effective bytes/configuration locations
have the same configuration ID independent of old/new/dual spelling, while their
raw qrate input IDs differ. The .qli-only qleisli.source.v1 identity is unchanged.
The actual embedded std content domain is qlirgo.bundled-std.v1.

Parent-to-child lint transport uses only the canonical configuration map. Only
the private stage passed to the fixed beta compiler substitutes Qargo.toml file
labels, preserving selected bytes and directory relationships. Derived compiler
aliases do not enter input_id, raw snapshots or configuration identities.
Manifest diagnostics refer to logical canonical configuration, without private
stage paths. Ordinary Qleisli checking is neither replaced nor weakened.
Standalone format/document operations remain syntax-only.

Qleisli stays exactly =0.3.0-beta and its source, loader and bundled std are not
edited. Its whole ecosystem filename/default migration belongs to 0.3.0 stable.
The four Cargo lockfiles select the published crates.io package from the
[Qleisli beta release](https://github.com/MGYamada/Qleisli/releases/tag/v0.3.0-beta).

## Public names and distribution

The previous draft name was `qlinty`. The executable, explicit tool option
(`--qlinties`), linter engine identity and version-1 envelope now use
`qlinties`. The bundle ships no `qlinty` command and rejects `--qlinty` and
`qlinty.result`. The three lint rule IDs, source spans and exit codes are preserved. There are no old qargo/qlippy command aliases,
--qlippy option, old-tool search fallback or old JSON acceptance. Shell aliases
are a user choice. Parent envelopes/build records are qlirgo.result and
qlirgo.build-record version 2; the linter uses qlinties.result version 1. qlifmt and
qlidoc envelopes remain version 1. Other fields/contracts retain their shapes.
Product versions, manifest versions and protocol versions remain independent.
Qrate versions may carry SemVer prerelease identifiers (for example 0.2.0-beta
or 0.3.0-alpha), preserved byte-exactly through configuration and build capture.
The selected bundled qrate version remains 0.2.0 by explicit release policy.

Artifacts use target/qlirgo. Archives use qlirgo-<version>-<target>, install state
uses lib/qlirgo, and all four binaries must have one release and linked beta
identity. Old qargo installations are not automatically modified; shared
qlifmt/qlidoc or other command collisions refuse with a separate-prefix hint.
The package requires documentation = "https://docs.rs/qlirgo/0.2.0-beta".

Published qargo 0.2.0-final and 0.2.0 remain immutable failure-only migration
wrappers. The reserved qlirgo 0.1.0 does not supply this functional bundle.
Historical records and fixed fixtures keep their original names and bytes.

## Validation

The [October rename checks](naming-validation.json) and [October beta preparation](beta-release-validation.json)
record local source-override builds. The registry dependency became available in November.
The merged rename and tool separation passed [bundle and package CI](https://github.com/MGYamada/qlirgo/actions/runs/44842588493)
and the [three-tool extraction matrix](https://github.com/MGYamada/qlirgo/actions/runs/44842047553).
The source trees tested in those runs are identical to [the merged source tree](https://github.com/MGYamada/qlirgo/tree/d058e041a332521a3da0f0625b2899c759247e60).

Use the [release checklist](releasing.md) for each publication candidate.
[Issue #40](https://github.com/MGYamada/qlirgo/issues/40) tracks candidate commits, validation and the stable migration.
