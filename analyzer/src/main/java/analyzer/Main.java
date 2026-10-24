package analyzer;

import com.sun.source.tree.CompilationUnitTree;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.source.tree.ClassTree;
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;

import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.element.VariableElement;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

public class Main {
    private static final ObjectMapper JSON = new ObjectMapper();

    private final Map<String, Map<String, Object>> nodes =
        new LinkedHashMap<>();
    private final List<Map<String, Object>> edges =
        new ArrayList<>();
    private final Set<String> edgeKeys =
        new LinkedHashSet<>();
    private final List<Map<String, Object>> diagnostics =
        new ArrayList<>();
    
    private final List<Map<String, Object>> cfgNodes =
        new ArrayList<>();

    private final List<Map<String, Object>> cfgEdges =
        new ArrayList<>();


    private Trees trees;

    private static String typeId(TypeElement type) {
        return "type:" + type.getQualifiedName();
    }

    private static String methodId(ExecutableElement method) {
        Element owner = method.getEnclosingElement();
        String parameters = method.getParameters().stream()
            .map(p -> p.asType().toString())
            .reduce((a, b) -> a + "," + b)
            .orElse("");

        return "method:" + owner + "#" + method.getSimpleName()
            + "(" + parameters + ")";
    }

    private static String fieldId(VariableElement field) {
        return "field:" + field.getEnclosingElement()
            + "#" + field.getSimpleName();
    }

    private void addNode(
        String id, String label, String kind, String type
    ) {
        if (nodes.containsKey(id)) {
            return;
        }

        Map<String, Object> node = new LinkedHashMap<>();
        node.put("id", id);
        node.put("label", label);
        node.put("kind", kind);

        if (type != null) {
            node.put("type", type);
        }

        nodes.put(id, node);
    }

    private void addEdge(
        String from, String to, String kind
    ) {
        String key = from + "|" + to + "|" + kind;

        if (!edgeKeys.add(key)) {
            return;
        }

        Map<String, Object> edge = new LinkedHashMap<>();
        edge.put("from", from);
        edge.put("to", to);
        edge.put("kind", kind);
        edges.add(edge);
    }

    private void addType(TypeElement type) {
        String id = typeId(type);
        String kind = switch (type.getKind()) {
            case INTERFACE, ANNOTATION_TYPE -> "interface";
            case ENUM -> "enum";
            case RECORD -> "record";
            default -> "class";
        };

        addNode(
            id,
            type.getQualifiedName().toString(),
            kind,
            type.asType().toString()
        );
    }

    private void addMethod(ExecutableElement method) {
        Element owner = method.getEnclosingElement();

        if (!(owner instanceof TypeElement type)) {
            return;
        }

        addType(type);

        String id = methodId(method);
        boolean constructor =
            method.getKind() == ElementKind.CONSTRUCTOR;

        String label = type.getQualifiedName() + "."
            + (constructor ? "<init>" : method.getSimpleName())
            + "("
            + method.getParameters().stream()
                .map(p -> p.asType().toString())
                .reduce((a, b) -> a + ", " + b)
                .orElse("")
            + ")";

        addNode(
            id,
            label,
            constructor ? "constructor" : "method",
            constructor ? null : method.getReturnType().toString()
        );

        addEdge(typeId(type), id, "contains");

        Map<String, Object> node = nodes.get(id);
        node.put("static", method.getModifiers().contains(
            javax.lang.model.element.Modifier.STATIC
        ));
        node.put("modifiers", method.getModifiers().stream()
            .map(Enum::name).toList());
    }

    private void addField(VariableElement field) {
        Element owner = field.getEnclosingElement();

        if (!(owner instanceof TypeElement type)) {
            return;
        }

        addType(type);

        String id = fieldId(field);
        addNode(
            id,
            type.getQualifiedName() + "." + field.getSimpleName(),
            "field",
            field.asType().toString()
        );

        addEdge(typeId(type), id, "contains");

        Map<String, Object> node = nodes.get(id);
        node.put("static", field.getModifiers().contains(
            javax.lang.model.element.Modifier.STATIC
        ));
        node.put("modifiers", field.getModifiers().stream()
            .map(Enum::name).toList());
    }

