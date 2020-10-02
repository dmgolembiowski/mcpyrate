# -*- coding: utf-8; -*-
'''Find and expand macros.

This layer provides the actual macro expander, defining:

 - Macro invocation types:
   - expr: `macroname[...]`,
   - block: `with macroname:`,
   - decorator: `@macroname`,
   - name: `macroname`.
 - Syntax for establishing macro bindings:
   - `from module import macros, ...`.
'''

__all__ = ['expand_macros', 'find_macros',
           'MacroExpander', 'MacroCollector',
           'namemacro', 'isnamemacro']

import importlib
import pathlib
import sys
import os
from ast import (Name, Import, ImportFrom, alias, AST, Expr, Constant,
                 copy_location, iter_fields, NodeVisitor)
from .core import BaseMacroExpander, global_postprocess, Done

class MacroExpander(BaseMacroExpander):
    '''The actual macro expander.'''

    def visit_Subscript(self, subscript):
        '''Detect an expression (expr) macro invocation.

        Detected syntax::

            macroname['index expression is the target of the macro']

        Replace the `SubScript` node with the result of the macro.
        '''
        rootdir = subscript.value
        if isinstance(rootdir, Name) and self.ismacroname(rootdir.id):
            macroname = rootdir.id
            tree = subscript.slice.value
            new_tree = self.expand('expr', subscript, macroname, tree, fill_root_location=True)
        else:
            new_tree = self.generic_visit(subscript)

        return new_tree

    def visit_With(self, withstmt):
        '''Detect a block macro invocation.

        Detected syntax::

            with macroname:
                "with's body is the target of the macro"

        Replace the `With` node with the result of the macro.
        '''
        with_item = withstmt.items[0]
        rootdir = with_item.context_expr
        if isinstance(rootdir, Name) and self.ismacroname(rootdir.id):
            macroname = rootdir.id
            tree = withstmt.body
            kw = {'optional_vars': with_item.optional_vars}
            new_tree = self.expand('block', withstmt, macroname, tree, fill_root_location=False, kw=kw)
            new_tree = _add_coverage_dummy_node(new_tree, withstmt)
        else:
            new_tree = self.generic_visit(withstmt)

        return new_tree

    def visit_ClassDef(self, classdef):
        return self._visit_Decorated(classdef)

    def visit_FunctionDef(self, functiondef):
        return self._visit_Decorated(functiondef)

    def _visit_Decorated(self, decorated):
        '''Detect a decorator macro invocation.

        Detected syntax::

            @macroname
            def f():
                "The whole function is the target of the macro"

        Or::

            @macroname
            class C():
                "The whole class is the target of the macro"

        Replace the whole decorated node with the result of the macro.
        '''
        macros, others = self._detect_decorator_macros(decorated.decorator_list)
        decorated.decorator_list = others
        if macros:
            macros_executed = []
            for macro in reversed(macros):
                macroname = macro.id
                new_tree = self.expand('decorator', decorated, macroname, decorated, fill_root_location=False)
                macros_executed.append(macro)
                if new_tree is None:
                    break
            for macro in macros_executed:
                new_tree = _add_coverage_dummy_node(new_tree, macro)
        else:
            new_tree = self.generic_visit(decorated)

        return new_tree

    def _detect_decorator_macros(self, decorator_list):
        '''Identify macros in a `decorator_list`.

        Return a pair `(macros, others)`, where `macros` is a `list` of macro
        decorator AST nodes, and `others` is a `list` of the decorator AST
        nodes not identified as macros. Ordering is preserved within each
        of the two subsets.
        '''
        macros, others = [], []
        for d in decorator_list:
            if isinstance(d, Name) and self.ismacroname(d.id):
                macros.append(d)
            else:
                others.append(d)

        return macros, others

    def visit_Name(self, name):
        '''Detect an identifier (name) macro invocation.

        Detected syntax::

            macroname

        The `Name` node itself is the input tree for the macro.
        Replace the `Name` node with the result of the macro.

        Macro functions that want to get called as an identifier macro must
        be declared. Use the `@mcpy.namemacro` decorator, place it outermost.

        The main use case of identifier macros is to define magic variables
        that are valid only inside the invocation of some other macro.
        An classic example is the anaphoric if's `it`.

        Another use case is where you just need to paste some boilerplate
        code without any parameters.
        '''
        if self.ismacroname(name.id) and isnamemacro(self.bindings[name.id]):
            macroname = name.id
            def ismodified(tree):
                return not (type(tree) is Name and tree.id == macroname)
            # For identifier macros, no part of the tree is guaranteed to be compiled away.
            # So prevent an infinite loop if the macro no-ops, returning `tree` as-is.
            # (That's the public API for "I did what I needed to, now go ahead and use this
            #  as a regular run-time identifier").
            with self._recursive_mode(False):
                new_tree = self.expand('name', name, macroname, name, fill_root_location=True)
            if self.recursive and new_tree is not None:
                if ismodified(new_tree):
                    new_tree = self.visit(new_tree)
                else:
                    # When a magic variable expands in a valid surrounding context and does
                    # `return tree`, the expander needs to know it has applied its context check,
                    # so it shouldn't be expanded again (when expanding remaining macros in the result).
                    new_tree = Done(new_tree)
        else:
            new_tree = self.generic_visit(name)

        return new_tree


