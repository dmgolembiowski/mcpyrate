# -*- coding: utf-8; -*-
'''Find and expand dialects, i.e. whole-module source and AST transformations.'''

# TODO: add single-stepping for debugging, like in `MacroExpander`.
#   - We could have one built-in "dialect" (expander feature, rather) that tells the expander
#     to single-step the rest.
# TODO: support dialects in repl? Need to first figure out what that would even mean...

__all__ = ["Dialect",
           "expand_dialects"]

import ast
from collections import deque
import re
import tokenize

from .exutilities import ismacroimport, get_macros

class Dialect:
    '''Base class for dialects.'''

    def transform_source(text):
        '''Override this to add a whole-module source transformer to your dialect.

        Input is the full source text of the module, as a string. Output should be
        the transformed source text, as a string.
        '''
        return text

    def transform_ast(tree):
        '''Override this to add a whole-module AST transformer to your dialect.

        Input is the full AST of the module, but with the dialect-import for this
        dialect already transformed away. Output should be the transformed AST.
        '''
        return tree


_dialectimport = re.compile(r"^from\s+([.0-9a-zA-z_]+)\s+import dialects,\s+([^(\\]+)$",
                            flags=re.MULTILINE)
class DialectExpander:
    '''The actual dialect expander.'''

    def __init__(self, filename):
        '''`filename`: full path to `.py` file being expanded, for module name resolution and error messages.'''
        self.filename = filename
        self._seen = set()

    def expand(self, data):
        '''Expand dialects in `data` (bytes) corresponding to `self.filename`. Top-level entrypoint.

        Dialects are expanded until no dialects remain.
        '''
        text = _decode_source_content(data)
        text = self.transform_source(text)
        tree = ast.parse(data)  # TODO: error out gracefully if this fails
        return self.transform_ast(tree)

    def transform_source(self, text):
        '''Apply all whole-module source transformers.'''
        while True:
            module_absname, bindings = self.find_dialectimport_source(text)
            if not module_absname:
                break
            if not bindings:
                continue

            for dialectname, cls in bindings.items():
                if not isinstance(cls, Dialect):
                    raise TypeError(f"{self.filename}: {module_absname}.{dialectname} is not a `Dialect`, got {repr(cls)}")
                dialect = cls()
                text = dialect.transform_source(text)
                # TODO: error out if empty text or None returned
        return text

    def transform_ast(self, tree):
        '''Apply all whole-module AST transformers.'''
        while True:
            module_absname, bindings = self.find_dialectimport_ast(tree)
            if not module_absname:
                break
            if not bindings:
                continue

            for dialectname, cls in bindings.items():
                if not isinstance(cls, Dialect):
                    raise TypeError(f"{self.filename}: {module_absname}.{dialectname} is not a `Dialect`, got {repr(cls)}")
                dialect = cls()
                tree = dialect.transform_ast(tree)
                # TODO: error out if None returned
        return tree

    def find_dialectimport_source(self, text):
        '''Find the first dialect-import statement by scanning source code `text`.

        As a side effect, import the dialect definition module.

        A dialect-import is a statement of the form::

            from ... import dialects, ...

        To keep the search simple, the dialect-import **must**:

          - Be on a single line; not use parentheses or a line continuation.
          - Start at the first column on the line where it appears.

        When this runs, the input is just text. It is not parseable by `ast.parse`,
        because a dialect that has a source transformer may introduce new surface
        syntax. Similarly, it's not tokenizable by `tokenize`, because a dialect
        may customize what constitutes a token.

        So we can only rely on the literal text "from ... import dialects, ...",
        similarly to how Racket heavily constrains the format of its `#lang` line.

        Return value is a dict `{dialectname: class, ...}` with all collected bindings
        from that one dialect-import. Each binding is a dialect, so usually there is
        just one.
        '''
        matches = _dialectimport.finditer(text)
        try:
            while True:
                match = next(matches)
                statement, *groups = list(match)
                if statement not in self._seen:  # apply each unique dialect-import once
                    self._seen.add(statement)
                    break
        except StopIteration:
            return "", {}

        dialectimport = ast.parse(statement)
        module_absname, bindings = get_macros(dialectimport, filename=self.filename,
                                              reload=False, allow_asname=False)
        return module_absname, bindings

    def find_dialectimport_ast(self, tree):
        '''Find the first dialect-import statement by scanning the AST `tree`.

        Transform the dialect-import into `import ...`, where `...` is the absolute
        module name the dialects are being imported from.

        As a side effect, import the dialect definition module.

        A dialect-import is a statement of the form::

            from ... import dialects, ...

        Return value is a dict `{dialectname: class, ...}` with all collected bindings
        from that one dialect-import. Each binding is a dialect, so usually there is
        just one.
        '''
        for index, statement in enumerate(tree.body):
            if ismacroimport(statement, magicname="dialects"):
                break
        else:
            return "", {}

        module_absname, bindings = get_macros(statement, filename=self.filename,
                                              reload=False, allow_asname=False)
        # Remove all names to prevent dialects being used as regular run-time objects.
        # Always use an absolute import, for the unhygienic expose API guarantee.
        tree.body[index] = ast.copy_location(ast.Import(names=[ast.alias(name=module_absname, asname=None)]),
                                             statement)
        return module_absname, bindings


