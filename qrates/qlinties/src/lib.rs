//! Advisory Qleisli lint rules and their native checker adapter.

pub mod adapter;
pub mod qlinties;
pub mod rules;
pub use crate::support;

pub use support::{PROFILE, QLEISLI_VERSION, executable, publication, report, snapshot, source};
pub const VERSION: &str = env!("CARGO_PKG_VERSION");
