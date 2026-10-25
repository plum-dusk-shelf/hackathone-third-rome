import json
import unittest
from unittest.mock import patch

from graph_optimizer_llm import _extract_method_source, analyze_method_complexity


class MethodComplexityTests(unittest.TestCase):
    def setUp(self):
        self.source = """
class Worker {
    int calculate(int n) {
        String brace = "}";
        // A comment with an unmatched brace: {
        for (int i = 0; i < n; i++) {
            System.out.println(brace);
        }
        return n;
    }
}
"""
        self.graph = {
            "nodes": [
                {"id": "1", "label": "Worker.calculate()", "group": "method"},
                {"id": "2", "label": "Worker", "group": "class"},
            ],
            "edges": [{"from": "2", "to": "1", "label": "contains"}],
        }

    def test_extracts_selected_method_without_braces_from_string_or_comment(self):
        method_source = _extract_method_source(self.source, self.graph["nodes"][0])

        self.assertIn("int calculate(int n)", method_source)
        self.assertIn('String brace = "}";', method_source)
        self.assertTrue(method_source.endswith("}"))
        self.assertNotIn("class Worker", method_source)

    def test_requests_model_with_selected_method_and_complete_graph(self):
        model_result = {
            "current_On": "O(n)",
            "detail_current_On": "T(n) = c0 + c1*n",
            "prediction_coeff": 5.2,
            "summary": "Повторный проход можно объединить.",
        }
        with patch(
            "graph_optimizer_llm._send_request",
            return_value=(
                {"choices": [{"message": {"content": json.dumps(model_result)}}]},
                None,
            ),
        ) as send_request:
            result = analyze_method_complexity(
                self.source,
                self.graph,
                "1",
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["current_On"], "O(n)")
        self.assertEqual(result["prediction_coeff"], 5.2)
        prompt = send_request.call_args.args[0][1]["content"]
        self.assertIn("int calculate(int n)", prompt)
        self.assertIn(json.dumps(self.graph, ensure_ascii=False), prompt)

    def test_rejects_class_node_without_calling_model(self):
        with patch("graph_optimizer_llm._send_request") as send_request:
            result = analyze_method_complexity(self.source, self.graph, "2")

        self.assertFalse(result["success"])
        send_request.assert_not_called()

    def test_rejects_invalid_model_result(self):
        with patch(
            "graph_optimizer_llm._send_request",
            return_value=(
                {"choices": [{"message": {"content": '{"prediction_coeff": -1}'}}]},
                None,
            ),
        ):
            result = analyze_method_complexity(self.source, self.graph, "1")

        self.assertFalse(result["success"])
        self.assertIn("ожидаемому формату", result["error"])


if __name__ == "__main__":
    unittest.main()
