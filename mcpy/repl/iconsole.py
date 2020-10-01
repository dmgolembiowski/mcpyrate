# -*- coding: utf-8 -*-
"""IPython extension for an mcpy-enabled REPL.

To enable::

    %load_ext mcpy.repl.iconsole

To autoload it at IPython startup, put this into your ``ipython_config.py``::

    c.InteractiveShellApp.extensions = ["mcpy.repl.iconsole"]

To find your config file, ``ipython profile locate``.

Make sure `c.TerminalInteractiveShell.autocall = 0`. Expr macro invocations
will not work if autocall is enabled, because in `mcpy` macros are functions
(and the REPL imports those functions so you can easily view their docstrings).

Notes:

  - The line magic `%macros` shows macros currently imported to the session.

  - Each time a ``from module import macros, ...`` is executed in the REPL,
    just before invoking the macro expander, the system reloads ``module``,
    to always import the latest macro definitions.

    Hence, semi-live updates to macro definitions are possible: hack on your
    macros, re-import the macros, and try out the new version in the REPL.
    No need to restart the REPL session in between.

    But note that only the macros you explicitly import again will be refreshed
    in the session.

  - Each time after importing macros, the macro functions are automatically
    imported as regular Python objects. Note only the REPL does this; normally,
    in `mcpy` macros are not imported as run-time objects.

    The intention is to allow viewing macro docstrings and source code easily
    in the REPL session, using ``some_macro?``, ``some_macro??``.

    This does not affect using the macros in the intended way, as macros.
"""

import ast
from collections import OrderedDict
from functools import partial

from IPython.core.error import InputRejected
from IPython.core.magic import register_cell_magic, register_line_magic

from mcpy import __version__ as mcpy_version
from mcpy.expander import find_macros, expand_macros

from .util import _reload_macro_modules

_placeholder = "<interactive input>"
_instance = None

def load_ipython_extension(ipython):
    # FIXME: The banner is injected too late. It seems IPython startup has  already performed when ``load_ipython_extension()`` is called.
    #
    # FIXME: We shouldn't print anything directly here; doing that breaks tools such as the Emacs Python autoimporter (see importmagic.el
    # FIXME: in Spacemacs; it will think epc failed to start if anything but the bare process id is printed). Tools expect to suppress
    # FIXME: **all** of the IPython banner by telling IPython itself not to print it.
    #
    # FIXME: For now, let's just put the info into banner2, and refrain from printing it.
    # https://stackoverflow.com/questions/31613804/how-can-i-call-ipython-start-ipython-with-my-own-banner
    ipython.config.TerminalInteractiveShell.banner2 = "mcpy {} -- Syntactic macros for Python.".format(mcpy_version)
    global _instance
    if not _instance:
        _instance = IMcpyExtension(shell=ipython)

def unload_ipython_extension(ipython):
    global _instance
    _instance = None

class InteractiveMacroTransformer(ast.NodeTransformer):
    def __init__(self, extension_instance, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ext = extension_instance
        self.bindings = OrderedDict()

    def visit(self, tree):
        try:
            _reload_macro_modules(tree)
            bindings = find_macros(tree)  # macro imports (this will import the modules)
            if bindings:
                self.ext.bindings_changed = True
                self.bindings.update(bindings)
            newtree = expand_macros(tree, self.bindings, "<interactive input>")
            self.ext.src = _placeholder
            return newtree
        except Exception as err:
            # see IPython.core.interactiveshell.InteractiveShell.transform_ast()
            raise InputRejected(*err.args)


# avoid complaining about typoed macro names when their stubs are loaded
@register_cell_magic
def ignore_importerror(line, cell):
    try:
        exec(cell, _instance.shell.user_ns)  # set globals to the shell user namespace to respect assignments
    except ImportError:
        pass

@register_line_magic
def macros(line):
    """Print a human-readable list of macros currently imported into the session."""
    t = _instance.macro_transformer
    if not t.bindings:
        print("<no macros imported>")
        return
    themacros = []
    for asname, function in t.bindings.items():
        themacros.append((asname, f"{function.__module__}.{function.__qualname__}"))
    for asname, fullname in themacros:
        print(f"{asname}: {fullname}")


class IMcpyExtension:
    def __init__(self, shell):
        self.src = _placeholder
        self.shell = shell
        ipy = self.shell.get_ipython()

        self.shell.input_transformers_post.append(self._get_source_code)

        self.bindings_changed = False
        self.macro_transformer = InteractiveMacroTransformer(extension_instance=self)
        self.shell.ast_transformers.append(self.macro_transformer)  # TODO: last or first?

        ipy.events.register('post_run_cell', self._refresh_stubs)

        # initialize mcpy in the session
        self.shell.run_cell("import mcpy.activate", store_history=False, silent=True)

    def __del__(self):
        ipy = self.shell.get_ipython()
        ipy.events.unregister('post_run_cell', self._refresh_stubs)
        self.shell.ast_transformers.remove(self.macro_transformer)
        self.shell.input_transformers_post.remove(self._get_source_code)

    def _get_source_code(self, lines):  # IPython 7.0+ with Python 3.5+
        """Get the source code of the current cell.

        This is a do-nothing string transformer that just captures the text.
        It is intended to run last, just before any AST transformers run.
        """
        self.src = lines
        return lines

    def _refresh_stubs(self, info):
        """Refresh macro stub imports.

        Called after running a cell, so that IPython help "some_macro?" works
        for the currently available macros, allowing the user to easily view
        macro docstrings.
        """
        if not self.bindings_changed:
            return
        self.bindings_changed = False
        internal_execute = partial(self.shell.run_cell,
                                   store_history=False,
                                   silent=True)

        for asname, function in self.macro_transformer.bindings.items():
            commands = ["%%ignore_importerror",
                        f"from {function.__module__} import {function.__qualname__} as {asname}"]
            internal_execute("\n".join(commands))