"""Unit tests for substitution module."""

import os
import unittest

from tasktree.substitution import (
    PLACEHOLDER_PATTERN,
    substitute_arguments,
    substitute_all,
    substitute_environment,
    substitute_variables,
)


class TestPlaceholderPattern(unittest.TestCase):
    """Test the regex pattern for matching placeholders."""

    def test_pattern_matches_var_prefix(self):
        """Test pattern matches {{ var.name }} syntax."""
        match = PLACEHOLDER_PATTERN.search("{{ var.foo }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "var")
        self.assertEqual(match.group(2), "foo")

    def test_pattern_matches_arg_prefix(self):
        """Test pattern matches {{ arg.name }} syntax."""
        match = PLACEHOLDER_PATTERN.search("{{ arg.bar }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "arg")
        self.assertEqual(match.group(2), "bar")

    def test_pattern_matches_env_prefix(self):
        """Test pattern matches {{ env.name }} syntax."""
        match = PLACEHOLDER_PATTERN.search("{{ env.USER }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "env")
        self.assertEqual(match.group(2), "USER")

    def test_pattern_allows_whitespace(self):
        """Test pattern tolerates extra whitespace."""
        test_cases = [
            "{{var.name}}",
            "{{ var.name }}",
            "{{ var.name }}",
            "{{  var  .  name  }}",
        ]
        for text in test_cases:
            with self.subTest(text=text):
                match = PLACEHOLDER_PATTERN.search(text)
                self.assertIsNotNone(match)
                self.assertEqual(match.group(1), "var")
                self.assertEqual(match.group(2), "name")

    def test_pattern_requires_valid_identifier(self):
        """Test pattern only matches valid identifier names."""
        # Valid identifiers
        valid = ["foo", "foo_bar", "foo123", "_private"]
        for name in valid:
            with self.subTest(name=name):
                match = PLACEHOLDER_PATTERN.search(f"{{{{ var.{name} }}}}")
                self.assertIsNotNone(match)

        # Invalid identifiers (should not match)
        invalid = ["123foo", "foo-bar", "foo.bar", "foo bar"]
        for name in invalid:
            with self.subTest(name=name):
                match = PLACEHOLDER_PATTERN.search(f"{{{{ var.{name} }}}}")
                self.assertIsNone(match)


class TestSubstituteVariables(unittest.TestCase):
    """Test substitute_variables function."""

    def test_substitute_single_variable(self):
        """Test basic {{ var.x }} substitution."""
        result = substitute_variables("Hello {{ var.name }}!", {"name": "World"})
        self.assertEqual(result, "Hello World!")

    def test_substitute_multiple_variables(self):
        """Test multiple different variables in same string."""
        text = "{{ var.greeting }} {{ var.name }}!"
        variables = {"greeting": "Hello", "name": "World"}
        result = substitute_variables(text, variables)
        self.assertEqual(result, "Hello World!")

    def test_substitute_same_variable_multiple_times(self):
        """Test same variable appears multiple times."""
        text = "{{ var.name }} says hello to {{ var.name }}"
        variables = {"name": "Alice"}
        result = substitute_variables(text, variables)
        self.assertEqual(result, "Alice says hello to Alice")

    def test_substitute_no_placeholders(self):
        """Test string without placeholders returns unchanged."""
        text = "No placeholders here"
        result = substitute_variables(text, {"foo": "bar"})
        self.assertEqual(result, text)

    def test_substitute_ignores_arg_prefix(self):
        """Test {{ arg.name }} is not substituted."""
        text = "{{ var.foo }} {{ arg.bar }}"
        variables = {"foo": "FOO", "bar": "BAR"}
        result = substitute_variables(text, variables)
        self.assertEqual(result, "FOO {{ arg.bar }}")

    def test_substitute_undefined_variable_raises(self):
        """Test error for undefined variable reference."""
        with self.assertRaises(ValueError) as cm:
            substitute_variables("{{ var.missing }}", {})
        self.assertIn("missing", str(cm.exception))
        self.assertIn("not defined", str(cm.exception))

    def test_substitute_with_whitespace_variations(self):
        """Test whitespace handling in placeholders."""
        variables = {"name": "World"}
        test_cases = [
            ("{{var.name}}", "World"),
            ("{{ var.name }}", "World"),
            ("{{ var.name }}", "World"),
            ("{{  var  .  name  }}", "World"),
        ]
        for text, expected in test_cases:
            with self.subTest(text=text):
                result = substitute_variables(text, variables)
                self.assertEqual(result, expected)

    def test_substitute_empty_string_value(self):
        """Test variable with empty string value."""
        result = substitute_variables("foo{{ var.x }}bar", {"x": ""})
        self.assertEqual(result, "foobar")

    def test_substitute_in_complex_text(self):
        """Test substitution in realistic command string."""
        text = 'echo "Deploying to {{ var.server }} on port {{ var.port }}"'
        variables = {"server": "production.example.com", "port": "8080"}
        result = substitute_variables(text, variables)
        self.assertEqual(
            result, 'echo "Deploying to production.example.com on port 8080"'
        )


class TestSubstituteArguments(unittest.TestCase):
    """Test substitute_arguments function."""

    def test_substitute_single_argument(self):
        """Test basic {{ arg.x }} substitution."""
        result = substitute_arguments("Hello {{ arg.name }}!", {"name": "World"})
        self.assertEqual(result, "Hello World!")

    def test_substitute_multiple_arguments(self):
        """Test multiple different arguments in same string."""
        text = "deploy {{ arg.app }} to {{ arg.region }}"
        args = {"app": "myapp", "region": "us-west-1"}
        result = substitute_arguments(text, args)
        self.assertEqual(result, "deploy myapp to us-west-1")

    def test_substitute_converts_types_to_strings(self):
        """Test int/bool/float values are converted to strings."""
        text = "port={{ arg.port }} debug={{ arg.debug }} timeout={{ arg.timeout }}"
        args = {"port": 8080, "debug": True, "timeout": 30.5}
        result = substitute_arguments(text, args)
        self.assertEqual(result, "port=8080 debug=True timeout=30.5")

    def test_substitute_ignores_var_prefix(self):
        """Test {{ var.name }} is not substituted."""
        text = "{{ arg.foo }} {{ var.bar }}"
        args = {"foo": "FOO", "bar": "BAR"}
        result = substitute_arguments(text, args)
        self.assertEqual(result, "FOO {{ var.bar }}")

    def test_substitute_undefined_argument_raises(self):
        """Test error for undefined argument reference."""
        with self.assertRaises(ValueError) as cm:
            substitute_arguments("{{ arg.missing }}", {})
        self.assertIn("missing", str(cm.exception))
        self.assertIn("not defined", str(cm.exception))

    def test_substitute_none_value(self):
        """Test None value is converted to string."""
        result = substitute_arguments("value={{ arg.x }}", {"x": None})
        self.assertEqual(result, "value=None")


class TestSubstituteEnvironment(unittest.TestCase):
    """Test substitute_environment function."""

    def test_substitute_single_env_var(self):
        """Test basic {{ env.VAR }} substitution."""
        os.environ['TEST_VAR'] = 'test_value'
        try:
            result = substitute_environment("Hello {{ env.TEST_VAR }}!")
            self.assertEqual(result, "Hello test_value!")
        finally:
            del os.environ['TEST_VAR']

    def test_substitute_multiple_env_vars(self):
        """Test multiple different env vars in same string."""
        os.environ['VAR1'] = 'value1'
        os.environ['VAR2'] = 'value2'
        try:
            text = "{{ env.VAR1 }} and {{ env.VAR2 }}"
            result = substitute_environment(text)
            self.assertEqual(result, "value1 and value2")
        finally:
            del os.environ['VAR1']
            del os.environ['VAR2']

    def test_substitute_same_env_var_multiple_times(self):
        """Test same env var appears multiple times."""
        os.environ['USER'] = 'testuser'
        try:
            text = "{{ env.USER }} says hello to {{ env.USER }}"
            result = substitute_environment(text)
            self.assertEqual(result, "testuser says hello to testuser")
        finally:
            del os.environ['USER']

    def test_substitute_no_placeholders(self):
        """Test string without placeholders returns unchanged."""
        text = "No placeholders here"
        result = substitute_environment(text)
        self.assertEqual(result, text)

    def test_substitute_ignores_var_prefix(self):
        """Test {{ var.name }} is not substituted."""
        os.environ['FOO'] = 'env_foo'
        try:
            text = "{{ env.FOO }} {{ var.bar }}"
            result = substitute_environment(text)
            self.assertEqual(result, "env_foo {{ var.bar }}")
        finally:
            del os.environ['FOO']

    def test_substitute_ignores_arg_prefix(self):
        """Test {{ arg.name }} is not substituted."""
        os.environ['FOO'] = 'env_foo'
        try:
            text = "{{ env.FOO }} {{ arg.bar }}"
            result = substitute_environment(text)
            self.assertEqual(result, "env_foo {{ arg.bar }}")
        finally:
            del os.environ['FOO']

    def test_substitute_undefined_env_var_raises(self):
        """Test error for undefined environment variable."""
        # Make sure var is not set
        if 'DEFINITELY_NOT_SET_VAR' in os.environ:
            del os.environ['DEFINITELY_NOT_SET_VAR']

        with self.assertRaises(ValueError) as cm:
            substitute_environment("{{ env.DEFINITELY_NOT_SET_VAR }}")
        self.assertIn("DEFINITELY_NOT_SET_VAR", str(cm.exception))
        self.assertIn("not set", str(cm.exception))

    def test_substitute_with_whitespace_variations(self):
        """Test whitespace handling in placeholders."""
        os.environ['TEST_VAR'] = 'value'
        try:
            test_cases = [
                ("{{env.TEST_VAR}}", "value"),
                ("{{ env.TEST_VAR }}", "value"),
                ("{{  env  .  TEST_VAR  }}", "value"),
            ]
            for text, expected in test_cases:
                with self.subTest(text=text):
                    result = substitute_environment(text)
                    self.assertEqual(result, expected)
        finally:
            del os.environ['TEST_VAR']

    def test_substitute_empty_string_value(self):
        """Test env var with empty string value."""
        os.environ['EMPTY_VAR'] = ''
        try:
            result = substitute_environment("foo{{ env.EMPTY_VAR }}bar")
            self.assertEqual(result, "foobar")
        finally:
            del os.environ['EMPTY_VAR']

    def test_substitute_in_complex_command(self):
        """Test substitution in realistic command string."""
        os.environ['DEPLOY_USER'] = 'admin'
        os.environ['DEPLOY_HOST'] = 'prod.example.com'
        try:
            text = 'scp package.tar.gz {{ env.DEPLOY_USER }}@{{ env.DEPLOY_HOST }}:/opt/'
            result = substitute_environment(text)
            self.assertEqual(result, 'scp package.tar.gz admin@prod.example.com:/opt/')
        finally:
            del os.environ['DEPLOY_USER']
            del os.environ['DEPLOY_HOST']


class TestSubstituteAll(unittest.TestCase):
    """Test substitute_all function."""

    def test_substitute_both_var_and_arg(self):
        """Test both variables and arguments are substituted."""
        text = "{{ var.server }} {{ arg.port }}"
        variables = {"server": "example.com"}
        args = {"port": 8080}
        result = substitute_all(text, variables, args)
        self.assertEqual(result, "example.com 8080")

    def test_variables_substituted_before_arguments(self):
        """Test variables are substituted first, then arguments."""
        # If a variable contains {{ arg.x }}, it should remain for arg substitution
        text = "{{ var.template }}"
        variables = {"template": "port={{ arg.port }}"}
        args = {"port": 9000}
        result = substitute_all(text, variables, args)
        self.assertEqual(result, "port=9000")

    def test_substitute_mixed_placeholders(self):
        """Test realistic case with both types."""
        text = 'echo "Deploy {{ arg.app }} to {{ var.server }}:{{ var.port }}"'
        variables = {"server": "prod.example.com", "port": "8080"}
        args = {"app": "myservice"}
        result = substitute_all(text, variables, args)
        self.assertEqual(result, 'echo "Deploy myservice to prod.example.com:8080"')

    def test_substitute_all_empty_dicts(self):
        """Test with no variables or arguments."""
        text = "No placeholders"
        result = substitute_all(text, {}, {})
        self.assertEqual(result, text)

    def test_substitute_all_three_types(self):
        """Test variables, arguments, and environment all work together."""
        os.environ['ENV_VAR'] = 'from_env'
        try:
            text = "{{ var.v }} {{ arg.a }} {{ env.ENV_VAR }}"
            variables = {"v": "from_var"}
            args = {"a": "from_arg"}
            result = substitute_all(text, variables, args)
            self.assertEqual(result, "from_var from_arg from_env")
        finally:
            del os.environ['ENV_VAR']

    def test_substitute_order_var_then_arg_then_env(self):
        """Test substitution happens in correct order."""
        os.environ['PORT'] = '9000'
        try:
            # Variable contains arg placeholder, which contains env placeholder
            text = "{{ var.template }}"
            variables = {"template": "server={{ arg.server }}"}
            args = {"server": "host:{{ env.PORT }}"}
            result = substitute_all(text, variables, args)
            self.assertEqual(result, "server=host:9000")
        finally:
            del os.environ['PORT']


if __name__ == "__main__":
    unittest.main()
