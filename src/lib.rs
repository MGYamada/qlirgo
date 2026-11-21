//! Local qrate management and standard source tools; no acceptance authority beyond Qleisli.

#[path = "../tool-support/mod.rs"]
pub mod support;

#[path = "../qrates/qlidoc/src/lib.rs"]
pub mod qlidoc_engine;
#[path = "../qrates/qlifmt/src/lib.rs"]
pub mod qlifmt_engine;
#[path = "../qrates/qlinties/src/lib.rs"]
pub mod qlinties_engine;

pub mod qlirgo;
mod tools;
pub use qlinties_engine::{adapter, qlinties, rules};
pub use support::{PROFILE, QLEISLI_VERSION, executable, publication, report, snapshot, source};

pub const VERSION: &str = env!("CARGO_PKG_VERSION");
