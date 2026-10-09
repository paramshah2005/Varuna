from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
target = root / "backend" / "package"
subprocess.run(
    [
        "uv",
        "--cache-dir",
        str(root / ".local" / "uv-cache"),
        "pip",
        "install",
        "--target",
        str(target),
        "--python-platform",
        "x86_64-manylinux_2_28",
        "--python-version",
        "3.12",
        "--only-binary",
        ":all:",
        "-r",
        str(root / "backend" / "requirements.txt"),
    ],
    check=True,
)
for name in ["api", "simulation", "agents", "workflows"]:
    shutil.copytree(
        root / "backend" / name,
        target / "backend" / name,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
(target / "backend").mkdir(exist_ok=True)
shutil.copyfile(root / "backend" / "__init__.py", target / "backend" / "__init__.py")
print("Packaged Python 3.12 Linux Lambda code and dependencies")
