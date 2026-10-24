"""examplee.py — короткий пример использования run_java_string_to_json.

Точка останова задаётся ИНДЕКСОМ СТРОКИ (1-based) в переданном Java-исходнике.

Запуск:
    python examplee.py
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from example2 import run_java_string_to_json


JAVA = """
public class Main {
    public static void main(String[] args) {
        int x = 41;
        int y = x + 1;
        String s = "hi";
        System.out.println(s + y);
    }
}
"""

# 1-based номер строки в JAVA, где встать отладчиком.
# Считаем по splitlines() от начала строки (пустая первая строка → строка 1).
# В этом примере:
#   1: (пустая)
#   2: public class Main {
#   3:     public static void main(String[] args) {
#   4:         int x = 41;
#   5:         int y = x + 1;        ← сюда
#   6:         String s = "hi";
#   7:         System.out.println(s + y);
#   8:     }
#   9: }
STOP_LINE = 5


async def main() -> None:
    path = await run_java_string_to_json(
        root=Path("workspace"),
        source=JAVA,
        stop_line=STOP_LINE,   # ← индекс строки, не маркер
        out="vars.json",
    )
    print(path)

    data = json.loads(Path(path).read_text("utf-8"))
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())