class MacroCollector(NodeVisitor):
    '''Scan `tree` for macro invocations, with respect to given `expander`.

    Collect a set of `(macroname, syntax)`. Constructor parameters:

        - `expander`: a `MacroExpander` instance to query macro bindings from.

    Usage::

        mc = MacroCollector(expander)
        mc.visit(tree)
        print(mc.collected)
        # ...do something to tree...
        mc.clear()
        mc.visit(tree)
        print(mc.collected)

    This is a sister class of the actual `MacroExpander`, mirroring its macro
    invocation syntax detection.
    '''
    def __init__(self, expander):
        self.expander = expander
        self.clear()

    def clear(self):
        self.collected = set()

    def ismacroname(self, name):
        return self.expander.ismacroname(name)

    def visit_Subscript(self, subscript):
        rootdir = subscript.value
        if isinstance(rootdir, Name) and self.ismacroname(rootdir.id):
            self.collected.add((rootdir.id, 'expr'))
        # We can't just `self.generic_visit(subscript)`, because that'll incorrectly detect
        # the name part of the invocation as an identifier macro. So recurse only where safe.
        self.visit(subscript.slice.value)

    def visit_With(self, withstmt):
        with_item = withstmt.items[0]
        rootdir = with_item.context_expr
        if isinstance(rootdir, Name) and self.ismacroname(rootdir.id):
            self.collected.add((rootdir.id, 'block'))
        self.visit(withstmt.body)

    def visit_ClassDef(self, classdef):
        self._visit_Decorated(classdef)

    def visit_FunctionDef(self, functiondef):
        self._visit_Decorated(functiondef)

    def _visit_Decorated(self, decorated):
        macros, decorators = self.expander._detect_decorator_macros(decorated.decorator_list)
        for macro in macros:
            self.collected.add((macro.id, 'decorator'))
        for decorator in decorators:
            self.visit(decorator)
        for field, value in iter_fields(decorated):
            if field == "decorator_list":
                continue
            if isinstance(value, list):
                for node in value:
                    self.visit(node)
            elif isinstance(value, AST):
                self.visit(value)

    def visit_Name(self, name):
        if self.ismacroname(name.id) and isnamemacro(self.expander.bindings[name.id]):
            self.collected.add((name.id, 'name'))
        self.generic_visit(name)


def _add_coverage_dummy_node(tree, target):
    '''Force `target` node to be reported as covered by coverage tools.

    Fixes coverage reporting for block and decorator macro invocations.

    `tree` must appear in a position where `ast.NodeTransformer.visit` is
    allowed to return a list of nodes. The return value is a `list` of nodes.
    '''
    # `target` itself might be macro-generated. In that case don't bother.
    if not hasattr(target, 'lineno') and not hasattr(target, 'col_offset'):
        return tree
    if tree is None:
        tree = []
    elif isinstance(tree, AST):
        tree = [tree]
    # The dummy node must actually run to get coverage, an `ast.Pass` won't do.
    # We must set location info manually, because we run after `expand`.
    non = copy_location(Constant(value=None), target)
    dummy = copy_location(Expr(value=non), target)
    tree.insert(0, Done(dummy))  # mark as Done so any expansions further out won't mess this up.
    return tree


