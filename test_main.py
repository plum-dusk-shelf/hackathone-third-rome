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
from graph_optimizer_llm import analyze_method_complexity as request_method_complexity
from graph_optimizer_llm import optimize_java_code
from settings import load_settings, save_settings

# PROJECT_DIR — папка, где лежит этот скрипт (тут же index.html, syntax.js)
PROJECT_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", PROJECT_DIR))

# WORKSPACE — папка проекта, которую выбрал пользователь (через .bat)
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
    """Разрешает относительный путь относительно WORKSPACE."""
    file_path = Path(path)
    return file_path if file_path.is_absolute() else DEBUG_WORKSPACE / file_path


def log(message: str):
    """Печатает в терминал и отправляет в панель «Консоль» в IDE."""
    print(message, flush=True)
    if win and win.is_shown():
        safe = (message.replace("\\", "\\\\").replace("'", "\\'")
                       .replace('"', '\\"').replace("\n", "\\n"))
        win.run(f"appendLog('{safe}');")


def _send_settings_result(callback, result):
    encoded = base64.b64encode(
        json.dumps(result, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    if win and win.is_shown():
        win.run(f"{callback}('{encoded}');")


def get_settings(_event=None):
    try:
        _send_settings_result("onSettingsLoaded", load_settings())
    except (OSError, ValueError) as ex:
        _send_settings_result("onSettingsLoaded", {"error": str(ex)})


def save_user_settings(event):
    try:
        settings_b64 = event.get_string() if hasattr(event, "get_string") else str(event)
        settings_data = json.loads(base64.b64decode(settings_b64).decode("utf-8"))
        saved_settings = save_settings(settings_data)
        _send_settings_result("onSettingsSaved", {"settings": saved_settings})
    except (OSError, ValueError, json.JSONDecodeError) as ex:
        _send_settings_result("onSettingsSaved", {"error": str(ex)})


def get_files(_event):
    """Возвращает дерево файлов выбранного проекта (WORKSPACE)."""
    base_dir = str(DEBUG_WORKSPACE)  # <-- ИСПОЛЬЗУЕМ WORKSPACE
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

        relative_path = base64.b64decode(safe_path_b64).decode('utf-8')
        absolute_path = str(resolve_project_path(relative_path))
        log(f"[read_file] Читаем: {absolute_path}")

        with open(absolute_path, 'r', encoding='utf-8') as f:
            content = f.read()

        log(f"[read_file] Прочитано {len(content)} символов")
        # ВАЖНО: возвращаем relative_path, а не absolute_path!
        json_data = json.dumps({'content': content, 'path': relative_path})
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
        relative_path = data.get('path', '')
        content = data.get('content', '')

        if not relative_path:
            raise ValueError("Путь не передан")

        absolute_path = str(resolve_project_path(relative_path))
        log(f"[save_file] Сохраняем: {absolute_path}")
        with open(absolute_path, 'w', encoding='utf-8') as f:
            f.write(content)

        log(f"[save_file] Успешно сохранено")
        resp = json.dumps({'status': 'ok', 'path': relative_path})
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
    request_id = None
    try:
        if hasattr(e, 'get_string'):
            payload_b64 = e.get_string()
        else:
            payload_b64 = str(e)
        payload = json.loads(base64.b64decode(payload_b64).decode("utf-8"))
        java_code = payload.get("code", "")
        graph_json = payload.get("graph", {})
        node_id = payload.get("node_id")
        request_id = payload.get("request_id")
        if not isinstance(java_code, str) or not java_code.strip():
            raise ValueError("Исходный код Java не передан.")
        if node_id is None:
            raise ValueError("Не выбрана вершина метода.")

        result = request_method_complexity(java_code, graph_json, str(node_id), log=log)
        result["request_id"] = request_id
        if not result.get("success"):
            log(f"[complexity] Ошибка: {result.get('error', 'Неизвестная ошибка')}")

        _send_settings_result("onComplexityAnalyzed", result)
    except Exception as ex:
        _send_settings_result("onComplexityAnalyzed", {
            "success": False,
            "error": str(ex),
            "request_id": request_id,
        })


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
    win.bind("get_settings", get_settings)
    win.bind("save_user_settings", save_user_settings)
    

    index_path = RESOURCE_DIR / "index.html"
    if not index_path.is_file():
        raise FileNotFoundError(f"Файл интерфейса WebUI не найден: {index_path}")
    
    # --- Отладочные принты ---
    print(f"[DBG] RESOURCE_DIR = {RESOURCE_DIR}", flush=True)
    print(f"[DBG] index_path   = {index_path}", flush=True)
    print(f"[DBG] exists       = {index_path.is_file()}", flush=True)
    print(f"[DBG] parent exists= {index_path.parent.is_dir()}", flush=True)
    print(f"[DBG] parent access= {os.access(str(index_path.parent), os.R_OK | os.X_OK)}", flush=True)
    print(f"[DBG] parent list  = {os.listdir(str(index_path.parent))[:5]}", flush=True)
    print(f"[DBG] DEBUG_WORKSPACE = {DEBUG_WORKSPACE}", flush=True)

    # set_root_folder указывает на папку, где лежит index.html (для веб-сервера WebUI)
    if not win.set_root_folder(str(index_path.parent)):
        raise RuntimeError(f"WebUI не смог открыть каталог ресурсов: {index_path.parent}")

    start_fastapi_server()

    if not win.show(index_path.name):
        raise RuntimeError(f"WebUI не смог открыть интерфейс: {index_path}")
    webui.wait()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()