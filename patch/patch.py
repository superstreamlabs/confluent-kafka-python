import argparse
import os
import tempfile
import zipfile

import requests


def get_wheel_urls(package_name, version):
    url = f"https://pypi.org/pypi/{package_name}/{version}/json"
    response = requests.get(url)
    response.raise_for_status()
    metadata = response.json()

    urls = []
    for info in metadata.get("urls"):
        if not info:
            continue
        if info.get("filename", "").endswith(".whl"):
            urls.append(info["url"])

    return urls


def download_whl(url, dest_dir):
    response = requests.get(url, stream=True)
    response.raise_for_status()
    file_path = os.path.join(dest_dir, os.path.basename(url))

    with open(file_path, "wb") as file:
        for chunk in response.iter_content(chunk_size=8192):
            file.write(chunk)


def download_wheels(pkg_name: str, pkg_version: str, dest_dir: str):
    os.makedirs(dest_dir, exist_ok=True)
    wheel_urls = get_wheel_urls(pkg_name, version=pkg_version)
    for url in wheel_urls:
        download_whl(url, dest_dir)


def extract_whl(whl_file, dest_dir=None):
    if not os.path.isfile(whl_file):
        print(f"{whl_file} not found!")
        return
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(whl_file, "r") as zip_ref:
        zip_ref.extractall(dest_dir)


def patch_single(source_build, distribution_build, dest_dir, prefix):
    def patch_cimpl(source_build_dir, distribution_build_dir):
        src_confluent_kafka = os.path.join(source_build_dir, "confluent_kafka")
        distribution_confluent_kafka = os.path.join(
            distribution_build_dir, "confluent_kafka"
        )

        src_cimpl_files = [
            f for f in os.listdir(src_confluent_kafka) if f.startswith("cimpl.")
        ]
        dist_cimpl_files = [
            f
            for f in os.listdir(distribution_confluent_kafka)
            if f.startswith("cimpl.")
        ]

        if src_cimpl_files:
            for f in src_cimpl_files:
                os.remove(os.path.join(src_confluent_kafka, f))

        if dist_cimpl_files:
            for f in dist_cimpl_files:
                dist_cimpl = os.path.join(distribution_confluent_kafka, f)
                src_cimpl = os.path.join(src_confluent_kafka, f)
                os.rename(dist_cimpl, src_cimpl)

    def patch_record(src_build_dir, distribution_build_dir):
        src_dist_info = [
            d for d in os.listdir(src_build_dir) if d.endswith(".dist-info")
        ][0]
        distribution_dist_info = [
            d for d in os.listdir(distribution_build_dir) if d.endswith(".dist-info")
        ][0]

        source_record = os.path.join(src_build_dir, src_dist_info, "RECORD")
        distribution_record = os.path.join(
            distribution_build_dir, distribution_dist_info, "RECORD"
        )

        rec_dist = {"cimpl": [], ".dylibs": []}
        with open(distribution_record, "r") as file:
            dist_lines = file.readlines()
            for i, line in enumerate(dist_lines):
                if line.startswith("confluent_kafka/cimpl"):
                    rec_dist["cimpl"].append(line)

                if line.startswith("confluent_kafka/.dylibs"):
                    rec_dist[".dylibs"].append(line)

        assert rec_dist["cimpl"], "cimpl not found in distribution wheel"

        with open(source_record, "r") as file:
            src_lines = file.readlines()

        src_lines = [  # remove existing cimpl and dylibs
            line
            for line in src_lines
            if not line.startswith("confluent_kafka/cimpl")
            and not line.startswith("confluent_kafka/.dylibs")
        ]

        src_lines = rec_dist["cimpl"] + rec_dist[".dylibs"] + src_lines

        with open(source_record, "w") as file:
            file.writelines(src_lines)

    def patch_wheel_txt(source_build_dir, distribution_build_dir):
        source_dist_info_dir = [
            d for d in os.listdir(source_build_dir) if d.endswith(".dist-info")
        ][0]
        distribution_dist_info_dir = [
            d for d in os.listdir(distribution_build_dir) if d.endswith(".dist-info")
        ][0]

        source_wheel = os.path.join(source_build_dir, source_dist_info_dir, "WHEEL")
        distribution_wheel = os.path.join(
            distribution_build_dir, distribution_dist_info_dir, "WHEEL"
        )

        with open(source_wheel, "r") as file:
            lines = file.readlines()
        with open(distribution_wheel, "r") as file:
            new_lines = file.readlines()

        for i, line in enumerate(lines):
            if line.startswith("Tag:"):
                lines[i] = new_lines[i]

        with open(source_wheel, "w") as file:
            file.writelines(lines)

    def patch_dylibs(source_build_dir, distribution_build_dir):
        src_confluent_kafka = os.path.join(source_build_dir, "confluent_kafka")
        distribution_confluent_kafka = os.path.join(
            distribution_build_dir, "confluent_kafka"
        )

        src_dylibs = os.path.join(src_confluent_kafka, ".dylibs")
        dist_dylibs = os.path.join(distribution_confluent_kafka, ".dylibs")
        if not os.path.exists(dist_dylibs):
            return
        os.makedirs(src_dylibs, exist_ok=True)

        for f in os.listdir(dist_dylibs):
            dist_dylib = os.path.join(dist_dylibs, f)
            src_dylib = os.path.join(src_dylibs, f)
            os.rename(dist_dylib, src_dylib)

    def create_patched_wheel(source_build_dir, distribution_build, prefix) -> str:
        # namever assumes the builds are prepared with the following convention
        # source_build = <name>-<version>-*
        name_version = os.path.basename(distribution_build).split("-")
        name_version = f"{name_version[0]}-{name_version[1]}"
        whl_name = os.path.basename(distribution_build).replace(name_version, prefix)
        patched_whl = os.path.join(
            os.path.dirname(source_build_dir),
            whl_name,
        )

        with zipfile.ZipFile(patched_whl, "w") as zip_ref:
            for root, _, files in os.walk(source_build_dir):
                for file in files:
                    zip_ref.write(
                        os.path.join(root, file),
                        os.path.relpath(os.path.join(root, file), source_build_dir),
                    )

        return patched_whl

    with tempfile.TemporaryDirectory() as temp_dir:
        source_build_dir = os.path.join(temp_dir, "source")
        distribution_build_dir = os.path.join(temp_dir, "distribution")

        os.makedirs(source_build_dir, exist_ok=True)
        os.makedirs(distribution_build_dir, exist_ok=True)

        extract_whl(source_build, source_build_dir)
        extract_whl(distribution_build, distribution_build_dir)

        patch_cimpl(source_build_dir, distribution_build_dir)
        patch_record(source_build_dir, distribution_build_dir)
        patch_wheel_txt(source_build_dir, distribution_build_dir)
        patch_dylibs(source_build_dir, distribution_build_dir)

        patched_whl = create_patched_wheel(source_build_dir, distribution_build, prefix)
        os.rename(patched_whl, os.path.join(dest_dir, os.path.basename(patched_whl)))


