//! Local qrate management and standard source tools; no acceptance authority beyond Qleisli.

// Embedded engines share the same support as the private development crates.
extern crate self as qlinties_engine;

#[path = "../qrates/qlidoc/src/lib.rs"]
pub mod qlidoc_engine;
#[path = "../qrates/qlifmt/src/lib.rs"]
pub mod qlifmt_engine;
#[path = "../qrates/qlinties/src/lib.rs"]
mod qlinties_support;

pub mod qlirgo;
mod tools;
pub use qlinties_support::{
    PROFILE, QLEISLI_VERSION, VERSION, adapter, executable, publication, qlinties, report, rules,
    snapshot, source, support,
};
