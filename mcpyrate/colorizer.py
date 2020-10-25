# -*- coding: utf-8; -*-
"""Colorize terminal output.

Use Colorama if available; works on any OS.

If not available, and OS is a *nix, use ANSI escape codes.
"""

__all__ = ["setcolor", "colorize", "ColorScheme",
           "Fore", "Back", "Style"]

try:
    from colorama import init as colorama_init, Fore, Back, Style
    colorama_init()
except ImportError:  # pragma: no cover
    # The `ansi` module is a slightly modified, POSIX-only,
    # vendored version from Colorama. Useful e.g. in Docker
    # images that don't have the library available.
    from .ansi import Fore, Back, Style  # noqa: F811

from .bunch import Bunch


def setcolor(*colors):
    """Set color for terminal display.

    Returns a string that, when printed into a terminal, sets the color
    and style.

    For available `colors`, see `Fore`, `Back` and `Style`.

    Each entry can also be a tuple (arbitrarily nested), which is useful
    for defining compound styles.

    **CAUTION**: The specified style and color remain in effect until another
    explicit call to `setcolor`. To reset, use `setcolor(Style.RESET_ALL)`.
    If you want to colorize a piece of text so that the color and style
    auto-reset after your text, use `colorize` instead.
    """
    def _setcolor(color):
        if isinstance(color, (list, tuple)):
            return "".join(_setcolor(elt) for elt in color)
        return color
    return _setcolor(colors)


def colorize(text, *colors, reset=True):
    """Colorize string `text` for terminal display.

    Returns `text`, augmented with color and style commands for terminals.

    For available `colors`, see `Fore`, `Back` and `Style`.

    Usage::

        print(colorize("I'm new here", Fore.GREEN))
        print(colorize("I'm bold and bluetiful", Style.BRIGHT, Fore.BLUE))

    Each entry can also be a tuple (arbitrarily nested), which is useful
    for defining compound styles::

        BRIGHT_BLUE = (Style.BRIGHT, Fore.BLUE)
        ...
        print(colorize("I'm bold and bluetiful, too", BRIGHT_BLUE))

    **CAUTION**: Does not nest. Style and color reset after the colorized text.
    If you want to set a color and style until further notice, use `setcolor`
    instead.
    """
    return "{}{}{}".format(setcolor(colors),
                           text,
                           setcolor(Style.RESET_ALL))


class ColorScheme(Bunch):
    """The color scheme for terminal output in `mcpyrate`'s debug utilities.

    This is just a bunch of constants. To change the colors, simply assign new
    values to them. Changes take effect immediately for any new output.

    To replace the whole color scheme, fill in a suitable `Bunch`, and then
    call `ColorScheme.replace(newbunch)`. To get the names of all settings,
    use `ColorScheme.keys()`.

    (Don't replace the `ColorScheme` object itself; all the use sites
    from-import it.)

    See `Fore`, `Back`, `Style` for valid values. To make a compound style,
    place the values into a tuple.

    The defaults are designed to fit the "Solarized" (Zenburn-like) theme
    of `gnome-terminal`, with "Show bold text in bright colors" set to OFF.
    But they work also with "Tango", and indeed with most themes.
    """
    def __init__(self):
        super().__init__()

        self._RESET = Style.RESET_ALL

        # ------------------------------------------------------------
        # unparse

        self.LINENUMBER = Style.DIM

        self.LANGUAGEKEYWORD = (Style.BRIGHT, Fore.YELLOW)  # for, if, import, ...
        self.BUILTINEXCEPTION = Fore.CYAN  # TypeError, ValueError, Warning, ...
        self.BUILTINOTHER = Style.BRIGHT  # str, property, print, ...

        self.DEFNAME = (Style.BRIGHT, Fore.CYAN)  # name of a function or class being defined
        self.DECORATOR = Fore.LIGHTBLUE_EX

        # These can be highlighted differently although Python 3.8+ uses `Constant` for all.
        self.STRING = Fore.GREEN
        self.NUMBER = Fore.GREEN
        self.NAMECONSTANT = Fore.GREEN  # True, False, None

        # Macro names are syntax-highlighted when a macro expander instance is
        # running and is provided to `unparse`, so it can query for bindings.
        # `step_expansion` does that automatically.
        #
        # So they won't yet be highlighted during dialect AST transforms,
        # because at that point, there is no *macro* expander.
        self.MACRONAME = Fore.BLUE

        self.INVISIBLENODE = Style.DIM  # AST node with no surface syntax repr (`Module`, `Expr`)

        # AST markers for data-driven communication within the macro expander
        self.ASTMARKER = Style.DIM  # the "$AstMarker" title
        self.ASTMARKERCLASS = Fore.YELLOW  # the actual marker type name

        # ------------------------------------------------------------
        # format_bindings, step_expansion, StepExpansion

        # TODO: Clean the implementations to use `_RESET` at the appropriate points
        # TODO: so we don't need to specify things `Fore.RESET` or `Style.NORMAL` here.

        self.HEADING = (Style.BRIGHT, Fore.LIGHTBLUE_EX)
        self.SOURCEFILENAME = (Style.BRIGHT, Fore.RESET)

        # format_bindings
        self.MACROBINDING = self.MACRONAME
        self.GREYEDOUT = Style.DIM  # if no bindings

        # step_expansion
        self.TREEID = (Style.NORMAL, Fore.LIGHTBLUE_EX)

        # StepExpansion
        self.ATTENTION = (Style.BRIGHT, Fore.GREEN)  # "DialectExpander debug mode"
        self.TRANSFORMERKIND = (Style.BRIGHT, Fore.GREEN)  # source, AST
        self.DIALECTTRANSFORMERNAME = (Style.BRIGHT, Fore.YELLOW)

        # ------------------------------------------------------------
        # dump

        self.NODETYPE = (Style.BRIGHT, Fore.LIGHTBLUE_EX)
        self.FIELDNAME = Fore.YELLOW
        self.BAREVALUE = Fore.GREEN
ColorScheme = ColorScheme()