def _decode_source_content(data):
    '''Decode a .py source file from bytes to string, parsing the encoding tag like `tokenize`.'''
    lines = deque(data.split(b"\n"))
    def readline():
        return lines.popleft()
    encoding, lines_read = tokenize.detect_encoding(readline)
    return data.decode(encoding)

# --------------------------------------------------------------------------------

def expand_dialects(data, *, filename):
    '''Find and expand dialects, i.e. whole-module source and AST transformers.

    The algorithm works as follows.

    We take the first not-yet-seen dialect-import statement, apply its source
    transformers left-to-right, and repeat (each time rescanning the text from
    the beginning) until the source transformers of all dialect-imports have
    been applied.

    Then, we take the first dialect-import statement at the top level of the
    module, transform it away (into a module import), and apply its AST
    transformers left-to-right. We then repeat (each time rescanning the AST
    from the beginning) until the AST transformers of all dialect-imports have
    been applied.

    Then we return `tree`; it may still have macros, but no more dialects.

    Note that a source transformer may edit the full source, including any
    dialect-imports. This will change which dialects get applied. If it removes
    its own dialect-import, that will cause it to skip its AST transformer.
    If it adds any new dialect-imports, those will get processed as encountered.

    Similarly, an AST transformer may edit the full module AST, including any
    remaining dialect-imports. If it removes any, those AST transformers will
    be skipped. If it adds any, those will get processed as encountered.
    '''
    dexpander = DialectExpander(filename)
    return dexpander.expand(data)

# --------------------------------------------------------------------------------

# TODO: essential utility, port to mcpy. Maybe move somewhere?

# def splice_ast(body, template, tag):
#     """In an AST transformer, splice module body into template.
#
#     Imports for MacroPy macros are handled specially, gathering them all at the
#     front, so that MacroPy sees them. Any macro imports in the template are
#     placed first (in the order they appear in the template), followed by any
#     macro imports in the user code (in the order they appear in the user code).
#
#     This function is provided as a convenience for modules that define dialects.
#     We use MacroPy to perform the splicing, so this function is only available
#     when MacroPy is installed (``ImportError`` is raised if not). Installation
#     status is checked only once per session, when ``dialects.util`` is first
#     imported.
#
#     Parameters:
#
#         ``body``: ``list`` of statements
#             Module body of the original user code (input).
#
#         ``template``: ``list`` of statements
#             Template for the module body of the new module (output).
#
#             Must contain a marker that indicates where ``body`` is to be
#             spliced in. The marker is an ``ast.Name`` node whose ``id``
#             attribute matches the value of the ``tag`` string.
#
#         ``tag``: ``str``
#             The value of the ``id`` attribute of the marker in ``template``.
#
#     Returns the new module body, i.e. ``template`` with ``body`` spliced in.
#
#     Example::
#
#         marker = q[name["__paste_here__"]]      # MacroPy, or...
#         marker = ast.Name(id="__paste_here__")  # ...manually
#
#         ...  # create template, place the marker in it
#
#         dialects.util.splice_ast(body, template, "__paste_here__")
#
#     """
#     if not Walker:  # optional dependency for Pydialect, but mandatory for this util
#         raise ImportError("macropy.core.walkers.Walker not found; MacroPy likely not installed")
#     if not body:  # ImportError because this occurs during the loading of a module written in a dialect.
#         raise ImportError("expected at least one statement or expression in module body")
#
#     def is_paste_here(tree):
#         return type(tree) is Expr and type(tree.value) is Name and tree.value.id == tag
#     def is_macro_import(tree):
#         return type(tree) is ImportFrom and tree.names[0].name == "macros"
#
#     # XXX: MacroPy's debug logger will sometimes crash if a node is missing a source location.
#     # In general, dialect templates are fully macro-generated with no source location info to start with.
#     # Pretend it's all at the start of the user module.
#     locref = body[0]
#     @Walker
#     def fix_template_srcloc(tree, **kw):
#         if not all(hasattr(tree, x) for x in ("lineno", "col_offset")):
#             tree = copy_location(tree, locref)
#         return tree
#
#     @Walker
#     def extract_macro_imports(tree, *, collect, **kw):
#         if is_macro_import(tree):
#             collect(tree)
#             tree = copy_location(Pass(), tree)  # must output a node so replace by a pass stmt
#         return tree
#
#     template = fix_template_srcloc.recurse(template)
#     template, template_macro_imports = extract_macro_imports.recurse_collect(template)
#     body, user_macro_imports = extract_macro_imports.recurse_collect(body)
#
#     @Walker
#     def splice_body_into_template(tree, *, stop, **kw):
#         if not is_paste_here(tree):
#             return tree
#         stop()  # prevent infinite recursion in case the user code contains a Name that looks like the marker
#         return If(test=Num(n=1),
#                   body=body,
#                   orelse=[],
#                   lineno=tree.lineno, col_offset=tree.col_offset)
#     finalbody = splice_body_into_template.recurse(template)
#     return template_macro_imports + user_macro_imports + finalbody
