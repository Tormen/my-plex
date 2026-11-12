"""my-plex's BOOT: what runs before the venv exists, and what decides WHO runs
and IN WHAT INTERPRETER.

The launcher (`my-plex`) imports this module under `-I -S` -- the stdlib and
nothing else -- and calls main().  main() refuses root, applies -Q, builds the
venv when it is missing and re-executes the launcher inside it, and only then
imports the tool, my_plex.  So this module may import nothing beyond the
stdlib: on a fresh machine it runs before any package is installed.

It is a module of its own, rather than part of the launcher or of the tool,
for three reasons: the launcher stays a few lines (CPython caches bytecode
for IMPORTED modules only); this code must import before the venv exists,
which the tool cannot; and err() and the print-only predicate are asked by
both this code and the tool, so each has ONE owner here that the tool imports
rather than a copy of its own.
"""
# Error codes: err() takes a five-digit string code ("00042"), UNIQUE per
# source line, numbered from 00001 in file order with no gap across BOTH
# files -- this one first, then my_plex.py -- so grepping a code lands on the
# one line that raised it.  _stamp_fail() and the _media_api_action() callers
# in my_plex.py share the numbering.  After adding a call (any placeholder
# code), renumber both files with one counter (`my-plex --run-tests errcodes`
# checks the result):
#   perl -0pi -e 'BEGIN{$n=0} s/(\b(?:err|_stamp_fail)[ \t]*\(\s*|_media_api_action[ \t]*\(media_identifier, action, )"?\d+"?(?=\s*[,)])/sprintf("%s\"%05d\"",$1,++$n)/ge' my_plex_boot.py my_plex.py

import os
import subprocess
import sys
from typing import NoReturn


def err(err_code: str, err_msg: str = "", exit_code: int = 1) -> NoReturn:
    """Report and stop.  exit_code is for the few callers that must exit with
    something other than 1 -- the top-level bug handler exits 70.

    `ERROR <code> [<exit>]: <text>` is the house shape.  The CODE is there to
    be grepped for: it identifies the source line that raised this, and
    nothing else in the message does.  The EXIT STATUS is printed beside it
    because the code holds both and a caller sees only one of them -- so a
    message claiming [1] while the process exits 70 is visible in ordinary
    output instead of having to be debugged.

    Defined HERE, in the boot module, because the first things that can fail
    are the venv bootstrap and the refusal below -- and an error from those
    is an error like any other.  The tool imports this one.
    """
    if len( err_msg )==0: err_msg = "This error should not be. Please contact the maintainer of this software. Thank you!"
    print(f"\nERROR {err_code} [{exit_code}]: {err_msg}\n", file=sys.stderr)
    sys.exit(exit_code)


# The path of the launcher this run was started through, as main() was given
# it (every symlink followed).  The tool asks it for what names the launcher:
# a run of itself, the build id, the suite's MAIN_SCRIPT.  Empty when the
# tool was imported without main() -- a test importing the module.
LAUNCHER = ""


def main(launcher: str) -> None:
    """Decide who runs and in what interpreter, then hand over to the tool.

    In this order, each for a reason:
      1. the ROOT refusal -- first, because a refusal that fires after the
         bootstrap has built /var/root/.python.venv is too late to be one;
      2. -Q, so the bootstrap's own output is silenced too;
      3. the venv: build it when missing, then re-exec the launcher inside
         it.  A run that only prints skips this -- see print_only_run();
      4. import the tool and run it.
    """
    global LAUNCHER
    LAUNCHER = launcher
    argv = sys.argv
    if as_root() and not print_only_run(argv):
        err("00001", root_refusal())
    if quiet_argv(argv):
        go_quiet()

    # Ctrl-C is caught HERE because the tool's own SIGINT handler
    # (_graceful_shutdown_handler) exists only once the tool is imported and
    # running.  So this window has the default handler, and an interrupt in it
    # ends in a KeyboardInterrupt traceback on the screen.  That is not
    # hypothetical: `pip install` hung on a held connection while building the
    # venv, and the Ctrl-C that stopped it printed nine frames of subprocess
    # internals (ada, 2026-11-01).  Same answer as the tool's backstop: one
    # line, and 130.
    try:
        if not print_only_run(argv) and not _inside_our_venv():
            if not _venv_has_deps():
                _bootstrap_venv()
            # Venv exists and has deps -- re-exec inside it
            _exec_in_venv()
    except KeyboardInterrupt:
        print(f"\nmy-plex: interrupted (Ctrl-C) while setting up '{VENV_DIR}' -- "
              f"nothing after that ran.\n"
              f"  The directory may be half-built; the next run takes it up from "
              f"there (remove it to start over).", file=sys.stderr)
        sys.exit(130)
    # Reaching this line means we are where we need to be: _exec_in_venv()
    # never returns.  So no re-exec is in flight any more and the marker goes
    # -- left set it is INHERITED by every child process this run starts, and
    # one of those children is another my-plex, which would then read a
    # marker that was never about it and refuse to re-exec at all.  That is
    # not hypothetical: the suite spawns my-plex constantly.
    os.environ.pop(_VENV_REEXEC_MARK, None)

    import my_plex
    my_plex.run()