def patch(
    source_pkg,
    distribution_pkg_name: str,
    distribution_pkg_version: str,
    dest_dir: str,
    prefix: str,
):
    temp_dir = tempfile.mkdtemp()
    download_dir = os.path.join(temp_dir, "download")
    distribution_build_dir = os.path.join(temp_dir, "build")

    os.makedirs(dest_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(download_dir, exist_ok=True)
    os.makedirs(distribution_build_dir, exist_ok=True)

    print(f"Downloading wheels for {distribution_pkg_name}=={distribution_pkg_version}")
    download_wheels(distribution_pkg_name, distribution_pkg_version, download_dir)
    print("Download complete, patching wheels...")
    build_distributions = [
        os.path.join(download_dir, f)
        for f in os.listdir(download_dir)
        if f.endswith(".whl")
    ]
    print(f"Found {len(build_distributions)} wheels to patch.")
    for i, db in enumerate(build_distributions):
        print(f"\t- Patching {i+1}/{len(build_distributions)} {db}")
        patch_single(source_pkg, db, dest_dir, prefix)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Patch a wheel file.")
    parser.add_argument(
        "--version",
        type=str,
        default="2.4.0",
        help="The version of confluent-kafka that will be used for patching.",
    )
    parser.add_argument(
        "--src", type=str, help="The file path to the superstream wheel file."
    )
    parser.add_argument(
        "--prefix",
        type=str,
        help="The prefix to use for the patched superstream wheel files. The structure should be <name>-<version>",
    )
    parser.add_argument(
        "--output", type=str, help="The directory to save the patched wheel."
    )

    args = parser.parse_args()

    print(f"Source: {args.src}")
    print(f"Package version: {args.version}")
    print(f"Output: {args.output}")
    print(f"Prefix: {args.prefix}")

    patch(args.src, "confluent-kafka", args.version, args.output, args.prefix)
