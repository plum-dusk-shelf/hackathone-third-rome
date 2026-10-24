import unittest

from parser import parse_java_to_graph


class ParseJavaToGraphTests(unittest.TestCase):
    def test_graph_contains_declared_classes_methods_and_local_calls(self):
        source = """
        class Service {
            void start() {
                runTask();
                this.finish();
            }

            void runTask() {}
            void finish() {}
        }
        """

        graph = parse_java_to_graph(source)
        labels = {node["id"]: node["label"] for node in graph["nodes"]}
        calls = {
            (labels[edge["from"]], labels[edge["to"]])
            for edge in graph["edges"]
            if edge["label"] == "calls"
        }

        self.assertEqual(
            calls,
            {
                ("Service.start()", "Service.runTask()"),
                ("Service.start()", "Service.finish()"),
            },
        )

    def test_does_not_guess_calls_to_same_named_methods_in_other_classes(self):
        source = """
        class First {
            void execute() {
                process();
            }

            void process() {}
        }

        class Second {
            void process() {}
        }
        """

        graph = parse_java_to_graph(source)
        labels = {node["id"]: node["label"] for node in graph["nodes"]}
        calls = [
            (labels[edge["from"]], labels[edge["to"]])
            for edge in graph["edges"]
            if edge["label"] == "calls"
        ]

        self.assertEqual(calls, [("First.execute()", "First.process()")])

    def test_resolves_inherited_unqualified_calls(self):
        source = """
        class Parent {
            void cleanup() {}
        }

        class Child extends Parent {
            void run() {
                cleanup();
            }
        }
        """

        graph = parse_java_to_graph(source)
        labels = {node["id"]: node["label"] for node in graph["nodes"]}
        calls = [
            (labels[edge["from"]], labels[edge["to"]])
            for edge in graph["edges"]
            if edge["label"] == "calls"
        ]

        self.assertEqual(calls, [("Child.run()", "Parent.cleanup()")])

    def test_resolves_method_calls_on_typed_receivers(self):
        source = """
        class FirstWorker {
            void run() {}
        }

        class SecondWorker {
            void run() {}
        }

        class Client {
            FirstWorker first;

            void execute(SecondWorker second) {
                first.run();
                second.run();
            }
        }
        """

        graph = parse_java_to_graph(source)
        labels = {node["id"]: node["label"] for node in graph["nodes"]}
        calls = {
            (labels[edge["from"]], labels[edge["to"]])
            for edge in graph["edges"]
            if edge["label"] == "calls"
        }

        self.assertEqual(
            calls,
            {
                ("Client.execute()", "FirstWorker.run()"),
                ("Client.execute()", "SecondWorker.run()"),
            },
        )

    def test_parser_error_is_returned_for_invalid_java(self):
        result = parse_java_to_graph("class Broken { void method( }")

        self.assertIn("error", result)
        self.assertNotIn("nodes", result)


if __name__ == "__main__":
    unittest.main()
