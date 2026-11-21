#!/usr/bin/env python3
"""Portable Rust project capture. Developer tooling, never a qlirgo operation."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tomllib

from qleisli_dependency import EXPECTED, complete_qleisli_vendor, dependency_root

QRATES = ("qlinties", "qlifmt", "qlidoc")
ENGINE_PACKAGES = {name + "-engine" for name in QRATES}
EXCLUDED = {"target", ".git", "__pycache__", ".DS_Store"}
SCRIPTS = ("qleisli_dependency.py", "qrate_project.py", "verify_qrate.py", "capture_build.py")
CONFIG_NAMES = (".cargo/config", ".cargo/config.toml", "rust-toolchain", "rust-toolchain.toml")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def manifest(path):
    return tomllib.loads(path.read_text(encoding="utf-8"))


def sha256(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def identity(domain, value):
    fields = [domain.encode(), canonical(value)]
    return sha256(b"".join(len(field).to_bytes(8, "big") + field for field in fields))


def entries(root):
    """Capture regular bytes/modes and directories, never following project links."""
    result = []

    def visit(path):
        label = path.relative_to(root).as_posix()
        label.encode("utf-8", errors="strict")
        before = path.lstat()
        if stat.S_ISDIR(before.st_mode):
            result.append({"path": label, "kind": "directory"})
            children = sorted(p.name for p in path.iterdir() if p.name not in EXCLUDED)
            for name in children:
                visit(path / name)
            require(children == sorted(p.name for p in path.iterdir() if p.name not in EXCLUDED),
                    "Directory changed during capture: " + label)
        else:
            require(stat.S_ISREG(before.st_mode), "Project links/special files are forbidden: " + label)
            data = path.read_bytes()
            result.append({"path": label, "kind": "file", "executable": bool(before.st_mode & 0o111),
                           "size": len(data), "sha256": sha256(data)})
        after = path.lstat()
        require((before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                == (after.st_ino, after.st_dev, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                "Input changed during capture: " + label)

    require(root.is_dir() and not root.is_symlink(), "Invalid project directory")
    visit(root)
    return sorted(result, key=lambda item: item["path"].encode())


def snapshot(root, component):
    inventory = [entry for entry in entries(root) if entry["path"] != "project-record.json"]
    optional = {}
    require(component in QRATES, "Unknown component: " + component)
    for directory in (".", "rust", "rust/" + component):
        for name in CONFIG_NAMES:
            label = (Path(directory) / name).as_posix()
            optional[label] = (root / label).is_file()
    selected = [entry for entry in inventory if entry["path"].startswith(
        ("rust/" + component + "/", "qrates/" + component + "/", "tool-support/"))]
    package = manifest(root / "rust" / component / "Cargo.toml")["package"]
    local = [{"name": package["name"], "version": package["version"], "role": "component",
              "snapshot_id": identity("qlirgo.local-rust-inputs.v1", selected)}]
    payload = {"component": component, "entries": inventory, "configuration": optional,
               "local_packages": local}
    return {"format": "qlirgo.rust-project", "version": 1,
            "project_id": identity("qlirgo.rust-project.v1", payload), **payload}


def check_snapshot(root):
    recorded = json.loads((root / "project-record.json").read_bytes())
    require(recorded == snapshot(root, recorded["component"]), "Project inventory/identity changed")
    return recorded


def dependencies(data):
    for key in ("dependencies", "build-dependencies", "dev-dependencies"):
        yield from data.get(key, {}).items()
    for target in data.get("target", {}).values():
        yield from dependencies(target)


def audit(root, components=QRATES, bundle=True):
    """Audit all declared edges, including inactive target/dev/build declarations."""
    support = root / "tool-support"

    def contained(path, roots):
        require(any(path.resolve().is_relative_to(base.resolve()) for base in roots),
                "Source escapes its component boundary: " + str(path))

    def includes(path, source, roots):
        for literal in re.findall(r'(?:#\[path\s*=\s*|include(?:_str|_bytes)?!\(\s*)"([^"]+)"', source):
            contained(path.parent / literal, roots)

    require((support / "mod.rs").is_file(), "Missing neutral tool support")
    for path in support.rglob("*.rs"):
        source = path.read_text()
        require(not re.search(r"\b(?:qlirgo(?:_tools)?|qlinties_engine|qlifmt_engine|qlidoc_engine)\b(?:\s*::|\s+as)", source)
                and not re.search(r"(?:use\s+crate\b(?!::support::)|crate::(?!support::)|super::super)", source),
                "Support depends on a product layer: " + str(path))
        includes(path, source, [support])

    for name in components:
        require(name in QRATES, "Unknown component: " + name)
        owned_roots = [root / "qrates" / name, root / "rust" / name]
        pair = [root / "qrates" / name / filename for filename in ("Qlirgo.toml", "Qargo.toml")]
        require(all(path.is_file() and not path.is_symlink() for path in pair) and pair[0].read_bytes() == pair[1].read_bytes(), "Transitional manifests differ: " + name)
        development = root / "rust" / name
        data = manifest(development / "Cargo.toml")
        require(data.get("workspace") == {"resolver": "3"}, "Each component must own its workspace")
        package = data["package"]
        require(package["name"] == name + "-engine" and package["publish"] is False,
                "Unexpected development package identity")
        require(package["edition"] == "2024" and package["rust-version"] == "1.85",
                "Rust edition/MSRV changed")
        require(data["lints"]["rust"]["unsafe_code"] == "forbid", "Unsafe code must remain forbidden")
        require(data["dependencies"]["qleisli"] == "=0.3.0-beta", "Qleisli must remain exactly pinned")
        require(not any(isinstance(value, dict) and value.get("workspace")
                        for value in package.values()), "Inherited package metadata")
        for alias, dep in dependencies(data):
            package_name = dep.get("package", alias) if isinstance(dep, dict) else alias
            require(package_name not in ("qlirgo", "qlirgo_tools"), "Reverse qlirgo dependency")
            require(package_name not in ENGINE_PACKAGES, "Tool-to-tool Cargo dependency: " + package_name)
            if isinstance(dep, dict):
                require(not dep.get("workspace"), "Inherited dependency: " + alias)
                require("git" not in dep, "Git dependencies require an explicit fixed source capture implementation")
                require("path" not in dep, "Component dependencies must resolve from the captured registry")
        for target in [data["lib"], *data.get("bin", []), *data.get("test", []), *data.get("example", []), *data.get("bench", [])]:
            contained(development / target["path"], owned_roots)
        require([target["name"] for target in data.get("bin", [])] == [name], "Missing component CLI")
        require(data.get("test"), "Missing component tests")
        if package.get("build"):
            contained(development / ("build.rs" if package["build"] is True else package["build"]), owned_roots)
        wrapper = (f'#[path = "../../qrates/{name}/src/lib.rs"]\nmod engine;\n'
                   '#[path = "../../tool-support/mod.rs"]\npub mod support;\n\npub use engine::*;\n')
        require(data["lib"]["path"] == "lib.rs" and (development / "lib.rs").read_text() == wrapper,
                "Standalone adapter must only assemble its engine and neutral support: " + name)
        peers = {peer + "_engine" for peer in QRATES if peer != name}
        for directory in owned_roots:
            for path in directory.rglob("*.rs"):
                if EXCLUDED.intersection(path.relative_to(root).parts):
                    continue
                source = path.read_text()
                require(not re.search(r"\b(?:qlirgo_tools|qlirgo)\s*::", source), "Reverse source dependency: " + str(path))
                require(not peers.intersection(re.findall(r"\b\w+_engine\b", source)), "Peer tool import: " + str(path))
                require("CARGO_MANIFEST_DIR" not in source, "Root-relative runtime fixture: " + str(path))
                includes(path, source, [*owned_roots, support] if path == development / "lib.rs" else owned_roots)
    if bundle:
        for name in QRATES:
            aliases = f"use qlirgo_tools::{name}_engine;\n"
            for label, inclusion in ((f"src/bin/{name}.rs", f"../../qrates/{name}/src/bin/{name}.rs"),
                                     (f"tests/{name}.rs", f"../qrates/{name}/tests/engine.rs")):
                require((root / label).read_text() == aliases + f'include!("{inclusion}");\n',
                        "Bundle adapter must only alias and include canonical code: " + label)
        require((root / "tests/snapshot.rs").read_text()
                == 'use qlirgo_tools::qlinties_engine;\ninclude!("../qrates/qlinties/tests/snapshot.rs");\n',
                "Snapshot adapter changed")


def audit_metadata(metadata, root):
    workspace = Path(metadata["workspace_root"]).resolve()
    require(workspace.name in QRATES and workspace.parent == root / "rust", "Workspace escaped extraction")
    own_manifest = workspace / "Cargo.toml"
    for package in metadata["packages"]:
        require(package["name"] not in ("qlirgo", "qlirgo_tools"), "Reverse dependency in resolved graph")
        path = Path(package["manifest_path"]).resolve()
        if path == own_manifest:
            require(package["name"] == workspace.name + "-engine", "Unexpected component package")
        else:
            require(path.is_relative_to(root / "vendor") and package["name"] not in ENGINE_PACKAGES,
                    "Unexpected package in component dependency graph: " + package["name"])
        # Vendoring puts registry, build and dev sources inside the project as well.
        require(Path(package["manifest_path"]).resolve().is_relative_to(root), "Dependency escaped extraction")
        for target in package["targets"]:
            require(Path(target["src_path"]).resolve().is_relative_to(root), "Target escaped extraction")
        for dep in package["dependencies"]:
            if dep.get("path"):
                require(Path(dep["path"]).resolve().is_relative_to(root), "Dependency path escaped extraction")


def audit_vendor(root, component):
    """Check the complete locked closure, including inactive platform packages."""
    locked = manifest(root / "rust" / component / "Cargo.lock")["package"]
    local = [pkg["name"] for pkg in locked if "source" not in pkg]
    require(local == [component + "-engine"], "Only the selected engine may be local in its lockfile")
    expected = {}
    for package in locked:
        if "source" in package:
            require(package["source"] == "registry+https://github.com/rust-lang/crates.io-index",
                    "Unsupported dependency source in lockfile")
            expected[package["name"] + "-" + package["version"]] = package["checksum"]
    vendor = root / "vendor"
    require({path.name for path in vendor.iterdir()} == set(expected), "Vendor inventory differs from locked dependency closure")
    for name, checksum in expected.items():
        directory = vendor / name
        captured = entries(directory)
        record = json.loads((directory / ".cargo-checksum.json").read_bytes())
        require(record["package"] == checksum, "Registry archive checksum differs from Cargo.lock: " + name)
        files = {entry["path"]: entry["sha256"].removeprefix("sha256:") for entry in captured
                 if entry["kind"] == "file" and entry["path"] != ".cargo-checksum.json"}
        require(files == record["files"], "Vendored source content differs from its checksum inventory: " + name)


def copy_tree(source, destination):
    # Preflight links and special files before any copying.
    captured = entries(source)
    destination.mkdir(parents=True)
    for entry in captured:
        target = destination / entry["path"]
        if entry["kind"] == "directory":
            target.mkdir(exist_ok=True)
        else:
            target.write_bytes((source / entry["path"]).read_bytes())
            target.chmod(0o755 if entry["executable"] else 0o644)
    require(entries(destination) == captured and entries(source) == captured, "Capture changed while copying")


def extract(source, destination, component, cargo):
    source, destination = source.resolve(), destination.resolve()
    require(not destination.exists(), "Extraction destination must not exist")
    require(not destination.is_relative_to(source), "Extraction destination must be outside the original checkout")
    audit(source, (component,), bundle=False)
    # Preparation uses the explicitly selected developer Cargo cache. Verification
    # later uses no cache or ambient Cargo configuration, and cannot fetch.
    for directory in (source, source / "rust", source / "rust" / component):
        for config in (".cargo/config", ".cargo/config.toml"):
            require(not (directory / config).exists(), "Unsupported source Cargo configuration: " + str(directory / config))
    destination.mkdir(parents=True)
    for directory in ("qrates", "rust"):
        copy_tree(source / directory / component, destination / directory / component)
    copy_tree(source / "tool-support", destination / "tool-support")
    copy_tree(source / "docs", destination / "docs")
    for label in ("LICENSE", "NOTICE", "QRATEBOUNDARY.md", *["scripts/" + name for name in SCRIPTS]):
        target = destination / label
        target.parent.mkdir(parents=True, exist_ok=True)
        require((source / label).is_file() and not (source / label).is_symlink(), "Missing extraction input: " + label)
        shutil.copyfile(source / label, target)
    shutil.copyfile(source / "docs/qrate-development.md", destination / "README.md")
    component_manifest = destination / "rust" / component / "Cargo.toml"
    metadata = subprocess.check_output([str(cargo), "metadata", "--frozen", "--format-version=1",
                                        "--manifest-path", str(component_manifest)], cwd=destination)
    registry_source = dependency_root(json.loads(metadata), component_manifest)
    subprocess.run([str(cargo), "vendor", "--offline", "--locked", "--versioned-dirs",
                    "--manifest-path", str(component_manifest),
                    str(destination / "vendor")], check=True, stdout=subprocess.DEVNULL, cwd=destination)
    complete_qleisli_vendor(destination / "vendor" / ("qleisli-" + EXPECTED), registry_source, component_manifest)
    config = destination / "rust" / component / ".cargo/config.toml"
    config.parent.mkdir()
    config.write_text('[source.crates-io]\nreplace-with = "captured"\n\n[source.captured]\ndirectory = "../../vendor"\n')
    audit_vendor(destination, component)
    record = snapshot(destination, component)
    (destination / "project-record.json").write_bytes(canonical(record) + b"\n")
    check_snapshot(destination)
    print(f"Captured {component}: {record['project_id']}")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--component", choices=QRATES)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--cargo", type=Path, default=Path(shutil.which("cargo") or "cargo"))
    args = parser.parse_args()
    if args.destination:
        require(args.component is not None, "Choose a component to extract")
        extract(args.source_root, args.destination, args.component, args.cargo)
    else:
        audit(args.source_root.resolve())
        print("Component dependency and adapter audit passed.")


if __name__ == "__main__":
    main()
