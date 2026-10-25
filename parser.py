import javalang

def parse_java_to_graph(java_code: str) -> dict:
    """
    Принимает Java-код (строку) и возвращает словарь с узлами и связями для vis-network.
    """
    try:
        tree = javalang.parse.parse(java_code)
    except Exception as e:
        return {"error": f"Ошибка парсинга Java: {str(e)}"}

    nodes = []
    edges = []
    node_id = 0
    class_ids = {}
    method_ids = {}
    methods_by_class = {}
    field_types = {}
    class_bases = {}
    edge_keys = set()

    # ==========================================
    # 1. Собираем классы
    # ==========================================
    for path, class_decl in tree.filter(javalang.tree.ClassDeclaration):
        class_name = class_decl.name
        if class_name not in class_ids:
            class_ids[class_name] = str(node_id)
            nodes.append({
                "id": str(node_id),
                "label": class_name,
                "group": "class",
                "shape": "box",
                "color": {"background": "#3a2c24", "border": "#d48c4a"}
            })
            node_id += 1
        if class_decl.extends:
            class_bases[class_name] = class_decl.extends.name

    for _, class_decl in tree.filter(javalang.tree.ClassDeclaration):
        class_name = class_decl.name
        class_fields = field_types.setdefault(class_name, {})
        for field in class_decl.fields:
            field_type = getattr(field.type, "name", None)
            if field_type in class_ids:
                for declarator in field.declarators:
                    class_fields[declarator.name] = field_type

    # ==========================================
    # 2. Собираем методы и связь "класс содержит метод"
    # ==========================================
    # Сначала создадим узлы методов, чтобы потом ссылаться на них при вызовах
    for path, method_decl in tree.filter(javalang.tree.MethodDeclaration):
        parent_class = next(
            (p.name for p in reversed(path) if isinstance(p, javalang.tree.ClassDeclaration)),
            None,
        )

        if parent_class and parent_class in class_ids:
            method_name = method_decl.name
            method_label = f"{parent_class}.{method_name}()"

            if method_label not in method_ids:
                method_ids[method_label] = str(node_id)
                nodes.append({
                    "id": str(node_id),
                    "label": method_label,
                    "group": "method",
                    "shape": "ellipse",
                    "color": {"background": "#222222", "border": "#777777"}
                })
                method_id = str(node_id)
                node_id += 1
            else:
                method_id = method_ids[method_label]

            methods_by_class.setdefault(parent_class, {}).setdefault(method_name, method_id)

            edge_key = (class_ids[parent_class], method_id, "contains")
            if edge_key not in edge_keys:
                edge_keys.add(edge_key)
                edges.append({
                    "from": class_ids[parent_class],
                    "to": method_id,
                    "label": "contains",
                    "arrows": "to",
                    "color": "#555555"
                })

    # ==========================================
    # 3. Анализ вызовов методов внутри методов
    # ==========================================
    for path, method_decl in tree.filter(javalang.tree.MethodDeclaration):
        parent_class = next(
            (p.name for p in reversed(path) if isinstance(p, javalang.tree.ClassDeclaration)),
            None,
        )

        if not parent_class:
            continue

        caller_label = f"{parent_class}.{method_decl.name}()"
        caller_id = method_ids.get(caller_label)
        if not caller_id:
            continue

        if method_decl.body:
            variable_types = {}
            for parameter in method_decl.parameters:
                parameter_type = getattr(parameter.type, "name", None)
                if parameter_type in class_ids:
                    variable_types[parameter.name] = parameter_type
            for _, declaration in method_decl.filter(javalang.tree.LocalVariableDeclaration):
                variable_type = getattr(declaration.type, "name", None)
                if variable_type in class_ids:
                    for declarator in declaration.declarators:
                        variable_types[declarator.name] = variable_type
            for _, control in method_decl.filter(javalang.tree.EnhancedForControl):
                variable_type = getattr(control.var.type, "name", None)
                if variable_type in class_ids:
                    for declarator in control.var.declarators:
                        variable_types[declarator.name] = variable_type

            for _, invocation in method_decl.filter(javalang.tree.MethodInvocation):
                qualifier = invocation.qualifier
                candidates = set()
                if not qualifier or qualifier == "this":
                    target_class = parent_class
                    visited_classes = set()
                    while target_class and target_class not in visited_classes:
                        visited_classes.add(target_class)
                        method_id = methods_by_class.get(target_class, {}).get(invocation.member)
                        if method_id:
                            candidates.add(method_id)
                            break
                        target_class = class_bases.get(target_class)
                elif qualifier == "super":
                    target_class = class_bases.get(parent_class)
                    method_id = methods_by_class.get(target_class, {}).get(invocation.member)
                    if method_id:
                        candidates.add(method_id)
                else:
                    receiver = qualifier.removeprefix("this.")
                    target_class = (
                        variable_types.get(receiver)
                        or field_types.get(parent_class, {}).get(receiver)
                        or (receiver if receiver in class_ids else None)
                    )
                    method_id = methods_by_class.get(target_class, {}).get(invocation.member)
                    if method_id:
                        candidates.add(method_id)

                if len(candidates) != 1:
                    continue

                target_id = candidates.pop()
                edge_key = (caller_id, target_id, "calls")
                if edge_key not in edge_keys:
                    edge_keys.add(edge_key)
                    edges.append({
                        "from": caller_id,
                        "to": target_id,
                        "label": "calls",
                        "arrows": "to",
                        "color": "#d48c4a",
                        "dashes": True
                    })

    return {"nodes": nodes, "edges": edges}



# ==========================================
# Для тестирования из консоли:
# ==========================================
if __name__ == "__main__":
    # Читаем файл TestGraph.java
    try:
        with open("TestGraph.java", "r", encoding="utf-8") as f:
            code = f.read()
    except FileNotFoundError:
        print("Файл TestGraph.java не найден. Создайте его в папке с проектом.")
        exit(1)

    graph = parse_java_to_graph(code)
    if "error" in graph:
        print("Ошибка:", graph["error"])
    else:
        print(f"Узлов: {len(graph['nodes'])}, Связей: {len(graph['edges'])}")
        for n in graph['nodes']:
            print(f"  Node {n['id']}: {n['label']} ({n['group']})")
        for e in graph['edges']:
            print(f"  Edge {e['from']} -> {e['to']} ({e['label']})")