def argv_options(argv: "list[str]") -> "list[str]":
    """The tokens main_parser reads as options: those before a `--`, after
    which every token is a positional."""
    return argv[1:argv.index('--')] if '--' in argv else argv[1:]


def version_asked(argv: "list[str]") -> bool:
    """True when argv asks for --version (answered before anything else)."""
    return any(a in ('--version', '-version') for a in argv_options(argv))


def print_only_run(argv: "list[str]") -> bool:
    """True for a run that only PRINTS: a bare `my-plex`, --help, --version.

    Such a run needs nothing from the venv, and must never build one.  A
    deployment gate asks `my-plex --help` to find out what this tool can do --
    on a machine that may have neither the venv nor the network to make one,
    and with nobody at the screen to answer for it.  Building an environment
    in order to answer that question is how `--help` comes back empty and a
    copy goes out untested.  The bare run is one of these: it prints the
    usage, so it must not build an environment to do it either.

    The ROOT rule in main() reads this same predicate, because it is the same
    question asked twice: does this run need anything of the user's?  A run
    that only prints needs nothing -- not the venv, not the cache, not the
    config -- so there is nothing for root to put in the wrong home, and
    refusing it would only hide the help from whoever is in a root shell.
    It reads nothing but argv, so it can be answered before anything else.
    It reads argv the way main_parser will: only the tokens before a `--`
    (`-U -Y -- --help` asks for no help -- matched anyway, it ran
    --update-cache as root).  The help flags are main_parser's `-H` /
    `--help`, in every spelling it accepts with a WHAT: `--help WHAT`,
    `--help=WHAT`, `-HWHAT`.  `-h` is no flag of my-plex, and counting it let
    a root `my-plex -h` into a real run.  Bundled into other short flags
    (`-VH`) it is not counted: as root that is refused, like any argv this
    misjudges -- the parser has the last word (the second root check in the
    tool's main).
    """
    return (len(argv) == 1 or version_asked(argv)
            or any(a == '--help' or a.startswith('--help=') or a.startswith('-H')
                   for a in argv_options(argv)))


def as_root() -> bool:
    """True when this run's euid is root -- the one place that asks.

    my-plex runs as the user whose Plex and whose media files these are, and
    as nobody else.  ROOT is refused for every command that DOES anything,
    because as root this tool is wrong in two directions at once: everything
    it keeps -- the venv it builds on first use, the cache, the config it
    reads, the zsh completion it installs -- lands in /var/root instead of
    that user's home, and everything it says about "the Python that runs
    my-plex" (the firewall rule --install names) would name root's
    interpreter, a process that never runs.  Nothing here needs privilege:
    where a step genuinely does, --install prints the command for a root
    shell and this tool writes nothing itself.

    Past the refusal in main(), root is only ever on a print-only run, and
    such a run writes nothing into root's home either: the tool skips the zsh
    completion and ~/.my-plex, which every run of an ordinary user writes.
    """
    return os.geteuid() == 0


def root_refusal() -> str:
    """The text of the root refusal -- one text, said at both root checks."""
    return ("my-plex does not run as root -- run it as the user whose Plex this is.\n"
            f"  (this run: euid 0, HOME={os.environ.get('HOME', '?')})\n"
            "Possible reasons:\n"
            "  - sudo, or a root shell: drop it, my-plex needs no privilege at all\n"
            "  - a rollout step: give it `# user: <that user>` instead of root\n"
            "  - the firewall rules: run `my-plex --install` as that user -- it\n"
            "    prints the root commands that write them, and writes none itself\n"
            "  - only READING what this tool is: `my-plex`, `--help [WHAT]` (or\n"
            "    `-H`) and `--version` print and touch nothing, so they work as root")


# -Q / --quiet: nothing on stdout at all -- not a summary, not a result.  It
# is for a crontab, a LaunchDaemon or a wrapper, where narration is mailed to
# nobody's benefit and only a failure is worth waking someone for.  Errors and
# warnings are on stderr throughout, so they still come through: that is what
# makes "quiet except errors" true here rather than hoped for.
#
# It acts HERE, ahead of the venv bootstrap, so a first run under -Q does not
# print pip's narration either; the re-exec inherits the silenced fd 1.
#
# -V and -D ask for MORE output, so either of them beats -Q.  That precedence
# is decided in quiet_argv(), once, and the tool's main() applies the same
# rule to the config value.
QUIET_ACTIVE = False


def quiet_argv(argv: "list[str]") -> bool:
    """True when argv asks for -Q and nothing that overrides it."""
    return (any(a in ('-Q', '--quiet') for a in argv[1:])
            and not any(a in ('-V', '--verbose', '-VV', '--very-verbose',
                              '-D', '--debug', '-DD', '--deepdebug')
                        for a in argv[1:]))


