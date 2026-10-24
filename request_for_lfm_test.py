import os
import json
import re
import javalang
import requests

from parser import parse_java_to_graph

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


def send_request(messages, enable_reasoning=True):
    payload = {
        "model": MODEL,
        "messages": messages,
        "reasoning": {"enabled": enable_reasoning},
    }
    print(f"\n[→] Запрос к {MODEL}...")
    try:
        response = requests.post(API_URL, headers=HEADERS, data=json.dumps(payload), timeout=300)
    except requests.RequestException as e:
        print(f"[!] Сетевая ошибка: {e}")
        return None
    if response.status_code != 200:
        print(f"[!] HTTP {response.status_code}: {response.text}")
        return None
    return response.json()


# ==========================================
# 1. Читаем исходник и парсим граф
# ==========================================
JAVA_FILE = "TestGraph.java"
if not os.path.exists(JAVA_FILE):
    print(f"[!] Файл {JAVA_FILE} не найден.")
    exit(1)

with open(JAVA_FILE, "r", encoding="utf-8") as f:
    java_code = f.read()

print("=" * 60)
print("ПАРСИНГ JAVA-КОДА")
print("=" * 60)

graph_json = parse_java_to_graph(java_code)
if "error" in graph_json:
    print("Ошибка парсинга:", graph_json["error"])
    exit(1)

print(f"Узлов: {len(graph_json['nodes'])}, рёбер: {len(graph_json['edges'])}")


# ==========================================
# 2. Запрос к модели — получаем граф с optimized_code
# ==========================================
system_prompt = """Ты — эксперт по оптимизации Java-кода.

Тебе дан:
1. Исходный код на Java.
2. Граф структуры этого кода в формате JSON (узлы — классы и методы; рёбра — связи "contains" и "calls").

Задача:
1. Проанализировать каждый метод.
2. Найти реальные оптимизации по времени (loop fission, вынос инвариантов, объединение проходов по массиву и т.п.).
3. НЕ удалять и НЕ переименовывать классы и методы. Связи contains и calls должны остаться.
4. Для каждого метода в узле графа:
   - Если метод изменён — добавь поле "optimized_code" с ПОЛНЫМ текстом нового тела метода, включая сигнатуру, открывающую и закрывающую фигурные скобки. Например: "public void processLargeArray(int[] data) { ... }".
   - Если метод НЕ изменён — не добавляй "optimized_code" вообще (или оставь его пустым).
5. Верни ОБНОВЛЁННЫЙ граф в JSON с ключами "nodes" и "edges", тем же форматом id/label/group/shape/color/from/to/arrows.

ВАЖНО: "optimized_code" должен содержать ровно один метод — тот, к которому относится узел. Не включай в него другие методы или классы.

Верни ТОЛЬКО валидный JSON без markdown-обёртки."""

user_prompt = f"""Исходный код Java:
{java_code}

Текущий граф (JSON):
{json.dumps(graph_json, ensure_ascii=False)}

Оптимизируй методы и верни граф с полем optimized_code у изменённых методов."""

print("\n" + "=" * 60)
print("ЗАПРОС К МОДЕЛИ")
print("=" * 60)

response = send_request([
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": user_prompt},
])
if not response:
    exit(1)

answer = response["choices"][0]["message"]["content"]

# Извлекаем JSON
clean = answer.strip()
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

try:
    optimized_graph = json.loads(clean)
except json.JSONDecodeError as e:
    print(f"[!] Невалидный JSON: {e}")
    with open("raw_answer.txt", "w", encoding="utf-8") as f:
        f.write(answer)
    exit(1)


# ==========================================
# 3. Собираем карту "полное_имя_метода → optimized_code"
# ==========================================
optimized_methods = {}  # {"TestGraph.processLargeArray": "public void processLargeArray(...) { ... }"}

for node in optimized_graph.get("nodes", []):
    if node.get("group") == "method":
        opt_code = node.get("optimized_code", "").strip()
        if opt_code:
            # label имеет вид "TestGraph.processLargeArray()"
            label = node.get("label", "")
            # Убираем "()" в конце, оставляем "TestGraph.processLargeArray"
            method_key = label.rstrip("()")
            optimized_methods[method_key] = opt_code

