import os
import sys
import json
import time
import base64
import threading
import uvicorn
import multiprocessing
import re
import socket
from urllib.error import URLError
from urllib.request import urlopen
from pathlib import Path
from webui import webui

# Импортируем FastAPI приложение и парсер
from fastapi_server import app as fastapi_app
from parser import parse_java_to_graph
from graph_optimizer_llm import optimize_java_code

PROJECT_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", PROJECT_DIR))
DEBUG_WORKSPACE = Path(
    os.environ.get("WORKSPACE", PROJECT_DIR)
).resolve()
os.environ.setdefault("WORKSPACE", str(DEBUG_WORKSPACE))

from server.main import app as java_debug_app

fastapi_app.mount("/debug", java_debug_app)

win = None
IS_WIN = (os.name == "nt")
SERVER_PROC = None


def _debug_server_is_running():
    try:
        with urlopen("http://127.0.0.1:8086/debug/api/files", timeout=1) as response:
            return response.status == 200 and isinstance(json.load(response), list)
    except (OSError, URLError, ValueError):
        return False


def _port_is_in_use():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", 8086)) == 0


def resolve_project_path(path: str) -> Path:
    file_path = Path(path)
    return file_path if file_path.is_absolute() else PROJECT_DIR / file_path

def log(message: str):
    """Печатает в терминал и отправляет в панель «Консоль» в IDE."""
    print(message, flush=True)
    if win and win.is_shown():
        safe = (message.replace("\\", "\\\\").replace("'", "\\'")
                       .replace('"', '\\"').replace("\n", "\\n"))
        win.run(f"appendLog('{safe}');")

def get_files(_event):
    base_dir = str(PROJECT_DIR)
    ignore_dirs = {'.git', '__pycache__', 'node_modules', 'venv', '.venv', '.jdtls-data', '.vscode', 'build', 'dist'}
    
    def scan_dir(current_path, rel_path=""):
        children = []
        try:
            entries = sorted(os.listdir(current_path), key=lambda x: (not os.path.isdir(os.path.join(current_path, x)), x.lower()))
            for entry in entries:
                full_path = os.path.join(current_path, entry)
                rel_entry_path = os.path.join(rel_path, entry) if rel_path else entry
                
                if os.path.isdir(full_path):
                    if entry in ignore_dirs:
                        continue
                    sub_children = scan_dir(full_path, rel_entry_path)
                    children.append({
                        "name": entry,
                        "path": rel_entry_path,
                        "type": "dir",
                        "children": sub_children
                    })
                else:
                    children.append({
                        "name": entry,
                        "path": rel_entry_path,
                        "type": "file"
                    })
        except PermissionError:
            pass
        return children

    try:
        tree = scan_dir(base_dir)
        json_data = json.dumps(tree)
        b64_str = base64.b64encode(json_data.encode('utf-8')).decode('ascii')
        
        if win and win.is_shown():
            win.run(f"onFilesLoaded('{b64_str}');")
    except Exception as ex:
        log(f"[get_files] Ошибка: {ex}")
        if win and win.is_shown():
            b64_err = base64.b64encode(json.dumps({'error': str(ex)}).encode('utf-8')).decode('ascii')
            win.run(f"onFilesLoaded('{b64_err}');")

def read_file(e):
    try:
        if hasattr(e, 'get_string'):
            safe_path_b64 = e.get_string()
        else:
            safe_path_b64 = str(e)

        path = str(resolve_project_path(base64.b64decode(safe_path_b64).decode('utf-8')))
        log(f"[read_file] Читаем: {path}")

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        log(f"[read_file] Прочитано {len(content)} символов")
        json_data = json.dumps({'content': content, 'path': path})
        b64_str = base64.b64encode(json_data.encode('utf-8')).decode('ascii')
        
        if win and win.is_shown():
            win.run(f"onFileContentLoaded('{b64_str}');")
    except Exception as ex:
        log(f"[read_file] Ошибка: {ex}")
        b64_err = base64.b64encode(json.dumps({'error': str(ex)}).encode('utf-8')).decode('ascii')
        if win and win.is_shown():
            win.run(f"onFileContentLoaded('{b64_err}');")