def go_quiet() -> None:
    """Silence this run's stdout for good.  Idempotent.

    FILE DESCRIPTOR 1 is what gets redirected, not sys.stdout: 22 of this
    tool's 67 subprocess calls inherit fd 1 (ssh, ffmpeg), so a Python-level
    swap would claim silence while letting their output through.  Replacing
    the descriptor covers both, and covers every one of the 5894 bare print()
    calls of the tool without any of them having to know about -Q -- so no
    print site can ever drift out of it.
    """
    global QUIET_ACTIVE
    if QUIET_ACTIVE:
        return
    try:
        sys.stdout.flush()
    except (ValueError, OSError):
        pass          # already closed by a caller; the redirect is still wanted
    _sink = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(_sink, 1)
    finally:
        os.close(_sink)
    QUIET_ACTIVE = True


# ---------------------------------------------------------------------------
# Venv bootstrap: ensure we run inside a venv with plexapi+readchar installed.
# If not, create the venv, install deps, and re-exec the launcher in it.
# ---------------------------------------------------------------------------
VENV_DIR = os.path.expanduser("~/.python.venv/my-plex")
VENV_PYTHON = os.path.join(VENV_DIR, "bin", "python3")
VENV_DEPS = ["plexapi", "readchar"]

# Set on the re-exec below, so a second one that lands nowhere is an error
# rather than an endless loop.
_VENV_REEXEC_MARK = "MY_PLEX_VENV_REEXEC"


def _inside_our_venv():
    """True when the interpreter running this IS the one in VENV_DIR.

    sys.prefix is the venv's own directory inside a venv, and the base
    installation's prefix outside it.  That is the only thing that answers
    this question.

    Comparing sys.executable with VENV_PYTHON does NOT answer it, which is
    how this was wrong: a venv's bin/python3 is a symlink to the interpreter
    the venv was built FROM, so os.path.realpath() of both sides yields that
    same base interpreter whenever the venv was built from the python3 the
    shebang picks.  The comparison then says "already inside", nothing
    re-execs, and the run continues with none of the venv's site-packages --
    a ModuleNotFoundError on the first `import readchar`.  It stayed hidden
    because a machine whose venv is a DIFFERENT python version from its
    python3 compares two different paths and works by accident.
    """
    return os.path.realpath(sys.prefix) == os.path.realpath(VENV_DIR)


def _exec_in_venv():
    """Hand this run over to the venv's interpreter, with the same arguments.

    sys.argv[0] is the launcher, so the venv's python runs the launcher again
    -- without its shebang's -I -S, so it meets the venv's site-packages.

    Refuses a second attempt: if we re-exec and still do not land inside,
    something is wrong with the venv itself (a missing or unreadable
    pyvenv.cfg), and an error naming it beats spawning for ever.
    """
    if os.environ.get(_VENV_REEXEC_MARK):
        err("00002", f"re-executed into '{VENV_DIR}' and still landed outside it.\n"
                 f"  Its pyvenv.cfg is missing or unreadable -- remove the\n"
                 f"  directory and run my-plex again to have it rebuilt.")
    os.environ[_VENV_REEXEC_MARK] = "1"
    os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)


def _venv_has_deps():
    """Check if venv exists and has required packages."""
    if not os.path.isfile(VENV_PYTHON):
        return False
    site_packages = os.path.join(VENV_DIR, "lib")
    if not os.path.isdir(site_packages):
        return False
    # Check for plexapi AND readchar in site-packages
    found: "set[str]" = set()
    for d in os.listdir(site_packages):
        pkg_dir = os.path.join(site_packages, d, "site-packages")
        if os.path.isdir(pkg_dir):
            for dep in VENV_DEPS:
                if os.path.isdir(os.path.join(pkg_dir, dep)):
                    found.add(dep)
    return found == set(VENV_DEPS)


def _bootstrap_venv():
    """Create venv, install deps, and re-exec."""
    print(f"\n >>> Creating python virtualenv '{VENV_DIR}'...\n", file=sys.stderr)

    rc = subprocess.call([sys.executable, "-m", "venv", VENV_DIR])
    if rc != 0:
        err("00003", f"failed to create the venv at {VENV_DIR} [rc {rc}]")

    pip = os.path.join(VENV_DIR, "bin", "pip")
    rc = subprocess.call([pip, "install"] + VENV_DEPS)
    if rc != 0:
        err("00004", f"failed to install the dependencies {', '.join(VENV_DEPS)} "
                 f"into {VENV_DIR} [rc {rc}]")

    print(f"\n >>> DONE creating python virtualenv '{VENV_DIR}'.", file=sys.stderr)
    print("=" * 64, file=sys.stderr)

    # Re-exec with venv python, preserving all arguments
    _exec_in_venv()
