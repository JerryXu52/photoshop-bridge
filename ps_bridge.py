#!/usr/bin/env python3
"""ps_bridge.py - send ExtendScript (JSX) into a running Adobe Photoshop on macOS.

The bridge uses the "port" method: it shells out to `osascript`, which asks
Photoshop (via Apple Events) to `do javascript` with the supplied JSX. The JSX
runs inside Photoshop's own scripting engine with full access to its DOM
(app, activeDocument, layers, ...), and the value of the last expression is
returned to the terminal.

Usage:
    python3 ps_bridge.py --health                 # non-destructive check
    python3 ps_bridge.py -e "app.documents.length"
    python3 ps_bridge.py -f script.jsx
    echo "app.version" | python3 ps_bridge.py

As a library:
    from ps_bridge import PhotoshopBridge
    ps = PhotoshopBridge()
    print(ps.run("app.version"))
"""

import argparse
import glob
import os
import subprocess
import sys

# The JSX is passed to AppleScript as a command-line argument (argv) rather
# than spliced into the AppleScript source. That way quotes, backslashes and
# newlines in the JSX never need escaping and cannot break the AppleScript.
# The app name must be a literal in the source: AppleScript only resolves
# Photoshop's `do javascript` command when it knows the target at compile time.
APPLESCRIPT = """
on run argv
    tell application "%s"
        return do javascript (item 1 of argv)
    end tell
end run
"""

# Wrapping the user's code means JSX errors come back as a readable message
# instead of a cryptic AppleScript error number.
JSX_WRAPPER = """(function () {
try {
    var __result = eval(%s);
    return (__result === undefined) ? "" : String(__result);
} catch (e) {
    return "__PS_ERROR__" + e.name + ": " + e.message + (e.line ? " (line " + e.line + ")" : "");
}
})();"""

ERROR_PREFIX = "__PS_ERROR__"


class PhotoshopError(RuntimeError):
    """Raised when Photoshop or osascript reports an error."""


def find_photoshop_app():
    """Return the name of the newest installed Photoshop, e.g. 'Adobe Photoshop 2026'."""
    candidates = glob.glob("/Applications/Adobe Photoshop*/Adobe Photoshop*.app")
    if not candidates:
        raise PhotoshopError("No Adobe Photoshop installation found in /Applications.")
    newest = sorted(candidates)[-1]
    return os.path.splitext(os.path.basename(newest))[0]


def js_string_literal(text):
    """Encode text as a JavaScript string literal that is safe to eval()."""
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )
    return '"' + escaped + '"'


class PhotoshopBridge:
    def __init__(self, app_name=None, timeout=120):
        self.app_name = app_name or os.environ.get("PS_APP") or find_photoshop_app()
        self.timeout = timeout

    def run(self, jsx):
        """Execute JSX in Photoshop and return the result as a string."""
        wrapped = JSX_WRAPPER % js_string_literal(jsx)
        try:
            proc = subprocess.run(
                ["osascript", "-e", APPLESCRIPT % self.app_name.replace('"', ""), wrapped],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            raise PhotoshopError(
                "Timed out after %ss. Is a modal dialog open in Photoshop?" % self.timeout
            )
        if proc.returncode != 0:
            raise PhotoshopError(proc.stderr.strip() or "osascript failed")
        out = proc.stdout.rstrip("\n")
        if out.startswith(ERROR_PREFIX):
            raise PhotoshopError(out[len(ERROR_PREFIX):])
        return out

    def run_file(self, path):
        with open(path, "r", encoding="utf-8") as fh:
            return self.run(fh.read())

    def health_check(self):
        """Read-only probe: reports version and open documents, changes nothing."""
        return self.run(
            '"Photoshop " + app.version + " | open documents: " + app.documents.length'
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Send ExtendScript (JSX) to Adobe Photoshop.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-e", "--eval", metavar="JSX", help="JSX code to run")
    group.add_argument("-f", "--file", metavar="PATH", help="JSX file to run")
    group.add_argument("--health", action="store_true", help="run a non-destructive health check")
    parser.add_argument("--app", help="Photoshop application name (default: auto-detect)")
    args = parser.parse_args(argv)

    try:
        ps = PhotoshopBridge(app_name=args.app)
        if args.health:
            result = ps.health_check()
        elif args.eval is not None:
            result = ps.run(args.eval)
        elif args.file:
            result = ps.run_file(args.file)
        elif not sys.stdin.isatty():
            result = ps.run(sys.stdin.read())
        else:
            parser.print_help()
            return 2
    except PhotoshopError as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 1

    if result:
        print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
