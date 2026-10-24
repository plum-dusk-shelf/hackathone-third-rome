import os
import json
import re
import requests
import javalang
import dotenv



dotenv.load_dotenv()
# ==========================================
# Настройки OpenRouter
# ==========================================
API_KEY = os.environ.get("OPENROUTER_API_KEY", "<OPENROUTER_API_KEY>")
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "http://localhost",
    "X-Title": "IDE Graph Optimizer",
}


def _send_request(messages, enable_reasoning=True, timeout=300):
    payload = {
        "model": MODEL,
        "messages": messages,
        "reasoning": {"enabled": enable_reasoning},
    }
    try:
        response = requests.post(API_URL, headers=HEADERS, data=json.dumps(payload), timeout=timeout)
    except requests.RequestException as e:
        return None, f"Сетевая ошибка: {e}"

    if response.status_code != 200:
        return None, f"HTTP {response.status_code}: {response.text}"

    return response.json(), None


def _extract_json(text: str):
    clean = text.strip()

    if clean.startswith("```"):
        lines = clean.split("\n")
        if len(lines) > 2:
            clean = "\n".join(lines[1:])
        if clean.rstrip().endswith("```"):
            clean = clean.rstrip()[:-3]
    clean = clean.strip()

    if not clean.startswith("{"):
        s, e = clean.find("{"), clean.rfind("}")
        if s != -1 and e != -1:
            clean = clean[s:e+1]

    return json.loads(clean)


def _find_method_ranges(source: str) -> dict:
    tree = javalang.parse.parse(source)
    ranges = {}

    for _, class_decl in tree.filter(javalang.tree.ClassDeclaration):
        class_name = class_decl.name
        for method in class_decl.methods:
            method_name = method.name
            key = f"{class_name}.{method_name}"

            pattern = re.compile(r'\b' + re.escape(method_name) + r'\s*\(')
            match = pattern.search(source)
            if not match:
                continue

            start = source.rfind("\n", 0, match.start()) + 1

            pos = match.end()
            while pos < len(source) and source[pos] != "{":
                pos += 1
            if pos >= len(source):
                continue

            depth = 0
            end = pos
            while end < len(source):
                ch = source[end]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end += 1
                        break
                end += 1

            ranges[key] = (start, end)

    return ranges


def optimize_java_code(java_code: str, graph_json: dict, enable_reasoning: bool = True, log=None) -> dict:
    """
    Главная функция. Отправляет код и граф в LLM, получает обновлённый граф,
    применяет точечные замены и возвращает результат.

    Параметр log — необязательная функция для логирования (например, из test_main.py).
    """
    if log is None:
        log = lambda msg: None

    system_prompt = """Ты — эксперт по оптимизации Java-кода.

Тебе дан:
1. Исходный код на Java.
2. Граф структуры этого кода в формате JSON (узлы — классы и методы; рёбра — связи "contains" и "calls").

Задача:
1. Проанализировать каждый метод.
2. Найти реальные оптимизации по времени (loop fission, вынос инвариантов, объединение/разделение проходов по массиву, замена индексов на for-each и т.п.).
3. НЕ удалять и НЕ переименовывать классы и методы. Связи contains и calls должны остаться.
4. Для каждого метода в узле графа:
   - Если метод изменён — добавь поле "optimized_code" с ПОЛНЫМ текстом нового метода, включая модификаторы, сигнатуру, тело в фигурных скобках. Например: "public void processLargeArray(int[] data) { ... }".
   - Если метод НЕ изменён — НЕ добавляй "optimized_code".
5. Дополнительно в каждый узел метода добавь поле "note" (1 короткое предложение): что изменено, либо "Уже оптимально".
6. Верни ОБНОВЛЁННЫЙ граф в JSON с ключами "nodes" и "edges", тем же форматом id/label/group/shape/color/from/to/arrows.

ВАЖНО: "optimized_code" содержит ровно один метод — тот, к которому относится узел. Не включай туда другие методы или классы.

Верни ТОЛЬКО валидный JSON без markdown-обёртки."""

    user_prompt = f"""Исходный код Java:
{java_code}

Текущий граф (JSON):
{json.dumps(graph_json, ensure_ascii=False)}

Оптимизируй методы. В изменённых узлах добавь "optimized_code" и "note", в остальных — только "note"."""

    log("[LLM] Отправляем запрос в OpenRouter...")
    response, error = _send_request(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        enable_reasoning=enable_reasoning,
    )

    if error:
        log(f"[LLM] Ошибка: {error}")
        return {"success": False, "error": error, "new_code": java_code, "optimized_graph": graph_json, "changed_methods": []}

    try:
        answer = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        log("[LLM] Не удалось извлечь content из ответа")
        return {"success": False, "error": "Не удалось извлечь content из ответа", "new_code": java_code, "optimized_graph": graph_json, "changed_methods": []}

    log("[LLM] Получили ответ, извлекаем JSON...")
    try:
        optimized_graph = _extract_json(answer)
    except json.JSONDecodeError as e:
        log(f"[LLM] Невалидный JSON: {e}")
        return {"success": False, "error": f"Невалидный JSON: {e}", "new_code": java_code, "optimized_graph": graph_json, "changed_methods": []}

    for node in optimized_graph.get("nodes", []):
        if node.get("group") == "method":
            node.setdefault("note", "")

    optimized_methods = {}
    for node in optimized_graph.get("nodes", []):
        if node.get("group") == "method":
            opt_code = (node.get("optimized_code") or "").strip()
            if opt_code:
                label = node.get("label", "")
                method_key = label.rstrip("()")
                optimized_methods[method_key] = opt_code

    log(f"[LLM] Модель изменила методов: {len(optimized_methods)}")

    if not optimized_methods:
        return {
            "success": True,
            "error": None,
            "new_code": java_code,
            "optimized_graph": optimized_graph,
            "changed_methods": [],
        }

    try:
        method_ranges = _find_method_ranges(java_code)
    except Exception as e:
        log(f"[LLM] Ошибка парсинга исходника: {e}")
        return {"success": False, "error": f"Ошибка парсинга исходника: {e}", "new_code": java_code, "optimized_graph": optimized_graph, "changed_methods": []}

    replacements = []
    for method_key, new_code in optimized_methods.items():
        if method_key in method_ranges:
            start, end = method_ranges[method_key]
            replacements.append((start, end, new_code, method_key))
        else:
            log(f"[LLM] Не нашли позицию метода {method_key} в исходнике — пропускаем.")

    replacements.sort(key=lambda x: x[0], reverse=True)

    new_source = java_code
    changed_methods = []
    for start, end, new_code, method_key in replacements:
        new_source = new_source[:start] + new_code + new_source[end:]
        changed_methods.append(method_key)

    log(f"[LLM] Применено замен: {len(changed_methods)}")

    return {
        "success": True,
        "error": None,
        "new_code": new_source,
        "optimized_graph": optimized_graph,
        "changed_methods": changed_methods,
    }