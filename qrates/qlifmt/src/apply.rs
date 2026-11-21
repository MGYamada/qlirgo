//! Per-file atomic replacement through held directories, without following links.

// The public failure contract carries a diagnostic and the completed update list.
#![allow(clippy::result_large_err)]

use std::path::Path;

use crate::support::report::Diagnostic;
use crate::support::snapshot::{Files, InputDirectory};

use super::{changed_files, validate_formatted};

#[derive(Debug)]
pub struct ApplyFailure {
    pub diagnostic: Diagnostic,
    pub updated_files: Vec<String>,
}

fn failure(diagnostic: Diagnostic, updated_files: &[String]) -> ApplyFailure {
    ApplyFailure {
        diagnostic,
        updated_files: updated_files.to_vec(),
    }
}

fn changed(label: &str) -> Diagnostic {
    Diagnostic::error(
        "source_changed",
        "qlirgo",
        format!("Source changed after capture: {label}"),
    )
}

fn io_error(label: &str, error: impl std::fmt::Display) -> Diagnostic {
    Diagnostic::error(
        "format_write",
        "qlirgo",
        format!("Cannot safely update source {label}: {error}"),
    )
}

/// Validate all candidates and all captured current bytes before the first write.
/// Each replacement is atomic; a later failure reports the already updated prefix.
pub fn apply_files(
    root: &Path,
    original: &Files,
    formatted: &Files,
) -> Result<Vec<String>, ApplyFailure> {
    let root = InputDirectory::open(root).map_err(|error| failure(error, &[]))?;
    apply_captured(&root, original, formatted)
}

/// Apply only through the directory object retained when the inputs were captured.
pub fn apply_captured(
    root: &InputDirectory,
    original: &Files,
    formatted: &Files,
) -> Result<Vec<String>, ApplyFailure> {
    root.verify().map_err(|error| failure(error, &[]))?;
    validate_formatted(original, formatted).map_err(|diagnostic| failure(diagnostic, &[]))?;
    if original.is_empty() {
        return Ok(Vec::new());
    }
    apply(root, original, formatted)
}

#[cfg(unix)]
struct StageDirectory {
    parent: std::fs::File,
    directory: std::fs::File,
    name: String,
}

#[cfg(unix)]
impl StageDirectory {
    fn create(parent: std::fs::File) -> std::io::Result<Self> {
        use rustix::fs::{Mode, OFlags, fstat, mkdirat, openat};
        use std::sync::atomic::{AtomicU64, Ordering};

        static SERIAL: AtomicU64 = AtomicU64::new(0);
        let name = format!(
            ".qlifmt-{}-{}.tmp",
            std::process::id(),
            SERIAL.fetch_add(1, Ordering::Relaxed)
        );
        mkdirat(&parent, name.as_str(), Mode::RWXU)?;
        let directory = std::fs::File::from(openat(
            &parent,
            name.as_str(),
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )?);
        let stat = fstat(&directory)?;
        if stat.st_uid != rustix::process::geteuid().as_raw() || stat.st_mode & 0o077 != 0 {
            return Err(std::io::Error::other(
                "Formatter staging requires an owner-only directory.",
            ));
        }
        Ok(Self {
            parent,
            directory,
            name,
        })
    }

    fn still_named(&self) -> std::io::Result<bool> {
        crate::support::snapshot::still_named(&self.parent, self.name.as_ref(), &self.directory)
    }
}

#[cfg(unix)]
impl Drop for StageDirectory {
    fn drop(&mut self) {
        if self.still_named().unwrap_or(false) {
            let _ = rustix::fs::unlinkat(
                &self.parent,
                self.name.as_str(),
                rustix::fs::AtFlags::REMOVEDIR,
            );
        }
    }
}

#[cfg(unix)]
struct Staged {
    stage: std::rc::Rc<StageDirectory>,
    output: std::fs::File,
    name: String,
    label: String,
    installed: bool,
}

