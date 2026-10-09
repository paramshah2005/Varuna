import json
from pathlib import Path
from email.parser import BytesParser

root = Path(__file__).resolve().parents[1]
notices = root / "frontend/public/third-party"
notices.mkdir(parents=True, exist_ok=True)
for name, source in {
    "DM-Sans-LICENSE.txt": root / "frontend/node_modules/@fontsource-variable/dm-sans/LICENSE",
    "Manrope-LICENSE.txt": root / "frontend/node_modules/@fontsource-variable/manrope/LICENSE",
    "shadcn-LICENSE.txt": root / "docs/third-party/shadcn-LICENSE.txt",
}.items():
    (notices / name).write_text(source.read_text(encoding="utf-8").rstrip() + "\n", encoding="utf-8")
lines = [
    "# Third-party credits",
    "",
    "All runtime and test dependencies retain their upstream licences in installed distributions. Preserve licence notices in bundled source/binaries. Versions below are drawn from the installed dependency metadata, not inferred. No external dataset or stock imagery is used. Synthetic fixtures and ordinary low-poly geometry were created for AquaAgent.",
    "",
    "The Button component is adapted from the official shadcn/ui new-york-v4 registry (MIT); its licence is preserved in third-party/shadcn-LICENSE.txt. Radix, class-variance-authority, clsx and tailwind-merge support the UI primitives. Registry source: https://ui.shadcn.com/r/styles/new-york-v4/button.json . No external WaterWise HTML or dashboard reference was available. Lucide supplies the interface icons (ISC). DM Sans and Manrope variable fonts are distributed locally through Fontsource and retain the SIL Open Font License. Font and shadcn licence notices also ship in frontend/public/third-party and built frontend/third-party assets. The browser does not depend on Google Fonts requests.",
    "",
    "Environmental guidance is adapted in brief from [CDC heat prevention guidance](https://www.cdc.gov/extreme-heat/prevention/), checked on 9 October 2026. It provides environmental precautions only, not symptom triage or diagnosis. AWS and Groq documentation informed API integrations; their example code was not copied wholesale.",
    "",
    "Codex, an OpenAI AI coding tool, assisted source generation, tests, debugging, design and documentation. Original project licensing remains the owner's decision.",
    "",
    "## JavaScript dependencies",
    "",
    "| Package | Version | Licence |",
    "|---|---|---|",
]
seen = set()
for project in ["frontend", "infrastructure"]:
    lock = json.loads((root / project / "package-lock.json").read_text())
    for key in sorted(lock["packages"]):
        if not key:
            continue
        file = root / project / key / "package.json"
        if not file.exists():
            continue
        pkg = json.loads(file.read_text(encoding="utf-8"))
        name, version = pkg.get("name", key), pkg.get("version", "unknown")
        if (name, version) in seen:
            continue
        seen.add((name, version))
        license = pkg.get("license", "See upstream licence notices")
        if isinstance(license, dict):
            license = license.get("type", str(license))
        lines.append(f"| {name} | {version} | {str(license).replace('|', '/')} |")
lines.extend(
    [
        "",
        "## Python dependencies",
        "",
        "| Package | Version | Licence metadata |",
        "|---|---|---|",
    ]
)
for file in sorted((root / ".venv/Lib/site-packages").glob("*.dist-info/METADATA")):
    metadata = BytesParser().parsebytes(file.read_bytes())
    name, version = metadata.get("Name"), metadata.get("Version")
    license = (
        metadata.get("License-Expression")
        or next(
            (
                c.split(" :: ")[-1]
                for c in metadata.get_all("Classifier", [])
                if c.startswith("License ::")
            ),
            None,
        )
        or metadata.get("License", "See distribution licence notices")
    )
    license = " ".join(license.split())
    if len(license) > 90:
        license = "See distribution licence text"
    lines.append(f"| {name} | {version} | {license.replace('|', '/')} |")
(root / "docs/THIRD_PARTY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(
    f"Recorded {len(seen)} JavaScript distributions and installed Python licence metadata"
)
