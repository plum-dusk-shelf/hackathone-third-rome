
import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
JAR_PATH = PROJECT_ROOT / "target" / "java-analyzer-1.0.0.jar"


def analyze_java(*source_files: str | Path) -> dict:
    if not JAR_PATH.exists():
        raise FileNotFoundError(
            f"Не найден анализатор: {JAR_PATH}. "
            "Сначала соберите проект командой mvn package."
        )

    files = [
        str(Path(path).resolve())
        for path in source_files
    ]

    if not files:
        raise ValueError("Передайте хотя бы один Java-файл.")

    for path in files:
        if not Path(path).is_file():
            raise FileNotFoundError(path)

    result = subprocess.run(
        ["java", "-jar", str(JAR_PATH), *files],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if result.returncode == 2:
        raise RuntimeError(
            result.stderr or "Не удалось запустить анализатор."
        )

    try:
        graph = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Анализатор не вернул корректный JSON.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        ) from exc

    graph["exit_code"] = result.returncode
    return graph


if __name__ == "__main__":
    graph = analyze_java(
        PROJECT_ROOT / "samples" / "MainExample.java",
        PROJECT_ROOT / "samples" / "Helper.java",
    )

    print(f"Узлов: {len(graph['nodes'])}")
    print(f"Связей: {len(graph['edges'])}")
    print(f"Диагностик: {len(graph['diagnostics'])}")

    Path("graph.json").write_text(
        json.dumps(graph, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