def save_file(e):
    try:
        if hasattr(e, 'get_string'):
            data_str = e.get_string()
        else:
            data_str = str(e)
        
        data = json.loads(data_str)
        path = data.get('path', '')
        content = data.get('content', '')

        if not path:
            raise ValueError("Путь не передан")

        path = str(resolve_project_path(path))
        log(f"[save_file] Сохраняем: {path}")
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        log(f"[save_file] Успешно сохранено")
        resp = json.dumps({'status': 'ok', 'path': path})
        b64_str = base64.b64encode(resp.encode('utf-8')).decode('ascii')
        
        if win and win.is_shown():
            win.run(f"onFileSaved('{b64_str}');")
    except Exception as ex:
        log(f"[save_file] Ошибка: {ex}")
        b64_err = base64.b64encode(json.dumps({'error': str(ex)}).encode('utf-8')).decode('ascii')
        if win and win.is_shown():
            win.run(f"onFileSaved('{b64_err}');")

def parse_java(e):
    log("[parse_java] Парсим Java-код...")
    try:
        if hasattr(e, 'get_string'):
            b64_code = e.get_string()
        else:
            b64_code = str(e)

        java_code = base64.b64decode(b64_code).decode('utf-8')
        graph_data = parse_java_to_graph(java_code)

        if "error" in graph_data:
            log(f"[parse_java] Ошибка: {graph_data['error']}")
            raise ValueError(graph_data["error"])

        log(f"[parse_java] Успех: {len(graph_data['nodes'])} узлов, {len(graph_data['edges'])} рёбер")
        json_data = json.dumps(graph_data)
        b64_str = base64.b64encode(json_data.encode('utf-8')).decode('ascii')

        if win and win.is_shown():
            win.run(f"onGraphLoaded('{b64_str}');")

    except Exception as ex:
        log(f"[parse_java] Исключение: {ex}")
        b64_err = base64.b64encode(json.dumps({'error': str(ex)}).encode('utf-8')).decode('ascii')
        if win and win.is_shown():
            win.run(f"onGraphLoaded('{b64_err}');")

def optimize_graph(e):
    log("[optimize_graph] Получен запрос на оптимизацию")
    try:
        if hasattr(e, 'get_string'):
            payload_b64 = e.get_string()
        else:
            payload_b64 = str(e)

        payload = json.loads(base64.b64decode(payload_b64).decode('utf-8'))
        java_code = payload.get("code", "")
        graph_json = payload.get("graph", {})

        if not java_code.strip():
            raise ValueError("Код пуст")
        if not graph_json:
            raise ValueError("Граф не передан")

        log(f"[optimize_graph] Код: {len(java_code)} символов, граф: {len(graph_json.get('nodes', []))} узлов")
        log("[optimize_graph] Отправляю запрос в OpenRouter...")

        result = optimize_java_code(java_code, graph_json, enable_reasoning=True, log=log)

        if not result["success"]:
            log(f"[optimize_graph] Ошибка LLM: {result['error']}")
            raise ValueError(result["error"] or "Неизвестная ошибка оптимизации")

        log(f"[optimize_graph] Успех. Изменено методов: {len(result['changed_methods'])}")

        response_data = {
            "new_code": result["new_code"],
            "optimized_graph": result["optimized_graph"],
            "changed_methods": result["changed_methods"],
        }
        json_data = json.dumps(response_data)
        b64_str = base64.b64encode(json_data.encode('utf-8')).decode('ascii')

        if win and win.is_shown():
            win.run(f"onGraphOptimized('{b64_str}');")

    except Exception as ex:
        log(f"[optimize_graph] Исключение: {ex}")
        b64_err = base64.b64encode(json.dumps({'error': str(ex)}).encode('utf-8')).decode('ascii')
        if win and win.is_shown():
            win.run(f"onGraphOptimized('{b64_err}');")

