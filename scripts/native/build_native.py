"""Export pinned sources and build isolated native article-setting executables.

Upstream clones and source versions remain untouched. Each modified tree has a
complete unified patch and source-hash manifest. No global dependency install.
"""

import argparse
import difflib
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = {
    "eecbs-stay": ("EECBS", "3f5048495c74c57661b332a0c1d33829a973e601"),
    "eecbs-disappear": ("EECBS", "39adefc048a46f4e2da2d361452931643a68994f"),
    "cbsh2": ("CBSH2-RTC", "0d53fa9c62a47d23768429c675e82f893285c49a"),
}


def export(name, revision, target):
    source = subprocess.check_output(
        ["git", "-C", str(ROOT / name), "archive", revision]
    )
    target.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(source)) as archive:
        archive.extractall(target, filter="data")


def original_sources(repo, revision):
    return {
        path: subprocess.check_output(
            ["git", "-C", str(ROOT / repo), "show", revision + ":" + path]
        ).decode()
        for path in subprocess.check_output(
            [
                "git",
                "-C",
                str(ROOT / repo),
                "ls-tree",
                "-r",
                "--name-only",
                revision,
            ]
        )
        .decode()
        .splitlines()
        if Path(path).suffix in (".cpp", ".h", ".txt")
    }


def apply_portability(tree, name, stage):
    if stage != "historical":
        if name.startswith("eecbs"):
            header = tree / "inc/CBSNode.h"
            text = header.read_text()
            if "virtual ~HLNode()" not in text:
                header.write_text(
                    text.replace(
                        "public:\n",
                        "public:\n    virtual ~HLNode() = default; // Required for deletion through the base pointer.\n",
                        1,
                    )
                )
        header = tree / "inc/Instance.h"
        header.write_text(
            header.read_text().replace(
                "0 < loc - num_of_cols", "0 <= loc - num_of_cols"
            )
        )
    cmake = tree / "CMakeLists.txt"
    content = (
        cmake.read_text()
        .replace('set(BOOST_ROOT "D:/boost/1_73_0")', "")
        .replace('set(BOOST_INCLUDEDIR "D:/boost/1_73_0")', "")
    )
    cmake.write_text(content)
    if stage == "corrected":
        from corrections import apply

        apply(tree, name)


def write_patch(tree, name, original):
    patch = "".join(
        "".join(
            difflib.unified_diff(
                before.splitlines(True),
                (tree / path).read_text().splitlines(True),
                fromfile="a/" + path,
                tofile="b/" + path,
            )
        )
        for path, before in original.items()
    )
    (tree.parent / (name + "-portability.patch")).write_text(patch)


def settings_for(name, stage):
    if name == "eecbs-disappear":
        return [3, 4]
    if name == "eecbs-stay" or stage == "corrected":
        return [1, 2]
    return [2]


def build_definitions(setting):
    return [
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_CXX_STANDARD=14",
        "-DCMAKE_POLICY_VERSION_MINIMUM=3.5",
        "-DCMAKE_POLICY_DEFAULT_CMP0167=OLD",
        "-DBoost_NO_SYSTEM_PATHS=ON",
        "-DBoost_USE_STATIC_LIBS=ON",
        "-DBOOST_ROOT=" + str(ROOT / "boost-install"),
        "-DNO_WAIT=" + str(int(setting in (1, 3))),
        "-DDISAPPEAR_AT_TARGET=" + str(int(setting in (3, 4))),
    ]


def compile_tree(tree, build, definitions, log):
    with log.open("w") as output:
        subprocess.run(
            ["cmake", "-S", str(tree), "-B", str(build), *definitions],
            stdout=output,
            stderr=subprocess.STDOUT,
            check=True,
        )
        subprocess.run(
            ["cmake", "--build", str(build), "--parallel", "4"],
            stdout=output,
            stderr=subprocess.STDOUT,
            check=True,
        )


def binary_path(build, name, setting):
    return build / (
        "cbs"
        if name == "cbsh2"
        else "eecbs-"
        + ("DaT" if setting in (3, 4) else "noDaT")
        + "-"
        + ("noW" if setting in (1, 3) else "wW")
    )


def prepare_source(name, source, stage):
    repo, revision = source
    tree = ROOT / stage / name
    if not tree.exists():
        export(repo, revision, tree)
    original = original_sources(repo, revision)
    apply_portability(tree, name, stage)
    write_patch(tree, name, original)


def build_profile(name, source, stage, setting):
    repo, revision = source
    tree = ROOT / stage / name
    build = ROOT / "build" / f"{stage}-{name}-s{setting}"
    definitions = build_definitions(setting)
    log = ROOT / f"{stage}-{name}-s{setting}-build.log"
    compile_tree(tree, build, definitions, log)
    binary = binary_path(build, name, setting)
    assert binary.is_file(), binary
    return {
        "name": name,
        "family": "cbsh2-rtc" if name == "cbsh2" else "eecbs",
        "repository": repo,
        "revision": revision,
        "setting": f"SETTING_{setting}",
        "executable": str(binary),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "coordinate_order": "row-col",
        "stage": stage,
        "cmake_definitions": definitions,
        "source_files": {
            str(p.relative_to(tree)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(tree.rglob("*"))
            if p.is_file()
        },
        "qualifications": "unqualified; actual-binary tests pending",
    }


def main():
    global ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage",
        choices=("historical", "memory-fixed", "corrected"),
        default="historical",
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    ROOT = args.root.resolve()
    catalog = []
    for name, source in SOURCES.items():
        prepare_source(name, source, args.stage)
        for setting in settings_for(name, args.stage):
            catalog.append(build_profile(name, source, args.stage, setting))
            (ROOT / f"{args.stage}-catalog.json").write_text(
                json.dumps(catalog, indent=2) + "\n"
            )
            print(f"Built {name} setting {setting}", flush=True)


if __name__ == "__main__":
    main()