#[cfg(unix)]
impl Staged {
    fn still_named(&self) -> std::io::Result<bool> {
        crate::support::snapshot::still_named(
            &self.stage.directory,
            self.name.as_ref(),
            &self.output,
        )
    }

    fn install(&mut self) -> Result<(), Diagnostic> {
        if !self
            .stage
            .still_named()
            .map_err(|error| io_error(&self.label, error))?
            || !self
                .still_named()
                .map_err(|error| io_error(&self.label, error))?
        {
            return Err(io_error(&self.label, "Staged file identity changed."));
        }
        // Resolve the candidate inside the held private directory throughout the rename.
        rustix::fs::renameat(
            &self.stage.directory,
            self.name.as_str(),
            &self.stage.parent,
            self.name.as_str(),
        )
        .map_err(|error| io_error(&self.label, error))?;
        self.installed = true;
        Ok(())
    }
}

#[cfg(unix)]
impl Drop for Staged {
    fn drop(&mut self) {
        if !self.installed && self.still_named().unwrap_or(false) {
            let _ = rustix::fs::unlinkat(
                &self.stage.directory,
                self.name.as_str(),
                rustix::fs::AtFlags::empty(),
            );
        }
    }
}

#[cfg(unix)]
fn apply(
    root: &InputDirectory,
    original: &Files,
    formatted: &Files,
) -> Result<Vec<String>, ApplyFailure> {
    apply_with_hook(root, original, formatted, |_, _| {})
}

