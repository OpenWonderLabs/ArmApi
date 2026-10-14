"""Change wheel/Conda distribution metadata while preserving every runtime file."""
import base64
import copy
import csv
import hashlib
import io
import json
import posixpath
import subprocess
import tarfile
import zipfile


def promote_package(data, old, new):
    def rename(name):
        return name.replace(f"-{old}.dist-info", f"-{new}.dist-info")

    def metadata(files):
        files = {rename(name): content for name, content in files.items()}
        for name, content in list(files.items()):
            if name.endswith(".dist-info/METADATA"):
                before = f"\nVersion: {old}\n".encode()
                if content.count(before) != 1:
                    raise ValueError("package metadata does not match source version")
                files[name] = content.replace(before, f"\nVersion: {new}\n".encode())
            elif name.endswith(".dist-info/direct_url.json"):
                files[name] = content.replace(f"-{old}-".encode(), f"-{new}-".encode())
        for name in files:
            if not name.endswith(".dist-info/RECORD"):
                continue
            base = posixpath.dirname(posixpath.dirname(name))
            rows = []
            for relative, digest, size in csv.reader(io.StringIO(files[name].decode())):
                relative = rename(relative)
                absolute = posixpath.normpath(posixpath.join(base, relative))
                if absolute == name:
                    digest, size = "", ""
                elif absolute in files:
                    content = files[absolute]
                    digest = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=")
                    size = str(len(content))
                rows.append((relative, digest, size))
            out = io.StringIO(newline="")
            csv.writer(out, lineterminator="\n").writerows(rows)
            files[name] = out.getvalue().encode()
        return files

    def read_tar(compressed):
        raw = subprocess.run(["zstd", "-dq"], input=compressed, capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            members = archive.getmembers()
            files = {m.name: archive.extractfile(m).read() for m in members if m.isfile()}
        return members, files

    def write_tar(members, files):
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w") as archive:
            for member in members:
                item = copy.copy(member)
                item.name, item.linkname = rename(item.name), rename(item.linkname)
                content = files.get(item.name)
                if item.isfile():
                    item.size = len(content)
                archive.addfile(item, io.BytesIO(content) if item.isfile() else None)
        return subprocess.run(["zstd", "-q", "-c", "-9", "-T1"], input=raw.getvalue(), capture_output=True, check=True).stdout

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        files = {i.filename: archive.read(i) for i in entries}
        conda = "metadata.json" in files
        if not conda:
            files = metadata(files)
        else:
            pkg = next(name for name in files if name.startswith("pkg-") and name.endswith(".tar.zst"))
            info = next(name for name in files if name.startswith("info-") and name.endswith(".tar.zst"))
            pkg_members, pkg_files = read_tar(files[pkg])
            pkg_files = metadata(pkg_files)
            info_members, info_files = read_tar(files[info])
            index = json.loads(info_files["info/index.json"])
            if index["version"] != old:
                raise ValueError("Conda source version differs")
            index["version"] = new
            info_files["info/index.json"] = (json.dumps(index, indent=2, sort_keys=True) + "\n").encode()
            paths = json.loads(info_files["info/paths.json"])
            for item in paths["paths"]:
                item["_path"] = rename(item["_path"])
                if item["_path"] in pkg_files:
                    content = pkg_files[item["_path"]]
                    item.update(sha256=hashlib.sha256(content).hexdigest(), size_in_bytes=len(content))
            info_files["info/paths.json"] = (json.dumps(paths, indent=2, sort_keys=True) + "\n").encode()
            info_files["info/files"] = rename(info_files["info/files"].decode()).encode()
            files[pkg] = write_tar(pkg_members, pkg_files)
            files[info] = write_tar(info_members, info_files)
        result = io.BytesIO()
        with zipfile.ZipFile(result, "w") as output:
            for entry in entries:
                item = copy.copy(entry)
                previous = item.filename
                item.filename = (previous.replace(f"-{old}-", f"-{new}-") if conda else rename(previous))
                output.writestr(item, files[previous if conda else item.filename])
        return result.getvalue()
