package analyzer;

import com.sun.source.tree.*;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Collections;
import java.util.List;
import java.util.Map;

public class CFGBuilder {

    private final List<Map<String, Object>> nodes = new ArrayList<>();
    private final List<Map<String, Object>> edges = new ArrayList<>();

    private String methodId;
    private int counter;

    public Map<String, Object> build(MethodTree method, String methodId) {
        this.methodId = methodId;
        this.counter = 0;
        nodes.clear();
        edges.clear();

        String entry = addNode("BEGIN", "entry");
        String exit = addNode("END", "exit");

        BlockTree body = method.getBody();

        if (body == null) {
            addEdge(entry, exit, "next");
        } else {
            String bodyEntry = buildStatement(
                    body,
                    exit,
                    exit,
                    null
            );

            addEdge(entry, bodyEntry, "next");
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("methodId", methodId);
        result.put("nodes", new ArrayList<>(nodes));
        result.put("edges", new ArrayList<>(edges));

        return result;
    }

    private String addNode(String label, String kind) {
        String id = "cfg:" + methodId + ":" + counter++;

        Map<String, Object> node = new LinkedHashMap<>();
        node.put("id", id);
        node.put("label", label);
        node.put("kind", kind);
        node.put("methodId", methodId);

        nodes.add(node);
        return id;
    }

    private void addEdge(String from, String to, String kind) {
        if (from == null || to == null) {
            return;
        }

        Map<String, Object> edge = new LinkedHashMap<>();
        edge.put("from", from);
        edge.put("to", to);
        edge.put("kind", kind);
        edge.put("methodId", methodId);

        edges.add(edge);
    }

    private String buildStatement(
            StatementTree statement,
            String next,
            String breakTarget,
            String continueTarget
    ) {
        if (statement == null) {
            return next;
        }

        // Последовательность операторов
        if (statement instanceof BlockTree block) {
            String current = next;
            List<? extends StatementTree> statements = block.getStatements();

            for (int i = statements.size() - 1; i >= 0; i--) {
                current = buildStatement(
                        statements.get(i),
                        current,
                        breakTarget,
                        continueTarget
                );
            }

            return current;
        }

        // if / else
        if (statement instanceof IfTree tree) {
            String condition = addNode(
                    tree.getCondition().toString(),
                    "condition"
            );

            String thenEntry = buildStatement(
                    tree.getThenStatement(),
                    next,
                    breakTarget,
                    continueTarget
            );

            String elseEntry;

            if (tree.getElseStatement() != null) {
                elseEntry = buildStatement(
                        tree.getElseStatement(),
                        next,
                        breakTarget,
                        continueTarget
                );
            } else {
                elseEntry = next;
            }

            addEdge(condition, thenEntry, "true");
            addEdge(condition, elseEntry, "false");

            return condition;
        }

        // switch
        if (statement instanceof SwitchTree tree) {
            String selector = addNode(
                    tree.getExpression().toString(),
                    "switch"
            );

            List<? extends CaseTree> cases = tree.getCases();
            List<String> entries = new ArrayList<>(
                    java.util.Collections.nCopies(cases.size(), next)
            );

            String nextCaseEntry = next;

            // Строим ветки в обратном порядке,
            // чтобы сохранить порядок операторов.
            for (int i = cases.size() - 1; i >= 0; i--) {
                CaseTree caseTree = cases.get(i);

                String fallThroughTarget = nextCaseEntry;
                String caseEntry;

                if (caseTree.getCaseKind() == CaseTree.CaseKind.RULE) {
                    // case ... -> ... не проваливается в следующую ветку.
                    Tree body = caseTree.getBody();

                    if (body instanceof StatementTree bodyStatement) {
                        caseEntry = buildStatement(
                                bodyStatement,
                                next,
                                next,
                                continueTarget
                        );
                    } else if (body != null) {
                        caseEntry = addNode(body.toString(), "statement");
                        addEdge(caseEntry, next, "next");
                    } else {
                        caseEntry = next;
                    }
                } else {
                    // Обычный case ...: может перейти в следующую ветку.
                    List<? extends StatementTree> statements =
                            caseTree.getStatements();

                    String current = fallThroughTarget;

                    if (statements != null) {
                        for (int j = statements.size() - 1; j >= 0; j--) {
                            current = buildStatement(
                                    statements.get(j),
                                    current,
                                    next,
                                    continueTarget
                            );
                        }
                    }

                    caseEntry = current;
                }

                entries.set(i, caseEntry);
                nextCaseEntry = caseEntry;
            }

            boolean hasDefault = false;

            for (int i = 0; i < cases.size(); i++) {
                CaseTree caseTree = cases.get(i);

                List<? extends ExpressionTree> expressions =
                        caseTree.getExpressions();

                String label;

                if (expressions == null || expressions.isEmpty()) {
                    label = "default";
                    hasDefault = true;
                } else {
                    label = String.join(
                            ", ",
                            expressions.stream()
                                    .map(Object::toString)
                                    .toList()
                    );
                }

                addEdge(selector, entries.get(i), "case " + label);
            }

            if (!hasDefault) {
                addEdge(selector, next, "no-match");
            }

            return selector;
        }

        // while
        if (statement instanceof WhileLoopTree tree) {
            String condition = addNode(
                    tree.getCondition().toString(),
                    "condition"
            );

            String bodyEntry = buildStatement(
                    tree.getStatement(),
                    condition,
                    next,
                    condition
            );

            addEdge(condition, bodyEntry, "true");
            addEdge(condition, next, "false");

            return condition;
        }

        // do-while
        if (statement instanceof DoWhileLoopTree tree) {
            String condition = addNode(
                    tree.getCondition().toString(),
                    "condition"
            );

            String bodyEntry = buildStatement(
                    tree.getStatement(),
                    condition,
                    next,
                    condition
            );

            addEdge(condition, bodyEntry, "true");
            addEdge(condition, next, "false");

            return bodyEntry;
        }

        // for
        if (statement instanceof ForLoopTree tree) {
            String condition;

            if (tree.getCondition() != null) {
                condition = addNode(
                        tree.getCondition().toString(),
                        "condition"
                );
            } else {
                condition = addNode("true", "condition");
            }

            // Обновления выполняются после тела цикла.
            String updateEntry = condition;
            List<? extends ExpressionStatementTree> updates =
                    tree.getUpdate();

            for (int i = updates.size() - 1; i >= 0; i--) {
                String update = addNode(
                        updates.get(i).toString(),
                        "update"
                );

                addEdge(update, updateEntry, "next");
                updateEntry = update;
            }

            String bodyEntry = buildStatement(
                    tree.getStatement(),
                    updateEntry,
                    next,
                    updateEntry
            );

            addEdge(condition, bodyEntry, "true");

            if (tree.getCondition() != null) {
                addEdge(condition, next, "false");
            }

            // Инициализация выполняется до проверки условия.
            String current = condition;
            List<? extends StatementTree> initializers =
                    tree.getInitializer();

            for (int i = initializers.size() - 1; i >= 0; i--) {
                current = buildStatement(
                        initializers.get(i),
                        current,
                        breakTarget,
                        continueTarget
                );
            }

            return current;
        }

        // for-each: for (String name : names)
        if (statement instanceof EnhancedForLoopTree tree) {
            String condition = addNode(
                    "hasNext(" + tree.getExpression() + ")",
                    "condition"
            );

            String iteration = addNode(
                    tree.getVariable() + " = next()",
                    "iteration"
            );

            String bodyEntry = buildStatement(
                    tree.getStatement(),
                    condition,
                    next,
                    condition
            );

            addEdge(condition, iteration, "true");
            addEdge(condition, next, "false");
            addEdge(iteration, bodyEntry, "next");

            return condition;
        }

        // break
        if (statement instanceof BreakTree) {
            String node = addNode(statement.toString(), "break");
            addEdge(node, breakTarget != null ? breakTarget : next, "break");
            return node;
        }

        // continue
        if (statement instanceof ContinueTree) {
            String node = addNode(statement.toString(), "continue");
            addEdge(
                    node,
                    continueTarget != null ? continueTarget : next,
                    "continue"
            );
            return node;
        }

        // return
        if (statement instanceof ReturnTree) {
            String node = addNode(statement.toString(), "return");
            addEdge(node, findExitNode(), "return");
            return node;
        }

        // throw
        if (statement instanceof ThrowTree) {
            String node = addNode(statement.toString(), "throw");
            addEdge(node, findExitNode(), "throw");
            return node;
        }

        // Прочие операторы: объявление переменной, вызов метода и т. д.
        String node = addNode(statement.toString(), "statement");
        addEdge(node, next, "next");

        return node;
    }

    private String findExitNode() {
        for (Map<String, Object> node : nodes) {
            if ("exit".equals(node.get("kind"))) {
                return (String) node.get("id");
            }
        }

        return null;
    }
}
