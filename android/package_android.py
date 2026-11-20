#!/usr/bin/env python3
"""OpenAdjust Android fat-jar packager.

Builds a standalone FCL "Client Version" jar for Android by merging the
Gradle-built thin client jar with its runtime dependencies, minus everything
the Fold Craft Launcher (FCL) provides itself at launch:

  EXCLUDED (provided by FCL's built-in LWJGL 3.3.3 Android runtime,
  which - unlike stock LWJGL - includes nanovg, stb, openal, freetype,
  tinyfd, jemalloc natives for arm64/arm32/x86/x86_64):
      lwjgl, lwjgl-glfw, lwjgl-opengl, lwjgl-openal, lwjgl-stb,
      lwjgl-tinyfd, lwjgl-jemalloc, lwjgl-freetype, lwjgl-nanovg
      + every *-natives-windows.jar

  KEPT:
      lwjgl-opus  (Java binding only; native absent on Android - the
                   voicechat code already guards Opus failures, so the
                   module degrades safely instead of crashing)
      lwjgl_util  (unsealed vector/glu helpers behind the source bridges)
      jna/jna-platform (classes only - natives stripped; FCL provisions
                   the Android JNA native when the JSON declares
                   net.java.dev.jna:jna:5.15.0)
      everything else (MC 1.8.9 stack + client libs)

Also strips: opus.dll (Windows-only, bundled in resources), any desktop
native binaries, JAR signatures, multi-release dirs, module-info.
META-INF/services/* entries are concatenated (shadow-jar semantics).
The thin jar is merged FIRST so the client's source-restored
org.lwjgl.* bridges / org.lwjgl.util.glu always win over dependency copies.
"""

import argparse
import json
import os
import re
import sys
import zipfile

# LWJGL 3 core modules supplied by FCL's own runtime (never bundle these)
FCL_PROVIDED_LWJGL_PREFIXES = (
    "lwjgl-", "lwjgl_util2-",
)
LWJGL_KEPT_PREFIXES = ("lwjgl-opus", "lwjgl_util-")

NATIVE_SUFFIXES = (".dll", ".so", ".jnilib", ".dylib", ".a", ".lib", ".pdb")

SKIP_SIGNATURE = re.compile(r"^META-INF/[^/]*\.(SF|RSA|DSA|EC|DSA_OLD)$")


def is_natives_jar(name: str) -> bool:
    return re.search(r"-natives-[a-z0-9_.-]+\.jar$", name) is not None


def skip_dependency_jar(name: str) -> str:
    """Returns a reason string when the whole dependency jar must be skipped."""
    base = os.path.basename(name)
    if is_natives_jar(base):
        return "natives classifier (FCL provides Android natives)"
    if base.startswith("lwjgl-"):
        if base.startswith(LWJGL_KEPT_PREFIXES):
            return None  # lwjgl-opus binding stays (guarded, no native)
        return "LWJGL3 core module (FCL runtime provides classes + Android natives)"
    return None


