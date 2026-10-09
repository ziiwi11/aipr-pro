"""Build a relocatable Windows runtime from verified official binary archives.

This prepares files only on non-Windows hosts; it does not claim a Windows
execution test. Run scripts/windows-runtime-smoke.py on the target Windows PC.
"""
import hashlib
import io
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
SHA256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"


def download(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def extract(archive, target):
    with zipfile.ZipFile(io.BytesIO(archive)) as package:
        for entry in package.infolist():
            name = pathlib.PurePosixPath(entry.filename)
            if name.is_absolute() or ".." in name.parts or "\\" in entry.filename:
                raise ValueError("Unsafe archive member")
        package.extractall(target)


def main():
    destination = ROOT / "runtime/windows-x64/python"
    if destination.exists():
        raise SystemExit("Existing runtime retained. Move it aside before rebuilding.")
    with tempfile.TemporaryDirectory(prefix="qianxun-windows-runtime-") as folder:
        temp = pathlib.Path(folder)
        staging, wheels = temp / "python", temp / "wheels"
        staging.mkdir()
        wheels.mkdir()
        archive = download(URL)
        if hashlib.sha256(archive).hexdigest() != SHA256:
            raise ValueError("Official CPython archive SHA256 mismatch")
        extract(archive, staging)
        subprocess.run([sys.executable, "-m", "pip", "download", "--index-url",
                        "https://pypi.org/simple", "--only-binary=:all:", "--platform",
                        "win_amd64", "--python-version", "312", "--implementation", "cp",
                        "--abi", "cp312", "--dest", str(wheels), "-r",
                        str(ROOT / "requirements-windows.txt")], check=True)
        packages = []
        site = staging / "Lib/site-packages"
        site.mkdir(parents=True)
        for wheel in sorted(wheels.glob("*.whl")):
            project, version = wheel.name.split("-")[:2]
            metadata = json.loads(download(f"https://pypi.org/pypi/{project}/{version}/json"))
            official = next(item for item in metadata["urls"] if item["filename"] == wheel.name)
            data = wheel.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if digest != official["digests"]["sha256"]:
                raise ValueError(f"PyPI SHA256 mismatch: {wheel.name}")
            extract(data, site)
            packages.append({"name": project, "version": version,
                             "filename": wheel.name, "sha256": digest,
                             "source": official["url"]})
        # The app uses its embedded Chromium over CDP, not a browser downloaded
        # by Playwright. The Windows Playwright wheel includes its own node.exe.
        (staging / "python312._pth").write_text(
            "python312.zip\n.\nLib/site-packages\n../../../backend\nimport site\n", encoding="utf-8")
        required = ["python.exe", "python312.dll", "Lib/site-packages/playwright/driver/node.exe",
                    "Lib/site-packages/openpyxl/__init__.py", "Lib/site-packages/pypdf/__init__.py"]
        for name in required:
            if not (staging / name).is_file():
                raise ValueError(f"Missing runtime file: {name}")
        manifest = {"schema": "qianxun-windows-runtime-v1", "architecture": "win32/x64",
                    "pythonVersion": "3.12.10", "pythonSource": URL,
                    "pythonArchiveSha256": SHA256, "packages": packages,
                    "executionVerified": False,
                    "files": [{"path": str(file.relative_to(staging)).replace("\\", "/"),
                               "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}
                              for file in sorted(staging.rglob("*")) if file.is_file()]}
        shutil.copytree(staging, destination)
        (destination.parent / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Prepared verified Windows files: {len(manifest['files'])}; Windows execution remains unverified")


if __name__ == "__main__":
    main()