def analyze_complexity(e):
    try:
        if hasattr(e, 'get_string'):
            b64_code = e.get_string()
        else:
            b64_code = str(e)
            
        code = base64.b64decode(b64_code).decode('utf-8')
        
        lines = code.split('\n')
        max_depth = 0
        current_depth = 0
        indent_stack = []
        
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
                
            indent = len(line) - len(line.lstrip())
            is_loop = bool(re.match(r'^(for|while)\b', stripped))
            is_if = bool(re.match(r'^if\b', stripped))
            
            if is_loop:
                while indent_stack and indent_stack[-1] >= indent:
                    indent_stack.pop()
                    current_depth -= 1
                
                indent_stack.append(indent)
                current_depth += 1
                max_depth = max(max_depth, current_depth)
            elif is_if:
                pass

        if max_depth == 0:
            if re.search(r'\bdef\s+(\w+).*?\1\s*\(', code, re.DOTALL):
                 complexity = "O(log n)"
                 desc = "Возможна рекурсия или бинарный поиск."
            else:
                complexity = "O(1)"
                desc = "Константная сложность. Нет циклов."
        elif max_depth == 1:
            complexity = "O(n)"
            desc = "Линейная сложность. Один уровень циклов."
        elif max_depth == 2:
            complexity = "O(n^2)"
            desc = "Квадратичная сложность. Два вложенных цикла."
        elif max_depth == 3:
            complexity = "O(n^3)"
            desc = "Кубическая сложность. Три вложенных цикла."
        else:
            complexity = f"O(n^{max_depth})"
            desc = f"Полиномиальная сложность. {max_depth} уровней вложенности."

        if re.search(r'while\s+.*?//\s*2', code) or re.search(r'while\s+.*?>>\s*1', code):
            complexity = "O(log n)"
            desc = "Логарифмическая сложность (деление пополам)."

        result = {
            "complexity": complexity,
            "description": desc,
            "max_depth": max_depth
        }
        
        json_data = json.dumps(result)
        b64_str = base64.b64encode(json_data.encode('utf-8')).decode('ascii')
        
        if win and win.is_shown():
            win.run(f"onComplexityAnalyzed('{b64_str}');")
            
    except Exception as ex:
        b64_err = base64.b64encode(json.dumps({'error': str(ex)}).encode('utf-8')).decode('ascii')
        if win and win.is_shown():
            win.run(f"onComplexityAnalyzed('{b64_err}');")

def start_fastapi_server():
    if _debug_server_is_running():
        log("Используется уже запущенный сервер Java/терминала на 127.0.0.1:8086.")
        return
    if _port_is_in_use():
        raise RuntimeError(
            "Порт 8086 уже занят приложением, которое не является сервером этой IDE. "
            "Закройте приложение, использующее порт, и запустите IDE снова."
        )

    server = uvicorn.Server(
        uvicorn.Config(fastapi_app, host="127.0.0.1", port=8086, log_level="error")
    )
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    deadline = time.monotonic() + 10
    while server_thread.is_alive() and not server.started and time.monotonic() < deadline:
        time.sleep(0.05)

    if server.started:
        return
    if _debug_server_is_running():
        log("Используется уже запущенный сервер Java/терминала на 127.0.0.1:8086.")
        return
    if _port_is_in_use():
        raise RuntimeError(
            "Порт 8086 занят другим приложением и не отвечает как сервер этой IDE. "
            "Закройте приложение, использующее порт, и запустите IDE снова."
        )
    raise RuntimeError(
        "Не удалось запустить локальный сервер Java/терминала на 127.0.0.1:8086. "
        "Проверьте сообщения выше и повторите запуск."
    )


def main():
    global win
    win = webui.window()
    
    win.bind("get_files", get_files)
    win.bind("read_file", read_file)
    win.bind("save_file", save_file)
    win.bind("parse_java", parse_java)
    win.bind("optimize_graph", optimize_graph)
    win.bind("analyze_complexity", analyze_complexity)

    index_path = RESOURCE_DIR / "index.html"
    if not index_path.is_file():
        raise FileNotFoundError(f"Файл интерфейса WebUI не найден: {index_path}")

    if not win.set_root_folder(str(index_path.parent)):
        raise RuntimeError(f"WebUI не смог открыть каталог ресурсов: {index_path.parent}")

    start_fastapi_server()

    if not win.show(index_path.name):
        raise RuntimeError(f"WebUI не смог открыть интерфейс: {index_path}")
    webui.wait()

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()