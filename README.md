# mcpy

Third-generation macro expander for Python, after the pioneering [macropy](https://github.com/lihaoyi/macropy), and the compact, pythonic [original mcpy](https://github.com/delapuente/mcpy).

The design philosophy follows the original `mcpy`: keep things as explicit and compact as reasonably possible. However, the codebase is larger due to having more features. We also tolerate a small amount of extra complexity, if it improves the programmer [UX](https://en.wikipedia.org/wiki/User_experience).

Supports Python 3.6, 3.7, 3.8, and PyPy3.

<!-- markdown-toc start - Don't edit this section. Run M-x markdown-toc-refresh-toc -->
**Table of Contents**

- [mcpy](#mcpy)
    - [Highlights](#highlights)
    - [Install & uninstall](#install--uninstall)
    - [Using macros](#using-macros)
        - [REPL](#repl)
        - [Syntax](#syntax)
        - [Importing macros](#importing-macros)
    - [Writing macros](#writing-macros)
        - [Distinguish how the macro is called](#distinguish-how-the-macro-is-called)
        - [The named parameters](#the-named-parameters)
        - [Macro arguments](#macro-arguments)
            - [Arguments or no arguments?](#arguments-or-no-arguments)
        - [Quasiquotes](#quasiquotes)
        - [Walk an AST](#walk-an-ast)
            - [Identifier macros](#identifier-macros)
        - [Get the source of an AST](#get-the-source-of-an-ast)
        - [Expand macros](#expand-macros)
        - [Macro expansion error reporting](#macro-expansion-error-reporting)
        - [Examples](#examples)
    - [Understanding the code](#understanding-the-code)

<!-- markdown-toc end -->

## Highlights

This fork adds a lot of features over `mcpy` 2.0.0:

- **Agile development**:
  - Universal bootstrapper: `macropython`. **Import and use macros in your main program**.
  - Interactive console: `macropython -i`. **Import and use macros in a console session**.
    - Embeddable à la `code.InteractiveConsole`. See `mcpy.repl.console.MacroConsole`.
  - IPython extension `mcpy.repl.iconsole`. **Import and use macros in an IPython session**.
- **Testing and debugging**:
  - Statement coverage is correctly reported by tools such as [`Coverage.py`](https://github.com/nedbat/coveragepy/).
  - Macro expansion errors are reported **at macro expansion time**, with use site traceback.
  - Debug output with a step-by-step expansion breakdown. See macro `mcpy.debug.step_expansion`.
  - Manual expand-once. See `expander.visit_once`; get the `expander` as a named argument of your macro.
- **Dialects, i.e. whole-module source and AST transforms**.
  - Think [Racket's](https://racket-lang.org/) `#lang`, but for Python.
  - Define languages that use Python's surface syntax, but change the semantics; or plug in a per-module transpiler that (at import time) compiles source code from some other programming language into macro-enabled Python.
  - Sky's the limit, really. Until we get [`unpythonic`](https://github.com/Technologicat/unpythonic) ported to use `mcpy`, see [`pydialect`](https://github.com/Technologicat/pydialect) for old example dialects.
  - For documentation, see the docstrings of [`mcpy.dialects`](mcpy/dialects.py).
  - For debugging, `from mcpy.debug import dialects, StepExpansion`.
- **Advanced quasiquoting**:
  - Hygienically interpolate both regular values **and macro names**.
  - Delayed macro expansion inside quasiquoted code.
    - User-controllable, see macros `expand1` and `expand` in `mcpy.quotes`.
    - Expand when you want, or just leave it to `mcpy` to expand automatically once your macro (that uses quasiquoting) returns.
  - Inverse quasiquote operator. See function `mcpy.quotes.unastify`.
    - Convert a quasiquoted AST back into a direct AST, typically for further processing before re-quoting it.
      - Not an unquote; we have those too, but the purpose of unquotes is to interpolate values into quoted code. The inverse quasiquote, instead, undoes the quasiquote operation itself, after any unquotes have already been applied.
    - Useful for second-order macros that need to process a quasiquoted code section at macro expansion time, before the quasiquoted tree has a chance to run. (As usual, when it runs, it converts itself into a direct AST.)
- **Identifier (a.k.a. name) macros**
  - Can be used for creating magic variables that may only appear inside specific macro invocations, erroring out at macro expansion time if they appear anywhere else.
  - Opt-in. Declare by using the `@namemacro` decorator on your macro function. Place it outermost (along with `@parametricmacro`, if used too).
- **Macro arguments**. Inspired by MacroPy, but slightly different.
  - Opt-in. Declare by using the `@parametricmacro` decorator on your macro function (along with `@namemacro`, if used too).
  - Use bracket syntax to invoke, e.g. `macroname[arg0, ...][expr]`. To send no args, invoke like a non-parametric macro, `macroname[expr]`.
  - For a parametric macro, `macroname[arg0, ...]` works in `expr`, `block` and `decorator` macro invocations in place of a bare `macroname`.
  - The named parameter `args` is a raw `list` of the macro argument ASTs. It is the empty list if no args were sent, or if the macro function is not declared as parametric.
- **Bytecode caching**:
  - `.pyc` bytecode caches are created and kept up-to-date. This saves the macro
    expansion cost at startup for modules that have not changed.

    Beside a `.py` source file itself, we look at any macro definition files
    the source file imports macros from, recursively, in a `make`-like fashion.

    The mtime is the latest of those of the source file and its macro-dependencies,
    considered recursively, so that if any macro definition anywhere in the
    macro-dependency tree of a source file is changed, Python will treat that
    source file as "changed", thus re-expanding and recompiling it (hence,
    updating the corresponding `.pyc`).
  - **CAUTION**: [PEP 552 - Deterministic pycs](https://www.python.org/dev/peps/pep-0552/) is not supported; we support only the default *mtime* invalidation mode, at least for now.
- **Conveniences**:
  - Relative macro-imports (for code in packages), e.g. `from .other import macros, kittify`.
  - The expander automatically fixes missing `ctx` attributes in the AST, so you don't need to care about those in your macros.
  - Several block macros can be invoked in the same `with` (equivalent to nesting them, with leftmost outermost).
  - Walker with a state stack, à la MacroPy, to easily temporarily override the state for a given subtree.
  - AST markers (pseudo-nodes) for communication in a set of co-operating macros (and with the expander).
  - `gensym` to create a fresh, unused lexical identifier.
  - `unparse` to convert an AST to the corresponding source code.
  - `dump` to look at an AST representation directly.


## Install & uninstall

PyPI package will follow later. For now, install from source:

```bash
python -m setup install
```

possibly with `--user`, if your OS is a *nix, and you feel lucky enough to use the system Python. If not, activate your venv first; the `--user` flag is then not needed.

To uninstall:

```bash
pip uninstall mcpy
```

but first, make sure you're not in a folder that has an `mcpy` subfolder - `pip` will think it got a folder name instead of a package name, and become confused.


## Using macros

Due to how `mcpy` works, `mcpy` must be explicitly enabled before importing any module that uses macros. Macros must be defined in a separate module. The following classical 3-file setup works fine:

```python
# run.py
import mcpy.activate
import application

# mymacros.py with your macro definitions
def echo(expr, **kw):
  print('Echo')
  return expr

# application.py 
from mymacros import macros, echo
echo[6 * 7]
```

To run, `python -m run`.

The per-project wrapper `run.py` is optional. You can use the following 2-file setup:

```python
# mymacros.py with your macro definitions
def echo(expr, **kw):
  print('Echo')
  return expr

# application.py
from mymacros import macros, echo
echo[6 * 7]
```

To run, `macropython -m application`. It will import `application`, making that module believe it's `__main__`. (In a sense, it really is: if you look at `sys.modules["__main__"]`, you'll find the `application` module. The conditional main idiom works, too.)

`macropython` will use the `python` interpreter that is currently active according to `/usr/bin/env`. So if you e.g. set up a venv with PyPy3 and activate the venv, `macropython` will use that.


### REPL

For interactive macro-enabled sessions, we provide an mcpy-enabled equivalent for `code.InteractiveConsole`, as well as an IPython extension. See the [REPL system documentation](repl.md).


### Syntax

`mcpy` macros can be used in four forms:

```python
# block form
with macro:
  ...

# expression form
macro[...]

# decorator form
@macro
...

# identifier form
macro
```

In the first three cases, the macro will receive `...` as input. An identifier macro will receive the `Name` AST node itself.

In each case, the expander will replace the invocation with the expanded content. Expansion occurs first for outermost nodes, i.e, from outside to inside.


### Importing macros

In `mcpy`, macros are just functions. To use functions from `module` as macros, use a *macro-import statement*:

```python
from module import macros, ...
```

replacing `...` with the macros you want to use. Importing all via `*` won't work. You must declare the macros you want explicitly. This syntax tells the macro expander to register macro bindings. The macro bindings are in scope for the module in which the macro-import statement appears.

All macro-import statements must appear at the top level of a module.

`mcpy` prevents you from accidentally using macros as regular functions in your code by transforming the macro-import into:

```python
import module
```

The transformed import is always absolute, even if the original macro-import was relative.

This is part of the public API. If the expanded form of your macro needs to refer to `thing` that exists in (whether is defined in, or has been imported to) the global, top-level scope of the module that defines the macro, you can just refer to `module.thing` in your expanded code. This is the `mcpy` equivalent of MacroPy's `unhygienic_expose` mechanism.

If your expansion needs to refer to some other value from the macro definition site (including local and nonlocal variables, and imported macros), see [the quasiquote system](quasiquotes.md), specifically the `h[]` (hygienic-unquote) operator.

If you want to use some of your macros as regular functions, simply use:

```python
from module import ...
```

Or, noting the above guarantee, use fully qualified names for them:

```python
module.macroname
```

If the name of a macro conflicts with a name you can provide an alias for the macro:

```python
from module import macros, macroname as alias
```

This will register the macro binding under the name `alias`.

Note this implies that if one of your macros needs to analyze whether the tree it's expanding is going to invoke specific other macros, then in `expander.bindings`, you **must look at the values** (whether they are the function objects you expect), not at the names (since names can be aliased to anything at the use site).


## Writing macros

No special imports are needed to write your own macros. Just consider a macro as a function accepting an AST `tree` and returning another AST (i.e., the macro function is a [syntax transformer](http://www.greghendershott.com/fear-of-macros/)). Refer to [Green Tree Snakes](https://greentreesnakes.readthedocs.io/en/latest/nodes.html) (a.k.a. the missing Python AST docs) for details on the AST node types. The documentation for the [AST module](https://docs.python.org/3/library/ast.html) may also be occasionally useful.

```python
def macro(tree, **kw): return tree
```

Although you don't strictly have to import anything to write macros, there are some useful things in the top-level namespace of `mcpy`. See `gensym`, `unparse`, `@namemacro`, and `@parametricmacro`. See also `mcpy.utils` for more macro-writing utilities that are too specific to warrant a spot in the top-level namespace.

The `tree` parameter is the only positional parameter the macro function is called with. All other parameters are passed by name, so you can easily pick what you need (and let `**kw` gather the ones you don't).

Beside returning an AST, you can return `None` to remove the `tree` you got in, or return a list of `AST` nodes (if in a position where that is syntactically admissible; so `block` and `decorator` macros only). The result of the macro expansion is recursively expanded until no new macro invocations are found.

```python
from ast import *
from mcpy import unparse
def log(expr, **kw):
    '''Replace log[expr] with print('expr: ', expr)'''
    label = unparse(expr) + ': '
    return Call(func=Name(id='print', ctx=Load()),
                args=[Str(s=label), expr], keywords=[],
                starargs=None, kwargs=None)
```

Any missing source locations and `ctx` fields are fixed automatically in a postprocessing step, so you don't need to care about those when writing your AST.

If you get an error saying an AST node is missing the required field `lineno`, the actual error is likely something else. This is due to an unfortunate lack of input validation in Python's compiler. The first thing to check is that your macro is really placing AST nodes where the compiler expects those, instead of accidentally using bare values.


### Distinguish how the macro is called

A macro can be called in four different ways. The way a macro is called is recorded in the `syntax` named parameter (one of `'block'`, `'expr'`, `'decorator'`, or `'name'`), so you can distinguish the syntax used in the source code and provide different implementations for each one. In other words, the macro function acts as a dispatcher for all types of uses of that macro.

When valid macro invocation syntax for one of the other three types is detected, the name part is skipped, and it **does not** get called as an identifier macro. The identifier macro mechanism is invoked only for appearances of the name *in contexts that are not other types of macro invocations*.

The other three work roughly the same as in MacroPy. An important difference is that in `mcpy`, macro arguments are passed using brackets, not parentheses, e.g. `macroname[arg0, ...][expr]`.

Also, in `mcpy` macros do not implicitly accept arguments. If you want your macro to accept them, declare it as a `@parametricmacro`. This explicitness makes it easier to implement macros that don't need arguments (the majority), since then you don't need to worry about `args`.


### The named parameters

Full list as of v3.0.0, in alphabetical order:

 - `args`: macro argument ASTs, if the invocation provided any. If not, `args = []`.
   - Macro arguments are a rarely needed feature. The macro function only accepts macro arguments if declared `@parametricmacro`. For non-parametric macros (default), `args = []` always.
 - `expander`: the macro expander instance.
   - To expand macro invocations inside the current one, use `expander.visit_recursively` or `expander.visit_once`, depending on whether you want expansion to continue until no macros remain. Use `expander.visit` to use current setting for recursive mode.
   - Also potentially useful are `expander.bindings` and `expander.filename`.
   - See [`mcpy.core.BaseMacroExpander`](mcpy/core.py) and [`mcpy.expander.MacroExpander`](mcpy/expander.py) for the expander API; it's just a few methods and attributes.
- `invocation`: the whole macro invocation AST node as-is, not only `tree`. For introspection.
   - Very rarely needed; if you need it, you'll know.
   - **CAUTION**: does not make a copy.
   - The node may have already been edited by the expander, for example to pop a block or decorator macro.
 - `optional_vars`: only exists when `syntax='block'`. The *as-part* of the `with` statement. (So actually use it as `kw['optional_vars']`.)
 - `syntax`: invocation type. One of `expr`, `block`, `decorator`, `name`.
   - Identifier macros are a rarely needed feature. The `syntax` parameter can be `name` only if the macro function is declared `@namemacro`.

*Changed in v3.0.0.* The named parameter `to_source` has been removed; use the top-level function `unparse` instead.

*Changed in v3.0.0.* The named parameter `expand_macros` has been replaced with `expander`, which grants access to the macro expander instance.


### Macro arguments

*New in v3.0.0.*

Macro arguments are a rarely needed feature. Hence, the expander interprets macro argument syntax only for macros that are declared as parametric. Declare by using the `@parametricmacro` decorator on your macro function. Place it outermost (along with `@namemacro`, if used too).

Once a macro has been declared parametric, macro arguments are sent by calling `macroname` with bracket syntax:

     macroname[arg0, ...]

Such an expression can appear in place of a bare `macroname` in an `expr`, `block` and `decorator` macro invocation. `name` macro invocations do not take macro arguments.

To invoke a parametric macro with no arguments, just use bare `macroname`, as if it was not parametric.

For simplicity, macro arguments are always positional.

The parametric macro function receives macro arguments as the `args` named parameter. It is a raw `list` of the ASTs `arg0` and so on. If the macro was invoked without macro arguments, `args` is an empty list. Any macro invocations inside the macro arguments are expanded after the primary macro invocation itself. To expand them first, use `expander.visit` in your macro implementation, as usual.

Observe `macroname[a][b]` may mean two different things:

  - If `macroname` is parametric, a macro invocation with `args=[a]`, `tree=b`.

  - If `macroname` is **not** parametric, first a macro invocation with `tree=a`,
    followed by a subscript operation on the result.

    Whether that subscript operation is applied at macro expansion time
    or at run time, depends on whether `macroname[a]` returns an AST for
    a `result`, for which `result[b]` can be interpreted as an invocation
    of a macro that is bound in the use site's macro expander. (This is
    exploited by the hygienic unquote operator `h`, when it is applied
    to a macro name.)


#### Arguments or no arguments?

Often, instead of taking macro arguments, you can just require `tree` to have a specific layout instead.

For example, a *let* macro invoked as `let[x << 1, y << 2][...]` could alternatively be designed to be invoked as `let[[x << 1, y << 2] in ...]`. But if the example `let` should work also as a decorator, then macro arguments are the obvious, uniform syntax, because then you can also `with let[x << 1, y << 2]:` and `@let[x << 1, y << 2]`.


### Quasiquotes

*New in v3.0.0.* We provide [a quasiquote system](quasiquotes.md) (both classical and hygienic) to make macro code both much more readable and simpler to write.

The system was inspired by MacroPy's, but the details differ; for example, macro invocations can be unquoted hygienically, and by default, macros in quasiquoted code are not expanded when the quasiquote itself expands. We provide macros to perform expansion in quoted code, to give you control over when things expand.


### Walk an AST

*New in v3.0.0.* To bridge the feature gap between [`ast.NodeTransformer`](https://docs.python.org/3/library/ast.html#ast.NodeTransformer) and MacroPy's `Walker`, we provide [`mcpy.walker.Walker`](walker.md), a zen-minimalistic AST walker base class based on `ast.NodeTransformer`, with a state stack and a node collector. If you need a walker that can temporarily change state while in a given subtree, maybe look here.


#### Identifier macros

*New in v3.0.0.*

Identifier macros are a rarely used feature, but one that is indispensable for
that rare use case. To avoid clutter in the dispatch logic of most macros, if a
macro function wants to be called as an identifier macro, it must explicitly opt
in. Declare by using the `@namemacro` decorator on your macro function. Place it
outermost (along with `@parametricmacro`, if used too).

Identifier macro invocations do not take macro arguments. So when a macro
function is invoked as an identifier macro, `args=[]`. The `tree` will be the
`Name` node itself.

Note it is valid for the same macro function to be invoked with one of the other
macro invocation types; in such contexts, it can take macro arguments if
declared (also) as `@parametricmacro`.

To tell the expander to go ahead and use the original name as a regular run-time
name, you can `return tree` without modifying it. This is useful when the
identifier macro is needed only for its side effects, such as validating its use
site.

Of course, if you want something else, you can return any tree you want to
replace the original with - after all, an identifier macro is just a macro,
and an identifier is just a special kind of expression.

The main use case, why this feature exists, is to create magic variables that
are allowed to appear only in certain contexts. Here's the pattern:

```python
from mcpy import namemacro
from mcpy.utils import NestingLevelTracker

_mymacro_level = NestingLevelTracker()

# a valid context for `it`
def mymacro(tree, *, syntax, expander, **kw):
    if syntax != "expr":
        raise SyntaxError("`mymacro` is an expr macro only")
    with _mymacro_level.changed_by(+1):
        tree = expander.visit_recursively(tree)  # this expands any `it` inside
        # Macro code goes here. You'll want it to define an actual
        # run-time `it` for the invocation site to refer to.
        # (But first check from `expander.bindings` what name
        #  our `it` macro function is actually bound to!)
    return tree

@namemacro
def it(tree, *, syntax, **kw):
    if syntax != "name":
        raise SyntaxError("`it` is a name macro only")
    if _mymacro_level.value < 1:
        raise SyntaxError("`it` may only appear within a `mymacro[...]`")
    return tree
```

This way any invalid, stray mentions of the magic variable `it` trigger an error at macro expansion time.

If you want to expand only `it` inside an invocation of `mymacro[...]` (thus checking that the mentions are valid), leaving other nested macro invocations untouched, that's also possible. See below how to temporarily run a second expander with different bindings (from which you can omit everything but `it`).


### Get the source of an AST

`mcpy.unparse` is a function that converts an AST back into Python source code.

Because the code is backconverted from the AST representation, the result may differ in minute details of surface syntax, such as parenthesization, whitespace, and which quote syntax is used for quoting string literals.


### Expand macros

Use the named parameter `expander` to access the macro expander. You can call `expander.visit_recursively(tree)` with an AST `tree` to expand all macros in that AST, until no macros remain. This is useful for making inner macro invocations expand first.

To expand only one layer of inner macro invocations, call `expander.visit_once(tree)`. This can be useful during debugging of a macro implementation. You can then convert the result into a printable form using `mcpy.unparse` or `mcpy.dump`.

To use the current setting for recursive mode, use `expander.visit(tree)`. The default mode is recursive.

If you need to temporarily run a second expander with different macro bindings, consult `expander.bindings` to grab the macro functions you need (and their current names), and then use `mcpy.expander.expand_macros(tree, modified_bindings, expander.filename)` to invoke a new expander with the modified bindings.


### Macro expansion error reporting

Any exception raised during macro expansion is reported immediately at compile time, and the program exits.

The error report includes two source locations: the macro use site (which was being expanded, not running yet), and the macro code that raised the exception (that was running and was terminated due to the exception).

The use site source location is reported in a chained exception (`raise from`), so if the second stack trace is long, scroll back in your terminal to see the original exception that was raised by the macro.


### Examples

`mcpy` is a macro expander, not a library containing macros. However, we provide a `demo` folder, to see `mcpy` in action. Navigate to it and run a Python console, then import `run`:

```python
import run
```

## Understanding the code

We follow the `mcpy` philosophy that macro expanders aren't rocket science. But the extra features do come with a cost in terms of codebase size.

For an overview of the core design, look at the [original mcpy](https://github.com/delapuente/mcpy), version 2.0.0. Of the parts that come from it, its `visitors` is our [`core`](mcpy/core.py) (the `BaseMacroExpander`), its `core` is our [`expander`](mcpy/expander.py) (the actual `MacroExpander`), and its `import_hooks` is our [`importer`](mcpy/importer.py). Its `BaseMacroExpander.ismacro` method is our `BaseMacroExpander.isbound`, because it checks a name, not an AST structure. The rest should be clear.

Then look at our [`importer`](mcpy/importer.py). After [`mcpy.activate`](mcpy/activate.py) has been imported, the importer becomes the top-level entry point.
