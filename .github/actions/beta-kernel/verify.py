"""Bind the official Qleisli kernel and crate to the locked compiler sources."""
import hashlib
import json
from pathlib import Path
import platform
import re
import sys
import tarfile
import tomllib

VERSION = "0.3.0"
HOSTS = {("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
         ("Darwin", "arm64"): "aarch64-apple-darwin"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def association(source, work, lock, commit):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Expected the exact published Qleisli tag commit")
    crate = work / f"qleisli-{VERSION}.crate"
    packages = tomllib.loads(lock.read_text())["package"]
    matching = [entry for entry in packages if entry["name"] == "qleisli"]
    if len(matching) != 1 or matching[0].get("version") != VERSION or (
            matching[0].get("source") != "registry+https://github.com/rust-lang/crates.io-index" or
            matching[0].get("checksum") != digest(crate)):
        raise ValueError("Official Qleisli crate bytes differ from the registry lock")
    package = tomllib.loads((source / "Cargo.toml").read_text())["package"]
    vcs = json.loads((source / ".cargo_vcs_info.json").read_bytes())
    if (package["name"], package["version"], vcs["git"]["sha1"]) != ("qleisli", VERSION, commit):
        raise ValueError("Linked crate does not identify the exact published sources")


def verify(source, work, lock, output, commit, target):
    association(source, work, lock, commit)
    if target == "source":
        return
    host = (platform.system(), platform.machine())
    if HOSTS.get(host) != target:
        raise ValueError("Unsupported published Qleisli kernel host")
    prefix = "qleisli-kernel-" + VERSION + "-" + target
    archive = work / (prefix + ".tar.gz")
    checksum = digest(archive)
    line = f"{checksum}  {archive.name}"
    if (work / "SHA256SUMS").read_text().splitlines().count(line) != 1:
        raise ValueError("Unexpected stable kernel archive identity")

    # Only the selected, checksum-verified archive can reach extraction.
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        if len({member.name for member in members}) != len(members) or not all(
            member.isfile() and not Path(member.name).is_absolute()
            and Path(member.name).parts[0] == prefix and ".." not in Path(member.name).parts
            for member in members
        ):
            raise ValueError("Unexpected kernel archive member")
        work = output.parent / prefix
        work.mkdir()
        bundle.extractall(output.parent, filter="data")
    manifest_path = work / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    dist = json.loads((work / "distribution.json").read_bytes())
    if (dist["source_commit"], dist["target"], dist["package_version"], dist["bundle_manifest_sha256"]) != (
            commit, target, VERSION, digest(manifest_path)):
        raise ValueError("Native distribution manifest differs from the selected stable release")
    if (manifest["package_version"], manifest["platform"], manifest["machine"],
            manifest["validation"]["lane"], manifest["validation"]["fresh_replay"]) != (
            VERSION, *host, "full", True) or manifest.get("protocol") != "qleisli.native-result 4":
        raise ValueError("Expected a complete audited native stable release bundle")
    for relative, expected in manifest["sources"].items():
        if digest(source / relative) != expected:
            raise ValueError("Linked source differs from the native release: " + relative)
    for relative, expected in manifest["files"].items():
        if digest(work / relative) != expected:
            raise ValueError("Released kernel payload differs: " + relative)
    work.rename(output)
    print(f"Selected {target} kernel from {commit}, archive SHA-256 {checksum}")


if __name__ == "__main__":
    verify(*(Path(arg) for arg in sys.argv[1:5]), *sys.argv[5:])
