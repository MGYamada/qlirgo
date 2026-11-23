//! Internal shared contracts. This layer must not depend on tool products.

pub mod executable;
pub mod manifest;
pub mod publication;
pub mod report;
pub mod snapshot;
pub mod source;

pub const QLEISLI_VERSION: &str = "0.3.0";
pub const PROFILE: &str = "finite-v0";