    private void scanDeclarations(
        Iterable<? extends com.sun.source.tree.CompilationUnitTree> units
    ) {
        for (var unit : units) {
            new TreePathScanner<Void, Void>() {
                @Override
                public Void visitClass(
                    ClassTree tree, Void unused
                ) {
                    Element element =
                        trees.getElement(getCurrentPath());

                    if (element instanceof TypeElement type) {
                        addType(type);
                    }

                    return super.visitClass(tree, unused);
                }

                @Override
                public Void visitMethod(MethodTree tree, Void unused) {
                    Element element = trees.getElement(getCurrentPath());
            
                    if (element instanceof ExecutableElement method) {
                        addMethod(method);
            
                        String id = methodId(method);
                        Map<String, Object> cfg =
                            new CFGBuilder().build(tree, id);
            
                        @SuppressWarnings("unchecked")
                        List<Map<String, Object>> methodNodes =
                            (List<Map<String, Object>>) cfg.get("nodes");
            
                        @SuppressWarnings("unchecked")
                        List<Map<String, Object>> methodEdges =
                            (List<Map<String, Object>>) cfg.get("edges");
            
                        cfgNodes.addAll(methodNodes);
                        cfgEdges.addAll(methodEdges);
                    }
            
                    return super.visitMethod(tree, unused);
                }

                @Override
                public Void visitVariable(
                    VariableTree tree, Void unused
                ) {
                    Element element =
                        trees.getElement(getCurrentPath());

                    boolean isField =
                        getCurrentPath().getParentPath() != null
                        && getCurrentPath().getParentPath().getLeaf()
                            instanceof ClassTree;

                    if (isField && element instanceof VariableElement field) {
                        addField(field);
                    }

                    return super.visitVariable(tree, unused);
                }
            }.scan(unit, null);
        }
    }

    private void scanCalls(
        Iterable<? extends com.sun.source.tree.CompilationUnitTree> units
    ) {
        for (var unit : units) {
            new TreePathScanner<Void, Void>() {
                private final Deque<String> callers =
                    new ArrayDeque<>();

                @Override
                public Void visitMethod(
                    MethodTree tree, Void unused
                ) {
                    Element element =
                        trees.getElement(getCurrentPath());

                    String id = element instanceof ExecutableElement method
                        ? methodId(method)
                        : null;

                    if (id != null) {
                        callers.push(id);
                    }

                    try {
                        return super.visitMethod(tree, unused);
                    } finally {
                        if (id != null) {
                            callers.pop();
                        }
                    }
                }

                @Override
                public Void visitMethodInvocation(
                    MethodInvocationTree tree, Void unused
                ) {
                    Element element =
                        trees.getElement(getCurrentPath());

                    if (!callers.isEmpty()
                        && element instanceof ExecutableElement target) {

                        addMethod(target);

                        addEdge(
                            callers.peek(),
                            methodId(target),
                            "calls"
                        );
                    }

                    return super.visitMethodInvocation(tree, unused);
                }
            }.scan(unit, null);
        }
    }

    public Map<String, Object> analyze(List<String> paths)
        throws Exception {

        JavaCompiler compiler =
            ToolProvider.getSystemJavaCompiler();

        if (compiler == null) {
            throw new IllegalStateException(
                "JDK не найден. Установите JDK, а не только JRE."
            );
        }

        DiagnosticCollector<JavaFileObject> collector =
            new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
            compiler.getStandardFileManager(
                collector, Locale.ROOT, null
            )) {

            var files = manager.getJavaFileObjectsFromStrings(paths);

            JavacTask task = (JavacTask) compiler.getTask(
                null,
                manager,
                collector,
                List.of("-proc:none", "-encoding", "UTF-8"),
                null,
                files
            );

            List<CompilationUnitTree> units = new ArrayList<>();
            task.parse().forEach(units::add);

            try {
                task.analyze();
            } catch (RuntimeException ex) {
                // Диагностики всё равно будут возвращены вызывающему коду.
            }

            trees = Trees.instance(task);

            scanDeclarations(units);
            scanCalls(units);

            for (Diagnostic<? extends JavaFileObject> d
                : collector.getDiagnostics()) {

                Map<String, Object> item = new LinkedHashMap<>();
                item.put("kind", d.getKind().name());
                item.put("message", d.getMessage(Locale.ROOT));
                item.put("line", d.getLineNumber());
                item.put("column", d.getColumnNumber());
                item.put("file", d.getSource() == null
                    ? null : d.getSource().getName());

                diagnostics.add(item);
            }
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("nodes", new ArrayList<>(nodes.values()));
        result.put("edges", edges);
        result.put("cfgNodes", cfgNodes);
        result.put("cfgEdges", cfgEdges);
        result.put("diagnostics", diagnostics);

        return result;
    }

    public static void main(String[] args) {
        try {
            if (args.length == 0) {
                System.err.println(
                    "Usage: java -jar java-analyzer.jar <file.java>..."
                );
                System.exit(2);
            }

            Map<String, Object> result =
                new Main().analyze(List.of(args));

            System.out.println(JSON.writeValueAsString(result));

            boolean hasErrors =
                ((List<?>) result.get("diagnostics")).stream()
                    .map(d -> (Map<?, ?>) d)
                    .anyMatch(d -> "ERROR".equals(d.get("kind")));

            if (hasErrors) {
                System.exit(1);
            }
        } catch (Exception ex) {
            System.err.println("Analysis failed: " + ex.getMessage());
            System.exit(2);
        }
    }
}