def keep_entry(path: str, is_thin: bool) -> str:
    """Returns a reason when a single zip entry must be skipped."""
    if path.endswith("/"):
        return None
    lower = path.lower()
    # desktop native binaries never belong in the Android jar
    if lower.endswith(NATIVE_SUFFIXES):
        return "desktop native binary"
    if SKIP_SIGNATURE.match(path):
        return "jar signature"
    if path == "META-INF/MANIFEST.MF":
        return "manifest (rewritten)"
    if path.startswith("META-INF/versions/"):
        return "multi-release overlay (base classes kept)"
    if path == "module-info.class" or path.endswith("/module-info.class"):
        return "module descriptor"
    if not is_thin and path.startswith("META-INF/maven/"):
        return "maven metadata"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--thin-jar", required=True)
    ap.add_argument("--cpfile", required=True,
                    help="printRtCp output: lines of 'CPITEM\\t/path.jar' + 'THINJAR\\t/path.jar'")
    ap.add_argument("--output", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    jars = []  # (path, is_thin) - thin FIRST so its entries win
    deps = []
    with open(args.cpfile, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            kind, _, path = line.partition("\t")
            path = path.strip()
            if kind == "THINJAR":
                if os.path.abspath(path) != os.path.abspath(args.thin_jar):
                    print("[warn] THINJAR mismatch: %s vs %s" % (path, args.thin_jar))
                jars.append((args.thin_jar, True))
            elif kind == "CPITEM":
                reason = skip_dependency_jar(path)
                if reason:
                    deps.append({"jar": os.path.basename(path), "skipped": reason})
                else:
                    jars.append((path, False))
                    deps.append({"jar": os.path.basename(path), "kept": True})

    if not any(t for _, t in jars):
        print("[fatal] thin jar missing from cpfile")
        return 1

    entries = {}           # path -> bytes (first wins)
    services = {}          # META-INF/services/name -> set(lines)
    skipped_entries = {}
    total_before = 0

    for jar_path, is_thin in jars:
        with zipfile.ZipFile(jar_path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                data = zf.read(info.filename)
                total_before += info.file_size
                path = info.filename
                if path.startswith("META-INF/services/") and not path.endswith("/"):
                    text = data.decode("utf-8", "replace")
                    lines = services.setdefault(path, [])
                    for ln in text.splitlines():
                        if ln and ln not in lines:
                            lines.append(ln)
                    continue
                reason = keep_entry(path, is_thin)
                if reason:
                    skipped_entries.setdefault(reason, []).append(path)
                    continue
                if path in entries:
                    continue
                entries[path] = data

    for path, lines in services.items():
        entries[path] = ("\n".join(lines) + "\n").encode("utf-8")

    manifest = (
        "Manifest-Version: 1.0\r\n"
        "Created-By: OpenAdjust Android packager\r\n"
        "Main-Class: net.minecraft.client.main.Main\r\n"
        "\r\n"
    )
    entries["META-INF/MANIFEST.MF"] = manifest.encode("utf-8")

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        for path in sorted(entries):
            out.writestr(path, entries[path])

    size_out = os.path.getsize(args.output)
    report = {
        "input_thin_jar": os.path.basename(args.thin_jar),
        "output_jar": os.path.basename(args.output),
        "size_before_uncompressed": total_before,
        "size_after": size_out,
        "entry_count": len(entries),
        "dependencies": deps,
        "skipped_entry_counts": {k: len(v) for k, v in sorted(skipped_entries.items())},
        "skipped_native_files": [
            p for p in skipped_entries.get("desktop native binary", [])
            if p.startswith("assets/") or "/" not in p
        ][:20],
        "fcl_provided_modules": [
            "lwjgl", "lwjgl-glfw", "lwjgl-opengl", "lwjgl-openal", "lwjgl-stb",
            "lwjgl-tinyfd", "lwjgl-jemalloc", "lwjgl-freetype", "lwjgl-nanovg",
        ],
        "android_notes": {
            "voicechat": "Opus/RNNoise natives do not exist for Android; the "
                         "upstream code already wraps every construction in "
                         "try/catch(Throwable), so the module degrades with a "
                         "log line instead of crashing.",
            "jna": "classes bundled, natives stripped; FCL provisions the "
                   "Android JNA native from the jna:5.15.0 AAR declared in the version JSON.",
            "lwjgl_classification": "version JSON declares org.lwjgl:lwjgl:3.3.3 so "
                                    "FCL selects its LWJGL3 runtime WITHOUT the lwjglx "
                                    "shim - the client's own source-restored "
                                    "org.lwjgl.* bridges stay the only ones on the classpath.",
        },
    }
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print("packaged %s (%d entries, %.1f MB -> %.1f MB compressed)" % (
        args.output, len(entries), total_before / 1e6, size_out / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
