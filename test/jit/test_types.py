from collections import namedtuple
from typing import Dict, List, Optional, Tuple

from torch.testing._internal.jit_utils import JitTestCase
from torch.testing import FileCheck
from textwrap import dedent
from jit.test_module_interface import TestModuleInterface  # noqa: F401
import inspect
import os
import sys
import torch
import torch.testing._internal.jit_utils

# Make the helper files in test/ importable
pytorch_test_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(pytorch_test_dir)

if __name__ == '__main__':
    raise RuntimeError("This test file is not meant to be run directly, use:\n\n"
                       "\tpython test/test_jit.py TESTNAME\n\n"
                       "instead.")

class TestTypesAndAnnotation(JitTestCase):
    def test_types_as_values(self):
        def fn(m: torch.Tensor) -> torch.device:
            return m.device

        self.checkScript(fn, [torch.randn(2, 2)])

        GG = namedtuple('GG', ['f', 'g'])

        class Foo(torch.nn.Module):
            def __init__(self):
                super().__init__()

            @torch.jit.ignore
            def foo(self, x: torch.Tensor, z: torch.Tensor) -> Tuple[GG, GG]:
                return GG(x, z), GG(x, z)

            def forward(self, x, z):
                return self.foo(x, z)

        foo = torch.jit.script(Foo())
        y = foo(torch.randn(2, 2), torch.randn(2, 2))

        class Foo(torch.nn.Module):
            def __init__(self):
                super().__init__()

            @torch.jit.ignore
            def foo(self, x, z) -> Tuple[GG, GG]:
                return GG(x, z)

            def forward(self, x, z):
                return self.foo(x, z)

        foo = torch.jit.script(Foo())
        y = foo(torch.randn(2, 2), torch.randn(2, 2))

    def test_ignore_with_types(self):
        @torch.jit.ignore
        def fn(x: Dict[str, Optional[torch.Tensor]]):
            return x + 10

        class M(torch.nn.Module):
            def __init__(self):
                super(M, self).__init__()

            def forward(self, in_batch: Dict[str, Optional[torch.Tensor]]) -> torch.Tensor:
                self.dropout_modality(in_batch)
                fn(in_batch)
                return torch.tensor(1)

            @torch.jit.ignore
            def dropout_modality(self, in_batch: Dict[str, Optional[torch.Tensor]]) -> Dict[str, Optional[torch.Tensor]]:
                return in_batch

        sm = torch.jit.script(M())
        FileCheck().check("dropout_modality").check("in_batch").run(str(sm.graph))

    def test_python_callable(self):
        class MyPythonClass(object):
            @torch.jit.ignore
            def __call__(self, *args) -> str:
                return str(type(args[0]))

        the_class = MyPythonClass()

        @torch.jit.script
        def fn(x):
            return the_class(x)

        # This doesn't involve the string frontend, so don't use checkScript
        x = torch.ones(2)
        self.assertEqual(fn(x), the_class(x))

    def test_bad_types(self):
        @torch.jit.ignore
        def fn(my_arg):
            return my_arg + 10

        with self.assertRaisesRegex(RuntimeError, "argument 'my_arg'"):
            @torch.jit.script
            def other_fn(x):
                return fn('2')

    def test_type_annotate_py3(self):
        def fn():
            a : List[int] = []
            b : torch.Tensor = torch.ones(2, 2)
            c : Optional[torch.Tensor] = None
            d : Optional[torch.Tensor] = torch.ones(3, 4)
            for _ in range(10):
                a.append(4)
                c = torch.ones(2, 2)
                d = None
            return a, b, c, d

        self.checkScript(fn, ())

        def wrong_type():
            wrong : List[int] = [0.5]
            return wrong

        with self.assertRaisesRegex(RuntimeError, "Lists must contain only a single type"):
            torch.jit.script(wrong_type)

    def test_optional_no_element_type_annotation(self):
        """
        Test that using an optional with no contained types produces an error.
        """
        def fn_with_comment(x: torch.Tensor) -> Optional:
            return (x, x)

        def annotated_fn(x: torch.Tensor) -> Optional:
            return (x, x)

        with self.assertRaisesRegex(RuntimeError, r"Attempted to use Optional without a contained type"):
            cu = torch.jit.CompilationUnit()
            cu.define(dedent(inspect.getsource(fn_with_comment)))

        with self.assertRaisesRegex(RuntimeError, r"Attempted to use Optional without a contained type"):
            cu = torch.jit.CompilationUnit()
            cu.define(dedent(inspect.getsource(annotated_fn)))

        with self.assertRaisesRegex(RuntimeError, r"Attempted to use Optional without a contained type"):
            torch.jit.script(fn_with_comment)

        with self.assertRaisesRegex(RuntimeError, r"Attempted to use Optional without a contained type"):
            torch.jit.script(annotated_fn)

    def test_tuple_no_element_type_annotation(self):
        """
        Test that using a tuple with no contained types produces an error.
        """
        def fn_with_comment(x: torch.Tensor) -> Tuple:
            return (x, x)

        def annotated_fn(x: torch.Tensor) -> Tuple:
            return (x, x)

        with self.assertRaisesRegex(RuntimeError, r"Attempted to use Tuple without a contained type"):
            cu = torch.jit.CompilationUnit()
            cu.define(dedent(inspect.getsource(fn_with_comment)))

        with self.assertRaisesRegex(RuntimeError, r"Attempted to use Tuple without a contained type"):
            cu = torch.jit.CompilationUnit()
            cu.define(dedent(inspect.getsource(annotated_fn)))

        with self.assertRaisesRegex(RuntimeError, r"Attempted to use Tuple without a contained type"):
            torch.jit.script(fn_with_comment)

        with self.assertRaisesRegex(RuntimeError, r"Attempted to use Tuple without a contained type"):
            torch.jit.script(annotated_fn)

    def test_ignoring_module_attributes(self):
        """
        Test that module attributes can be ignored.
        """
        class Sub(torch.nn.Module):
            def __init__(self):
                super().__init__()

            def forward(self, a: int) -> int:
                return sum([a])

        class ModuleWithIgnoredAttr(torch.nn.Module):
            __jit_ignored_attributes__ = ["a", "sub"]

            def __init__(self, a: int, b: int):
                super().__init__()
                self.a = a
                self.b = b
                self.sub = Sub()

            def forward(self) -> int:
                return self.b

            @torch.jit.ignore
            def ignored_fn(self) -> int:
                return self.sub.forward(self.a)

        mod = ModuleWithIgnoredAttr(1, 4)
        scripted_mod = torch.jit.script(mod)
        self.assertEqual(scripted_mod(), 4)
        self.assertEqual(scripted_mod.ignored_fn(), 1)

        # Test the error message for ignored attributes.
        class ModuleUsesIgnoredAttr(torch.nn.Module):
            __jit_ignored_attributes__ = ["a", "sub"]

            def __init__(self, a: int):
                super().__init__()
                self.a = a
                self.sub = Sub()

            def forward(self) -> int:
                return self.sub(self.b)

        mod = ModuleUsesIgnoredAttr(1)

        with self.assertRaisesRegexWithHighlight(RuntimeError, r"attribute was ignored during compilation", "self.sub"):
            scripted_mod = torch.jit.script(mod)

    def test_unimported_type_resolution(self):
        # verify fallback from the python resolver to the c++ resolver

        @ torch.jit.script
        def fn(x):
            # type: (number) -> number
            return x + 1

        FileCheck().check('Scalar').run(fn.graph)

    def test_parser_bug(self):
        def parser_bug(o: Optional[torch.Tensor]):
            pass

    def test_mismatched_annotation(self):
        with self.assertRaisesRegex(RuntimeError, 'annotated with type'):
            @torch.jit.script
            def foo():
                x : str = 4
                return x

    def test_reannotate(self):
        with self.assertRaisesRegex(RuntimeError, 'declare and annotate'):
            @torch.jit.script
            def foo():
                x = 5
                if 1 == 1:
                    x : Optional[int] = 7