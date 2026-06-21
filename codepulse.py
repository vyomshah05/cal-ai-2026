"""CodePulse — codebase health scanner with a rich terminal dashboard."""
from __future__ import annotations

import ast
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from rich.bar import Bar
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

console = Console()

# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def _scan_file(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    lines = source.splitlines()
    total = len(lines)
    blank = sum(1 for l in lines if not l.strip())
    comment = sum(1 for l in lines if l.strip().startswith("#"))
    code = total - blank - comment

    imports: list[str] = []
    functions = 0
    classes = 0
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module.split(".")[0])
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                functions += 1
            elif isinstance(node, ast.ClassDef):
                classes += 1
    except SyntaxError:
        # Fallback: regex import extraction
        for m in re.finditer(r"^(?:import|from)\s+([a-zA-Z0-9_]+)", source, re.M):
            imports.append(m.group(1))

    return {
        "path": str(path),
        "total": total,
        "blank": blank,
        "comment": comment,
        "code": code,
        "imports": imports,
        "functions": functions,
        "classes": classes,
    }


def scan(root: Path) -> dict:
    files_data: list[dict] = []
    py_files = list(root.rglob("*.py"))
    py_files = [f for f in py_files if ".venv" not in f.parts
                and "__pycache__" not in f.parts
                and ".git" not in f.parts]

    all_imports: list[str] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]Scanning[/] {task.description}"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Python files...", total=len(py_files))
        for f in py_files:
            progress.update(task, description=f.name)
            data = _scan_file(f)
            if data:
                files_data.append(data)
                all_imports.extend(data["imports"])
            progress.advance(task)

    total_lines = sum(d["total"] for d in files_data)
    blank_lines = sum(d["blank"] for d in files_data)
    comment_lines = sum(d["comment"] for d in files_data)
    code_lines = sum(d["code"] for d in files_data)
    total_functions = sum(d["functions"] for d in files_data)
    total_classes = sum(d["classes"] for d in files_data)
    import_counts = Counter(all_imports).most_common(10)

    return {
        "root": str(root),
        "scanned_at": datetime.now().isoformat(),
        "file_count": len(files_data),
        "total_lines": total_lines,
        "blank_lines": blank_lines,
        "comment_lines": comment_lines,
        "code_lines": code_lines,
        "total_functions": total_functions,
        "total_classes": total_classes,
        "top_imports": import_counts,
        "files": sorted(files_data, key=lambda d: d["total"], reverse=True),
    }


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _metric_panel(label: str, value: str, color: str) -> Panel:
    body = Text(value, style=f"bold {color}", justify="center")
    return Panel(body, title=f"[dim]{label}[/]", border_style=color, padding=(0, 2))


def display(result: dict) -> None:
    project_name = Path(result["root"]).name

    console.print()
    console.rule(
        f"[bold white] CodePulse [/][bold cyan]{project_name}[/]"
        f"  [dim]{result['scanned_at'][:19]}[/]",
        style="cyan",
    )
    console.print()

    # --- Summary metrics ---
    panels = [
        _metric_panel("Python Files", str(result["file_count"]), "cyan"),
        _metric_panel("Total Lines", f"{result['total_lines']:,}", "green"),
        _metric_panel("Code Lines", f"{result['code_lines']:,}", "bright_green"),
        _metric_panel("Comments", f"{result['comment_lines']:,}", "yellow"),
        _metric_panel("Blank Lines", f"{result['blank_lines']:,}", "dim white"),
        _metric_panel("Functions", f"{result['total_functions']:,}", "magenta"),
        _metric_panel("Classes", f"{result['total_classes']:,}", "bright_magenta"),
    ]
    console.print(Columns(panels, equal=True, expand=True))
    console.print()

    # --- Top 5 files by line count ---
    file_table = Table(
        title="[bold]Largest Files[/]",
        border_style="dim",
        header_style="bold cyan",
        show_lines=False,
    )
    file_table.add_column("File", style="white", no_wrap=True)
    file_table.add_column("Total", justify="right", style="green")
    file_table.add_column("Code", justify="right", style="bright_green")
    file_table.add_column("Blank", justify="right", style="dim")
    file_table.add_column("Funcs", justify="right", style="magenta")
    file_table.add_column("Classes", justify="right", style="bright_magenta")

    for d in result["files"][:5]:
        rel = str(Path(d["path"]).relative_to(result["root"]))
        file_table.add_row(
            rel,
            str(d["total"]),
            str(d["code"]),
            str(d["blank"]),
            str(d["functions"]),
            str(d["classes"]),
        )
    console.print(file_table)
    console.print()

    # --- Import bar chart ---
    if result["top_imports"]:
        console.print(Panel(
            "[bold]Top Imported Packages[/]",
            border_style="cyan",
            expand=False,
        ))
        max_count = result["top_imports"][0][1]
        for pkg, count in result["top_imports"]:
            bar = Bar(size=max_count, begin=0, end=count, color="cyan")
            label = f"  [white]{pkg:<20}[/] [dim]{count:>4}x[/]  "
            console.print(label, bar)
        console.print()

    # --- Code ratio ---
    if result["total_lines"] > 0:
        ratio = result["code_lines"] / result["total_lines"] * 100
        color = "green" if ratio > 60 else "yellow" if ratio > 40 else "red"
        console.print(
            f"  [dim]Code ratio:[/] [{color}]{ratio:.1f}%[/] of lines are active code"
        )
        console.print()

    console.rule(style="dim")
    console.print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    if not root.exists() or not root.is_dir():
        console.print(f"[red]Error:[/] {root} is not a valid directory")
        sys.exit(1)

    console.print(f"\n[bold cyan]CodePulse[/] scanning [dim]{root}[/]...\n")
    t0 = time.perf_counter()
    result = scan(root)
    elapsed = time.perf_counter() - t0

    display(result)

    # Export JSON
    report_path = Path("codepulse_report.json")
    report_path.write_text(json.dumps(result, indent=2))
    console.print(
        f"  [dim]Scanned {result['file_count']} files in {elapsed:.2f}s"
        f" → [/][cyan]{report_path}[/]\n"
    )


if __name__ == "__main__":
    main()
