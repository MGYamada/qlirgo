"""Bind the official beta kernel archive to the actual locked compiler sources in CI."""
import hashlib
import json
from pathlib import Path
import platform
import sys
import tarfile
import tomllib

VERSION = "0.3.0-beta"
COMMIT = "ce71d151427af30f9fffe8d967524b905265701f"
# Published SHA256SUMS at https://github.com/MGYamada/Qleisli/releases/tag/v0.3.0-beta
HOSTS = {
    ("Linux", "x86_64"): ("x86_64-unknown-linux-gnu", "59e52cf0583e90f2cfbdb5762753a29822fc77e69db82a353ae85585d0de2828"),
    ("Darwin", "arm64"): ("aarch64-apple-darwin", "b6c523f308d355945141b8564f275035ff98f0b682c8586772caec32b4d4bf97"),
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(source, archive, output):
    host = (platform.system(), platform.machine())
    target, checksum = HOSTS[host]
    prefix = "qleisli-kernel-" + VERSION + "-" + target
    if archive.name != prefix + ".tar.gz" or digest(archive) != checksum:
        raise ValueError("Unexpected beta kernel archive identity")
    package = tomllib.loads((source / "Cargo.toml").read_text())["package"]
    vcs = json.loads((source / ".cargo_vcs_info.json").read_bytes())
    if (package["name"], package["version"], vcs["git"]["sha1"]) != ("qleisli", VERSION, COMMIT):
        raise ValueError("The linked crate does not identify the released Qleisli sources")

    # Only the two fixed archives above can reach extraction.
    with tarfile.open(archive, "r:gz") as bundle:
        if not all(member.isfile() and Path(member.name).parts[0] == prefix
                   and ".." not in Path(member.name).parts for member in bundle):
            raise ValueError("Unexpected beta kernel archive member")
        work = output.parent / prefix
        work.mkdir()
        bundle.extractall(output.parent, filter="data")
    manifest_path = work / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    dist = json.loads((work / "distribution.json").read_bytes())
    if (dist["source_commit"], dist["target"], dist["package_version"], dist["bundle_manifest_sha256"]) != (
            COMMIT, target, VERSION, digest(manifest_path)):
        raise ValueError("Native distribution manifest differs from the selected beta")
    if (manifest["package_version"], manifest["platform"], manifest["machine"],
            manifest["validation"]["lane"], manifest["validation"]["fresh_replay"]) != (
            VERSION, *host, "full", True):
        raise ValueError("Expected a complete audited native beta release bundle")
    for relative, expected in manifest["sources"].items():
        if digest(source / relative) != expected:
            raise ValueError("Linked source differs from the native release: " + relative)
    for relative, expected in manifest["files"].items():
        if digest(work / relative) != expected:
            raise ValueError("Released kernel payload differs: " + relative)
    work.rename(output)
    print(f"Selected {target} kernel from {COMMIT}, archive SHA-256 {checksum}")


if __name__ == "__main__":
    verify(*(Path(arg) for arg in sys.argv[1:]))
