# -*- coding: utf-8; -*-
"""AST splicing utilities."""

__all__ = ["splice_statements", "splice_dialect"]

import ast
from copy import deepcopy

from .coreutils import ismacroimport
from .walker import Walker


def splice_statements(body, template, tag="__paste_here__"):
    """Splice `body` into `template`.

    This is somewhat like `mcpy.quotes.a`, but must be called from outside the
    quoted snippet, and splices statements (from a `list` of AST nodes) instead
    of a single expression AST node.

    Parameters:

        `body`: `list` of statements
            The statements you would like to splice in.

        `template`: `list` of statements
            Template into which to splice `body`.

            Must contain a paste-here indicator AST node, in a statement position,
            that specifies where `body` is to be spliced in. The node is expected
            to have the format::

                ast.Expr(value=ast.Name(id=tag))

            Or in plain English, it's a bare identifier in a statement position.

            The first-found instance (in AST scan order) of the paste-here indicator
            is replaced by `body`.

            If the paste-here indicator appears multiple times, second and further
            instances are replaced with a `copy.deepcopy` of `body` so that they will
            stay independent during any further AST edits.

        `tag`: `str`
            The name of the paste-here indicator in `template`.

    Returns `template` with `body` spliced in. Note `template` is **not** copied.

    Example::

        from mcpy.quotes import macros, q
        from mcpy.splicing import splice_statements

        body = [...]  # a list of statements

        with q as template:
            ...
            __paste_here__
            ...

        splice_statements(body, template)

    (Flake8 will complain about the undefined name `__paste_here__`. You can silence
     it with the appropriate `# noqa`, or to make it happy, import the `n` macro from
     `mcpy.quotes` and use `n["__paste_here__"]` instead of a plain `__paste_here__`.)
    """
    if isinstance(body, ast.AST):
        body = [body]
    if isinstance(template, ast.AST):
        body = [template]
    if not body:
        raise ValueError("expected at least one statement in `body`")
    if not template:
        return body

    def ispastehere(tree):
        return type(tree) is ast.Expr and type(tree.value) is ast.Name and tree.value.id == tag

    class StatementSplicer(Walker):
        def __init__(self):
            self.first = True
            super().__init__()

        def transform(self, tree):
            if ispastehere(tree):
                if not self.first:
                    return deepcopy(body)
                self.first = False
                return body
            return self.generic_visit(tree)

    return StatementSplicer().visit(template)


def splice_dialect(body, template, tag="__paste_here__"):
    """In a dialect AST transformer, splice module `body` into `template`.

    On top of what `splice_statements` does, this function handles macro-imports
    specially, gathering them all at the top level of the final module body, so
    that mcpy sees them when the module is sent to the macro expander.

    Any macro-imports in the template are placed first (in the order they
    appear in the template), followed by any macro imports in the user code
    (in the order they appear in the user code).

    This also handles the module docstring and the magic `__all__` (if any)
    from `body`, placing them at the top.

    Parameters:

        `body`: `list` of statements
            Original module body from the user code (input).

        `template`: `list` of statements
            Template for the final module body (output).

            Must contain a paste-here indicator as in `splice_statements`.

        `tag`: `str`
            The name of the paste-here indicator in `template`.

    Returns `template` with `body` spliced in. Note `template` is **not** copied.
    """
    if isinstance(body, ast.AST):
        body = [body]
    if isinstance(template, ast.AST):
        body = [template]
    if not body:
        raise ValueError("expected at least one statement in `body`")
    if not template:
        return body

    # Generally speaking, dialect templates are fully macro-generated
    # quasiquoted snippets with no source location info to start with.
    # Pretend it's at the beginning of the user module.
    #
    # The dialect expander runs before the macro expander, so it's our job to
    # give its source location filling logic something sensible to work with.
    for stmt in template:
        ast.copy_location(stmt, body[0])
        ast.fix_missing_locations(stmt)

    # TODO: remove ast.Str once we bump minimum language version to Python 3.8
    if type(body[0]) is ast.Expr and type(body[0].value) in (ast.Constant, ast.Str):
        docstring, *body = body
        docstring = [docstring]
    else:
        docstring = []

    def extract_magic_all(tree):
        def ismagicall(tree):
            if not (type(tree) is ast.Assign and len(tree.targets) == 1):
                return False
            target = tree.targets[0]
            return type(target) is ast.Name and target.id == "__all__"
        class MagicAllExtractor(Walker):
            def transform(self, tree):
                if ismagicall(tree):
                    self.collect(tree)
                    return None
                # We get just the top level of body by not recursing.
                return tree
        w = MagicAllExtractor()
        w.visit(tree)
        return tree, w.collected
    body, user_magic_all = extract_magic_all(body)

    def extract_macroimports(tree):
        class MacroImportExtractor(Walker):
            def transform(self, tree):
                if ismacroimport(tree):
                    self.collect(tree)
                    return None
                return self.generic_visit(tree)
        w = MacroImportExtractor()
        w.visit(tree)
        return tree, w.collected
    template, template_macro_imports = extract_macroimports(template)
    body, user_macro_imports = extract_macroimports(body)

    finalbody = splice_statements(body, template, tag)
    return docstring + user_magic_all + template_macro_imports + user_macro_imports + finalbody