print(f"\nМетодов с optimized_code: {len(optimized_methods)}")
for k in optimized_methods:
    print(f"  - {k}")


# ==========================================
# 4. Реконструкция файла: точечная замена методов
# ==========================================
# Используем javalang, чтобы найти позиции методов в исходном тексте.
# javalang не даёт offset, но мы можем вычислить по тексту.

def find_method_ranges(source: str) -> dict:
    """
    Возвращает { "ClassName.methodName": (start, end) }, где start/end — позиции
    текста метода в source (включая сигнатуру и закрывающую скобку).
    """
    tree = javalang.parse.parse(source)

    ranges = {}

    for path, class_decl in tree.filter(javalang.tree.ClassDeclaration):
        class_name = class_decl.name
        for method in class_decl.methods:
            method_name = method.name
            key = f"{class_name}.{method_name}"

            # Ищем в тексте: имя метода + "("
            # Простое, но надёжное приближение: от первой встречи "имя_метода" + "("
            # до соответствующей закрывающей "}" (с балансом скобок)
            pattern = re.compile(r'\b' + re.escape(method_name) + r'\s*\(')
            match = pattern.search(source)
            if not match:
                continue

            # Идём назад до начала строки (чтобы захватить модификаторы и тип возврата)
            start = source.rfind("\n", 0, match.start()) + 1
            # Идём вперёд до "}" с балансом
            depth = 0
            pos = match.end()
            # Сначала найдём открывающую "{" тела метода
            while pos < len(source) and source[pos] != "{":
                pos += 1
            if pos >= len(source):
                continue
            # Теперь считаем баланс
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


method_ranges = find_method_ranges(java_code)
print(f"\nНайдено методов в исходнике: {len(method_ranges)}")
for k in method_ranges:
    print(f"  - {k}")


# ==========================================
# 5. Применяем замены (с конца, чтобы не сбить смещения)
# ==========================================
replacements = []
for method_key, new_code in optimized_methods.items():
    if method_key in method_ranges:
        start, end = method_ranges[method_key]
        replacements.append((start, end, new_code))
    else:
        print(f"[!] Не нашли позицию метода {method_key} в исходнике — пропускаем.")

# Сортируем по убыванию start, чтобы замены не сдвигали позиции
replacements.sort(key=lambda x: x[0], reverse=True)

new_source = java_code
for start, end, new_code in replacements:
    new_source = new_source[:start] + new_code + new_source[end:]


# ==========================================
# 6. Сохраняем и валидируем
# ==========================================
OUTPUT_FILE = "TestGraph_optimized.java"
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(new_source)

print("\n" + "=" * 60)
print(f"НОВЫЙ JAVA-КОД (сохранён в {OUTPUT_FILE})")
print("=" * 60)
print(new_source)


# Валидация: парсим новый код
new_graph = parse_java_to_graph(new_source)
if "error" in new_graph:
    print(f"\n[!] Новый код НЕ парсится: {new_graph['error']}")
    exit(1)

old_classes = sum(1 for n in graph_json["nodes"] if n.get("group") == "class")
old_methods = sum(1 for n in graph_json["nodes"] if n.get("group") == "method")
new_classes = sum(1 for n in new_graph["nodes"] if n.get("group") == "class")
new_methods = sum(1 for n in new_graph["nodes"] if n.get("group") == "method")

print("\n" + "=" * 60)
print("ВАЛИДАЦИЯ")
print("=" * 60)
print(f"[✓] Парсинг успешен: узлов {len(new_graph['nodes'])}, рёбер {len(new_graph['edges'])}")
print(f"    Классов: было {old_classes}, стало {new_classes}")
print(f"    Методов: было {old_methods}, стало {new_methods}")

if old_classes == new_classes and old_methods == new_methods:
    print("[✓] Структура сохранена.")
else:
    print("[!] Структура изменилась — проверьте вручную.")