#[cfg(unix)]
fn apply_with_hook(
    root: &InputDirectory,
    original: &Files,
    formatted: &Files,
    mut before_replace: impl FnMut(&str, usize),
) -> Result<Vec<String>, ApplyFailure> {
    use std::collections::BTreeMap;
    use std::collections::btree_map::Entry;
    use std::fs::File;
    use std::io::{Read, Write};
    use std::rc::Rc;

    use rustix::fs::{Mode, OFlags, fstat, openat};

    let directory_flags = OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC;
    let root_file = root.held_file().map_err(|error| failure(error, &[]))?;

    fn parent(root: &File, label: &str, flags: OFlags) -> Result<(File, String), Diagnostic> {
        let mut directory = root.try_clone().map_err(|error| io_error(label, error))?;
        let mut components = label.split('/').peekable();
        while let Some(component) = components.next() {
            if components.peek().is_none() {
                return Ok((directory, component.to_owned()));
            }
            directory = File::from(
                openat(&directory, component, flags, Mode::empty())
                    .map_err(|error| io_error(label, error))?,
            );
        }
        Err(io_error(label, "Invalid empty source path."))
    }

    fn current(directory: &File, name: &str, label: &str) -> Result<Vec<u8>, Diagnostic> {
        let fd = openat(
            directory,
            name,
            OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::NONBLOCK | OFlags::CLOEXEC,
            Mode::empty(),
        )
        .map_err(|error| io_error(label, error))?;
        let file = File::from(fd);
        if !file
            .metadata()
            .map_err(|error| io_error(label, error))?
            .is_file()
        {
            return Err(io_error(label, "Source must be an ordinary file."));
        }
        let mut bytes = Vec::new();
        file.take(crate::support::snapshot::FILE_BYTES + 1)
            .read_to_end(&mut bytes)
            .map_err(|error| io_error(label, error))?;
        Ok(bytes)
    }

    // All selected source paths are checked, including files with no changes.
    for (label, expected) in original {
        let (directory, name) =
            parent(&root_file, label, directory_flags).map_err(|error| failure(error, &[]))?;
        if current(&directory, &name, label).map_err(|error| failure(error, &[]))? != *expected {
            return Err(failure(changed(label), &[]));
        }
    }
    let mut directories = BTreeMap::new();
    let mut staged = Vec::new();
    for label in changed_files(original, formatted) {
        let (directory, name) =
            parent(&root_file, &label, directory_flags).map_err(|error| failure(error, &[]))?;
        let input = File::from(
            openat(
                &directory,
                name.as_str(),
                OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::NONBLOCK | OFlags::CLOEXEC,
                Mode::empty(),
            )
            .map_err(|error| failure(io_error(&label, error), &[]))?,
        );
        let metadata = input
            .metadata()
            .map_err(|error| failure(io_error(&label, error), &[]))?;
        if !metadata.is_file() {
            return Err(failure(
                io_error(&label, "Source must be an ordinary file."),
                &[],
            ));
        }
        let permissions = metadata.permissions();
        let parent_label = Path::new(&label)
            .parent()
            .expect("source filename")
            .to_owned();
        let stage = match directories.entry(parent_label) {
            Entry::Vacant(entry) => {
                let directory = StageDirectory::create(directory)
                    .map_err(|error| failure(io_error(&label, error), &[]))?;
                entry.insert(Rc::new(directory))
            }
            Entry::Occupied(entry) => entry.into_mut(),
        };
        let fd = openat(
            &stage.directory,
            name.as_str(),
            OFlags::WRONLY | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::RUSR | Mode::WUSR,
        )
        .map_err(|error| failure(io_error(&label, error), &[]))?;
        let mut candidate = Staged {
            stage: Rc::clone(stage),
            output: File::from(fd),
            installed: false,
            name,
            label,
        };
        candidate
            .output
            .write_all(&formatted[&candidate.label])
            .and_then(|()| candidate.output.set_permissions(permissions))
            .and_then(|()| candidate.output.sync_all())
            .map_err(|error| failure(io_error(&candidate.label, error), &[]))?;
        staged.push(candidate);
    }
    let mut updated = Vec::new();
    for mut candidate in staged {
        before_replace(&candidate.label, updated.len());
        root.verify().map_err(|error| failure(error, &updated))?;
        let (fresh_parent, _) = parent(&root_file, &candidate.label, directory_flags)
            .map_err(|error| failure(error, &updated))?;
        let old_parent = fstat(&candidate.stage.parent)
            .map_err(|error| failure(io_error(&candidate.label, error), &updated))?;
        let new_parent = fstat(&fresh_parent)
            .map_err(|error| failure(io_error(&candidate.label, error), &updated))?;
        if old_parent.st_dev != new_parent.st_dev || old_parent.st_ino != new_parent.st_ino {
            return Err(failure(changed(&candidate.label), &updated));
        }
        if current(&candidate.stage.parent, &candidate.name, &candidate.label)
            .map_err(|error| failure(error, &updated))?
            != original[&candidate.label]
        {
            return Err(failure(changed(&candidate.label), &updated));
        }
        candidate
            .install()
            .map_err(|error| failure(error, &updated))?;
        updated.push(candidate.label.clone());
    }
    Ok(updated)
}

#[cfg(all(test, unix))]
mod tests {
    use super::super::format_files;
    use super::*;

    #[test]
    fn mismatched_staging_entries_are_neither_installed_nor_cleaned_up() {
        use std::fs::{self, File};
        use std::os::unix::fs::symlink;

        let directory = tempfile::tempdir().unwrap();
        let root = directory.path();
        let stage = std::rc::Rc::new(StageDirectory::create(File::open(root).unwrap()).unwrap());
        let staging = root.join(&stage.name);
        fs::write(staging.join("held"), b"formatted").unwrap();
        fs::write(staging.join("other"), b"formatted").unwrap();
        symlink("held", staging.join("link")).unwrap();
        for name in ["other", "link", "absent"] {
            fs::write(root.join(name), b"original").unwrap();
            let mut staged = Staged {
                stage: stage.clone(),
                output: File::open(staging.join("held")).unwrap(),
                name: name.to_owned(),
                label: name.to_owned(),
                installed: false,
            };
            assert_eq!(staged.install().unwrap_err().id, "format_write");
            drop(staged);
            assert_eq!(fs::read(root.join(name)).unwrap(), b"original");
            assert_eq!(fs::read(staging.join("other")).unwrap(), b"formatted");
            assert_eq!(
                fs::read_link(staging.join("link")).unwrap(),
                Path::new("held")
            );
            assert!(!staging.join("absent").exists());
        }
    }

