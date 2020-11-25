# -*- coding: utf-8; -*-
"""Hygienic macro recursion."""

from mcpyrate.multiphase import macros, phase
from mcpyrate.debug import macros, step_expansion  # noqa: F811

with phase[1]:
    from mcpyrate.quotes import macros, q, u, a  # noqa: F811, F401

    import ast

    from mcpyrate.quotes import capture_as_macro

    def even(tree, **kw):
        if type(tree) is ast.Constant:
            v = tree.value
        elif type(tree) is ast.Num:  # up to Python 3.7
            v = tree.n

        if v == 0:
            return q[True]
        return q[a[our_odd][u[v - 1]]]

    def odd(tree, **kw):
        if type(tree) is ast.Constant:
            v = tree.value
        elif type(tree) is ast.Num:  # up to Python 3.7
            v = tree.n

        if v == 0:
            return q[False]
        return q[a[our_even][u[v - 1]]]

    # This is the magic part: capture macro functions manually to make hygienic
    # references, without caring about macro-imports at the use site.
    our_even = capture_as_macro(even)
    our_odd = capture_as_macro(odd)


from __self__ import macros, even, odd  # noqa: F811, F401

def demo():
    with step_expansion:
        assert even[4]

    with step_expansion:
        assert not odd[4]

if __name__ == '__main__':
    demo()
