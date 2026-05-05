from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "verification"
REPORT_JSON = OUT_DIR / "coverage_report.json"
REPORT_MD = OUT_DIR / "coverage_report.md"


def run_command(args: list[str]) -> dict[str, object]:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{ROOT / 'src'};{ROOT}"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {
        "args": args,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-10000:],
        "stderr": proc.stderr[-10000:],
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    built_gui = ROOT / "dist" / "confluence-export-desktop" / "confluence-export-desktop.exe"
    built_installer = ROOT / "dist" / "ConfluenceExportDesktopSetup-0.1.0.exe"
    results = {
        "compileall": run_command([sys.executable, "-m", "compileall", "-q", "src", "tests", "scripts"]),
        "unittest": run_command([sys.executable, "-m", "unittest"]),
        "credential_manager_smoke": run_command([sys.executable, "scripts/credential_manager_smoke.py"]),
        "built_gui_exists": {"returncode": 0 if built_gui.exists() else 127, "exists": built_gui.exists(), "path": str(built_gui)},
        "built_apps_smoke": run_command([sys.executable, "scripts/smoke_built_apps.py"]) if built_gui.exists() else {"returncode": 127, "stderr": "built GUI missing"},
        "built_installer_exists": {"returncode": 0 if built_installer.exists() else 127, "exists": built_installer.exists(), "path": str(built_installer)},
    }
    checks = {
        "cme_only_engine": "SyncEngine uses CME exporter adapter only",
        "cme_only_gui": "GUI exposes CME Job options and no internal backend selector",
        "cme_config_template": "CME 4.1.1 export and connection_config options are present",
        "dry_run_wrapper": "Preview/Dry Run validate config and do not calculate internal page diffs",
        "packaging": "PyInstaller bundles GUI and confluence-markdown-exporter modules; Inno Setup creates installer exe",
    }
    ok = all(int(item.get("returncode", 1)) == 0 for item in results.values())
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": "gui-background-runtime",
        "checks": checks,
        "commands": results,
        "ok": ok,
        "external_remaining": [
            "Live Confluence export still requires real credentials and target page/space/org.",
            "Clean Windows machine without Python still requires external verification.",
        ],
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Verification Coverage Report",
        "",
        f"Generated at: {report['generated_at']}",
        "",
        f"- Mode: {report['mode']}",
        f"- OK: {report['ok']}",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in checks.items())
    lines.extend(["", "## Command Results", ""])
    for name, result in results.items():
        lines.append(f"- {name}: {result.get('returncode')}")
    lines.extend(["", "## External Remaining", ""])
    lines.extend(f"- {item}" for item in report["external_remaining"])
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": ok, "commands": {name: result.get("returncode") for name, result in results.items()}}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