def expand_macros(tree, bindings, filename):
    '''
    Return an expanded version of `tree` with macros applied.
    Perform top-level postprocessing when done.

    This is meant to be called with `tree` the AST of a module that uses macros.

    `bindings` is a dictionary of the macro name/function pairs.

    `filename` is the full path to the `.py` being macroexpanded, for error reporting.
    '''
    expansion = MacroExpander(bindings, filename).visit(tree)
    expansion = global_postprocess(expansion)
    return expansion


def find_macros(tree, filename, reload=False):
    '''
    Look for `from ... import macros, ...` statements in the module body, and
    return a dict with names and implementations for found macros, or an empty
    dict if no macros are used.

    As a side effect, transform each macro import statement into `import ...`,
    where `...` is the module the macros are being imported from.

    This is meant to be called with `tree` the AST of a module that uses macros.

    `filename` is the full path to the `.py` being macroexpanded, for error reporting.

    `reload=True` can be used to force a module reload for the macro definition modules.
    This is useful in interactive use.
    '''
    bindings = {}
    for index, statement in enumerate(tree.body):
        if _is_macro_import(statement):
            module_fullname, more_bindings = _get_macros(statement, filename, reload=reload)
            bindings.update(more_bindings)
            # Remove all names to prevent the macros being accidentally used as regular run-time objects.
            # Always use an absolute import so that the unhygienic expose API guarantee works.
            # (E.g. even if `from .quotes import macros, q`, the module will be exposed as `mcpy.quotes`,
            #  not just `quotes`.)
            tree.body[index] = copy_location(Import(names=[alias(name=module_fullname, asname=None)]),
                                             statement)

    return bindings

def _is_macro_import(statement):
    '''
    A "macro import" is a statement of the form::

        from ... import macros, ...
    '''
    is_macro_import = False
    if isinstance(statement, ImportFrom):
        firstimport = statement.names[0]
        if firstimport.name == 'macros' and firstimport.asname is None:
            is_macro_import = True

    return is_macro_import

def _get_macros(macroimport, filename, reload=False):
    '''Get module name, macro names and macro functions from the macro import statement.

    As a side effect, import the macro definition module.

    `filename` is the full path to the `.py` being macroexpanded,
    used for resolving relative imports.

    `reload=True` can be used to force a module reload for the macro definition module.
    This is useful in interactive use.

    Return value is `(module_fullname, {macro_name: macro_function, ...})`.
    '''
    lineno = macroimport.lineno if hasattr(macroimport, "lineno") else None
    if macroimport.module is None:
        raise SyntaxError(f"{filename}:{lineno}: missing module name in macro-import")

    package = None
    if macroimport.level:
        try:
            package = _resolve_package(filename)
        except ValueError:
            raise SyntaxError(f"{filename}:{lineno}: relative import outside any package")
        except ImportError:
            raise ImportError(f"{filename}:{lineno}: could not determine containing package to resolve relative import")

    module_fullname = importlib.util.resolve_name('.' * macroimport.level + macroimport.module, package)
    module = importlib.import_module(module_fullname)
    if reload:
        module = importlib.reload(module)

    return module_fullname, {name.asname or name.name: getattr(module, name.name)
                             for name in macroimport.names[1:]}

def _resolve_package(filename):  # TODO: for now, _guess_package, really. Check the docs again.
    """Resolve absolute Python package name for .py source file `filename`."""
    pyfiledir = pathlib.Path(filename).expanduser().resolve().parent
    for rootdir in sys.path:
        rootdir = pathlib.Path(rootdir).expanduser().resolve()
        if str(pyfiledir).startswith(str(rootdir)):
            package_relative_path = str(pyfiledir)[len(str(rootdir)):]
            if not package_relative_path:  # at the rootdir - not inside a package
                raise ValueError(f"{filename} not in package, is at root level of {str(rootdir)}")
            package_relative_path = package_relative_path[1:]  # drop the initial path sep
            package_dotted_name = package_relative_path.replace(os.path.sep, '.')
            return package_dotted_name
    raise ImportError(f"{filename} not under any directory in `sys.path`")

def namemacro(function):
    '''Decorator. Declare a macro function as an identifier macro.

    Since identifier macros are a rarely needed feature, only macros that are
    declared as such will be called as identifier macros.

    This must be the outermost decorator.
    '''
    function._isnamemacro = True
    return function

def isnamemacro(function):
    '''Return whether the macro function `function` has been declared as an identifier macro.'''
    return hasattr(function, '_isnamemacro')
