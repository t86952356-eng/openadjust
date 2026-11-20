#!/usr/bin/env python3
"""Generate the FCL Client Version JSON for the OpenAdjust Android build.

The manifest is a STANDALONE version (no inheritsFrom): the fat jar contains
the fully restored Minecraft 1.8.9 + Adjust client, so only the official 1.8
asset index and a handful of marker libraries are needed:

  - org.lwjgl:lwjgl:3.3.3 (+ module markers) -> makes FCL pick its built-in
    LWJGL 3.3.3 Android runtime (classes + arm64/arm32/x86 natives, including
    nanovg) and skip the lwjglx LWJGL2 shim (the client ships its own
    source-restored org.lwjgl.* bridges).
  - net.java.dev.jna:jna:5.15.0 -> triggers FCL's JNA Android-native
    provisioning (official jna AAR) matching the bundled classes.
  - com.github.oshi:oshi-core:6.6.5 -> parity with the LibFilter expectation.
  - openadjust:client:1.8.9-android -> the fat jar itself (release asset).

Legacy `minecraftArguments` AND modern `arguments` are both written (same
game tokens) for maximum launcher compatibility; the JVM block carries the
`--add-opens=java.base/java.nio=ALL-UNNAMED` flag the client's dev launcher
uses on Java 21. Java 21 is requested via javaVersion (FCL runtime "jre21").
"""

import argparse
import datetime
import json
import urllib.request

VANILLA_1_8_9_META = (
    "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"
)
FALLBACK_ASSET_INDEX = {
    "id": "1.8",
    "sha1": "f6ad102c0413f45c2b803c6b5e978519ab4f7dd4",
    "size": 80879,
    "totalSize": 121426499,
    "url": "https://launchermeta.mojang.com/v1/packages/f6ad102c0413f45c2b803c6b5e978519ab4f7dd4/1.8.json",
    "totalSizeKnown": True,
}

GAME_ARGS = [
    "--username", "${auth_player_name}",
    "--version", "${version_name}",
    "--gameDir", "${game_directory}",
    "--assetsDir", "${assets_root}",
    "--assetIndex", "${assets_index_name}",
    "--uuid", "${auth_uuid}",
    "--accessToken", "${auth_access_token}",
    "--userProperties", "${user_properties}",
    "--userType", "${user_type}",
]
MINECRAFT_ARGUMENTS = " ".join(GAME_ARGS)

JVM_ARGS = [
    "-Djava.library.path=${natives_directory}",
    "-Djna.tmpdir=${natives_directory}",
    "-Dorg.lwjgl.system.librarypath=${natives_directory}",
    "--add-opens=java.base/java.nio=ALL-UNNAMED",
    "-Dfile.encoding=UTF-8",
]


def maven_lib(group, artifact, version, base_url):
    path = "%s/%s/%s/%s-%s.jar" % (group.replace(".", "/"), artifact, version,
                                   artifact, version)
    return {
        "name": "%s:%s:%s" % (group, artifact, version),
        "downloads": {"artifact": {"path": path, "url": base_url + path}},
    }


def fetch_vanilla_asset_index():
    try:
        with urllib.request.urlopen(VANILLA_1_8_9_META, timeout=30) as r:
            manifest = json.load(r)
        for v in manifest["versions"]:
            if v["id"] == "1.8.9":
                with urllib.request.urlopen(v["url"], timeout=30) as r:
                    vanilla = json.load(r)
                return vanilla["assetIndex"]
    except Exception as exc:  # CI may be offline; fall back to pinned copy
        print("[warn] could not fetch vanilla 1.8.9 manifest (%s); using pinned assetIndex" % exc)
    return dict(FALLBACK_ASSET_INDEX)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--client-url", required=True)
    ap.add_argument("--id", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    jar_name = args.jar.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    libraries = [
        maven_lib("org.lwjgl", "lwjgl", "3.3.3", "https://repo1.maven.org/maven2/"),
        maven_lib("org.lwjgl", "lwjgl-glfw", "3.3.3", "https://repo1.maven.org/maven2/"),
        maven_lib("org.lwjgl", "lwjgl-opengl", "3.3.3", "https://repo1.maven.org/maven2/"),
        maven_lib("org.lwjgl", "lwjgl-openal", "3.3.3", "https://repo1.maven.org/maven2/"),
        maven_lib("org.lwjgl", "lwjgl-stb", "3.3.3", "https://repo1.maven.org/maven2/"),
        maven_lib("org.lwjgl", "lwjgl-tinyfd", "3.3.3", "https://repo1.maven.org/maven2/"),
        maven_lib("org.lwjgl", "lwjgl-jemalloc", "3.3.3", "https://repo1.maven.org/maven2/"),
        maven_lib("net.java.dev.jna", "jna", "5.15.0", "https://repo1.maven.org/maven2/"),
        maven_lib("com.github.oshi", "oshi-core", "6.6.5", "https://repo1.maven.org/maven2/"),
        {
            "name": "openadjust:client:1.8.9-android",
            "downloads": {"artifact": {"path": "openadjust/client/1.8.9-android/" + jar_name,
                                       "url": args.client_url}},
        },
    ]

    version = {
        "id": args.id,
        "type": "release",
        "time": now,
        "releaseTime": now,
        "assets": "1.8",
        "assetIndex": fetch_vanilla_asset_index(),
        "mainClass": "net.minecraft.client.main.Main",
        "minecraftArguments": MINECRAFT_ARGUMENTS,
        "arguments": {"game": GAME_ARGS, "jvm": JVM_ARGS},
        "javaVersion": {"component": "java-runtime-delta", "majorVersion": 21},
        "minimumLauncherVersion": 21,
        "libraries": libraries,
    }

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(version, fh, indent=2, ensure_ascii=False)
    print("wrote %s (mainClass=%s, assets=1.8, java=21)" % (args.out, version["mainClass"]))


if __name__ == "__main__":
    main()