    #[test]
    fn a_different_empty_directory_is_preserved_during_staging_cleanup() {
        use std::fs::{self, File};
        let home = tempfile::tempdir().unwrap();
        let root = home.path();
        fs::create_dir(root.join("held")).unwrap();
        fs::create_dir(root.join("other")).unwrap();
        let stage = StageDirectory {
            parent: File::open(root).unwrap(),
            directory: File::open(root.join("held")).unwrap(),
            name: "other".to_owned(),
        };
        assert!(!stage.still_named().unwrap());
        drop(stage);
        assert!(root.join("other").is_dir());
    }

    #[test]
    fn byte_identical_directory_replacement_is_rejected_before_any_write() {
        for single_file in [false, true] {
            let home = tempfile::tempdir().unwrap();
            let root = home.path().join("src");
            let old = home.path().join("old");
            let source = b"pub unitary fn identity(q:Q<Bit>)->Q<Bit>{q}";
            std::fs::create_dir(&root).unwrap();
            std::fs::write(root.join("module.qli"), source).unwrap();
            let selected = if single_file {
                root.join("module.qli")
            } else {
                root.clone()
            };
            let input = crate::support::source::capture_source(&selected).unwrap();
            let formatted = format_files(input.sources.files()).unwrap();
            std::fs::rename(&root, &old).unwrap();
            std::fs::create_dir(&root).unwrap();
            std::fs::write(root.join("module.qli"), source).unwrap();
            let failed = apply_captured(&input.original_root, input.sources.files(), &formatted)
                .unwrap_err();
            assert!(failed.updated_files.is_empty());
            for directory in [&root, &old] {
                assert_eq!(std::fs::read(directory.join("module.qli")).unwrap(), source);
                assert_eq!(std::fs::read_dir(directory).unwrap().count(), 1);
            }
        }
    }

    #[test]
    fn later_io_failure_reports_the_atomic_update_prefix_and_cleans_staging() {
        let directory = tempfile::tempdir().unwrap();
        let source = b"pub unitary fn identity(q:Q<Bit>)->Q<Bit>{q}";
        let original = Files::from([
            ("a.qli".into(), source.to_vec()),
            ("b.qli".into(), source.to_vec()),
        ]);
        for (label, bytes) in &original {
            std::fs::write(directory.path().join(label), bytes).unwrap();
        }
        let formatted = format_files(&original).unwrap();
        let failed = apply_with_hook(
            &InputDirectory::open(directory.path()).unwrap(),
            &original,
            &formatted,
            |label, count| {
                if count == 1 {
                    std::fs::remove_file(directory.path().join(label)).unwrap();
                }
            },
        )
        .unwrap_err();
        assert_eq!(failed.updated_files, ["a.qli"]);
        assert_eq!(failed.diagnostic.id, "format_write");
        assert_eq!(
            std::fs::read(directory.path().join("a.qli")).unwrap(),
            formatted["a.qli"]
        );
        assert!(std::fs::read_dir(directory.path()).unwrap().all(|entry| {
            !entry
                .unwrap()
                .file_name()
                .to_string_lossy()
                .starts_with(".qlifmt-")
        }));
    }
}

#[cfg(not(unix))]
fn apply(
    _root: &InputDirectory,
    _original: &Files,
    _formatted: &Files,
) -> Result<Vec<String>, ApplyFailure> {
    Err(failure(
        io_error(
            "root",
            "Atomic formatter updates are supported only on Linux and macOS.",
        ),
        &[],
    ))
}
