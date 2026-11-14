"""my-plex's BOOT: what runs before the venv exists, and what decides WHO runs
and IN WHAT INTERPRETER.

The launcher (`my-plex`) imports this module under `-I -S` -- the stdlib and
nothing else -- and calls main().  main() refuses root, applies -Q, builds the
venv when it is missing and re-executes the launcher inside it, and only then
imports the tool, my_plex.  So this module may import nothing beyond the
stdlib: on a fresh machine it runs before any package is installed.

As root, main() runs one command alone, --install: the firewall rules,
then the drop to the user the rest runs as (_root_install).

It is a module of its own, rather than part of the launcher or of the tool,
for three reasons: the launcher stays a few lines (CPython caches bytecode
for IMPORTED modules only); this code must import before the venv exists,
which the tool cannot; and err() and the argv predicates (help_asked,
print_only_run) are asked by both this code and the tool, so each has ONE
owner here that the tool imports rather than a copy of its own.
"""
# pyright: reportConstantRedefinition=false
#   Uppercase names here are module STATE set once at startup (LAUNCHER,
#   QUIET_ACTIVE), as the house names its run flags (VRB, DBG, QUIET) -- not
#   constants.  The rule is off per file because pyright's "strict" list
#   overrides any rule setting in pyrightconfig.json.
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
         bootstrap has built /var/root/.python.venv is too late to be one.
         --install is the one command root runs: its firewall half, then
         the drop to the user (_root_install), never past this point;
      2. -Q, so the bootstrap's own output is silenced too;
      3. the venv: build it when missing -- or, for the --install root hands
         over, when it was built from another Python minor -- then re-exec
         the launcher inside it.  A run that only prints skips this -- see
         print_only_run();
      4. import the tool and run it.  Ctrl-C while the tool imports is
         caught here too: its own SIGINT handler exists only once it has.
    """
    global LAUNCHER
    LAUNCHER = launcher
    argv = sys.argv
    if as_root() and not print_only_run(argv) and not install_asked(argv):
        err("00001", root_refusal())
    if quiet_argv(argv):
        go_quiet()
    if as_root() and not print_only_run(argv):
        try:
            _root_install(launcher, argv)
        except KeyboardInterrupt:
            print("\nmy-plex: interrupted (Ctrl-C) in --install's firewall half -- nothing was\n"
                  "  handed over; the rules written so far stay, and a second run writes the rest.",
                  file=sys.stderr)
            sys.exit(130)

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
            # The --install root hands over rebuilds a venv of another Python
            # minor: root has just written rules naming THIS python3, and to
            # the firewall another minor is another program.  Only that run:
            # a user's own --install writes no rule, so none names this
            # python3, and it must not clear the venv.
            built_from = (_venv_minor() if install_asked(argv)
                          and os.environ.get(INSTALL_FROM_ROOT_ENV) == "1" else None)
            stale = built_from is not None and built_from != _this_minor()
            if stale or not _venv_has_deps():
                _bootstrap_venv(rebuilt_from=built_from if stale else None)
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

    try:
        tool = _import_tool()
    except KeyboardInterrupt:
        print("\nmy-plex: interrupted (Ctrl-C) while loading the tool -- nothing ran.",
              file=sys.stderr)
        sys.exit(130)
    tool.run()


def _import_tool():
    """my_plex, the tool -- the one place every run imports it, so the one
    place that asks for MIN_PYTHON: an older python3 would stop on the tool's
    first `match` with a SyntaxError traceback instead of a sentence.  A run
    that only prints imports it in the python3 that started the launcher,
    with no venv between.  An ERROR, too, naming the directory my_plex.py is
    missing from."""
    if sys.version_info < MIN_PYTHON:
        import shlex
        v = sys.version_info
        err("00002", f"my-plex needs python3 >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}, and the python3 "
                     f"running `{shlex.join(['my-plex'] + sys.argv[1:])}` is "
                     f"{v.major}.{v.minor}.{v.micro}: {sys.executable}\n"
                     f"Possible reasons:\n"
                     f"  - this PATH (a root shell's, a job's) finds an older python3 before\n"
                     f"    the one my-plex's users run: put the newer one first, or install it")
    try:
        import my_plex
    except ModuleNotFoundError as e:
        if e.name != "my_plex":
            raise
        err("00003", f"my_plex.py is not beside my_plex_boot.py in "
                     f"{os.path.dirname(os.path.realpath(__file__))} -- a copy of part of my-plex")
    return my_plex


def argv_options(argv: "list[str]") -> "list[str]":
    """The tokens main_parser reads as options: those before a `--`, after
    which every token is a positional."""
    return argv[1:argv.index('--')] if '--' in argv else argv[1:]


def version_asked(argv: "list[str]") -> bool:
    """True when argv asks for --version (answered before anything else)."""
    return any(a in ('--version', '-version') for a in argv_options(argv))


def help_asked(argv: "list[str]") -> bool:
    """True when argv asks for help, read the way main_parser will: only the
    tokens before a `--` (after it `--help` is a positional), and the help
    flags `-H` / `--help` in every spelling the parser accepts with a WHAT:
    `--help WHAT`, `--help=WHAT`, `-HWHAT`.  `-h` is no flag of my-plex.
    Bundled into other short flags (`-VH`) it is not counted -- the parser
    has the last word.  The print-only check below and the tool's main()
    (which lets help win over --create-config and bare --config) both ask
    this one question here, so the two cannot read argv differently."""
    return any(a == '--help' or a.startswith('--help=') or a.startswith('-H')
               for a in argv_options(argv))


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
    It reads argv the way main_parser will (help_asked): `-U -Y -- --help`
    asks for no help -- matched anyway, it ran --update-cache as root; and
    counting `-h` let a root `my-plex -h` into a real run.  What this
    misjudges as root is refused -- the parser has the last word (the second
    root check in the tool's main).
    """
    return len(argv) == 1 or version_asked(argv) or help_asked(argv)


def caller_name() -> str:
    """The name of the user this run IS -- its uid's, from the password
    database -- for every message that names the caller.  Never $USER or
    $LOGNAME (what getpass.getuser() reads): an environment can name anyone,
    and on ada's deploy gate (2026-11-13) it named root while the uid was
    not, so a line judged by the uid named the wrong user.  A uid with no
    entry is shown as the number."""
    import pwd
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        return str(os.getuid())


def as_root() -> bool:
    """True when this run's euid is root -- the one place that asks.

    my-plex runs as the user whose Plex and whose media files these are, and
    as nobody else.  ROOT is refused for every command that DOES anything,
    because as root this tool is wrong in two directions at once: everything
    it keeps -- the venv it builds on first use, the cache, the config it
    reads, the zsh completion it installs -- lands in /var/root instead of
    that user's home, and everything it says about "the Python that runs
    my-plex" (the firewall rule --install names) would name root's
    interpreter, a process that never runs.  The one step that needs
    privilege is --install's firewall half: root runs that command alone, and
    hands the rest over to the user (_root_install).

    Past the refusal in main(), root is only ever on a print-only run or in
    that firewall half, and neither writes into root's home: the tool skips
    the zsh completion and ~/.my-plex, which every run of an ordinary user
    writes, and root builds no venv.
    """
    return os.geteuid() == 0


def root_refusal() -> str:
    """The text of the root refusal -- one text, said at both root checks."""
    return ("my-plex does not run as root -- run it as the user whose Plex this is.\n"
            f"  (this run: euid 0, HOME={os.environ.get('HOME', '?')})\n"
            "Possible reasons:\n"
            "  - sudo, or a root shell: drop it, my-plex needs no privilege at all\n"
            "  - a rollout step: give it `# user: <that user>` instead of root\n"
            "  - `--install` is the one command that runs as root: it writes the\n"
            "    firewall rules, then hands the rest over to RUN_AS_USER itself\n"
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

    A run WITHOUT site is outside too.  The launcher's shebang adds -S, and
    when the python3 PATH finds is the venv's own (the venv activated, or its
    bin/ first in a job's PATH), sys.prefix is the venv -- read from
    pyvenv.cfg at startup -- while its site-packages, which only site adds,
    are not importable.  The re-exec runs the venv's python without -S.
    """
    return (not sys.flags.no_site
            and os.path.realpath(sys.prefix) == os.path.realpath(VENV_DIR))


def _exec_in_venv():
    """Hand this run over to the venv's interpreter, with the same arguments.

    sys.argv[0] is the launcher, so the venv's python runs the launcher again
    -- without its shebang's -I -S, so it meets the venv's site-packages.

    Refuses a second attempt: if we re-exec and still do not land inside,
    something is wrong with the venv itself (a missing or unreadable
    pyvenv.cfg), and an error naming it beats spawning for ever.
    """
    if os.environ.get(_VENV_REEXEC_MARK):
        err("00004", f"re-executed into '{VENV_DIR}' and still landed outside it.\n"
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


def _this_minor() -> str:
    """The Python minor running this, "3.15"."""
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def _venv_minor() -> "str | None":
    """The Python minor VENV_DIR was built from ("3.14"), from its
    pyvenv.cfg; None when there is none to read."""
    try:
        with open(os.path.join(VENV_DIR, "pyvenv.cfg")) as f:
            for line in f:
                key, _eq, value = line.partition("=")
                if key.strip() in ("version", "version_info"):
                    return ".".join(value.strip().split(".")[:2])
    except OSError:
        pass
    return None


def _bootstrap_venv(rebuilt_from: "str | None" = None):
    """Create the venv -- emptied first when REBUILT_FROM names the other
    Python minor it was built from -- install deps, and re-exec."""
    if rebuilt_from:
        print(f"\n >>> rebuilding python virtualenv '{VENV_DIR}': it was built from python "
              f"{rebuilt_from}, and this python3, the one root's --install ran under, is "
              f"{_this_minor()}\n", file=sys.stderr)
    else:
        print(f"\n >>> Creating python virtualenv '{VENV_DIR}'...\n", file=sys.stderr)

    rc = subprocess.call([sys.executable, "-m", "venv"] + (["--clear"] if rebuilt_from else [])
                         + [VENV_DIR])
    if rc != 0:
        err("00005", f"failed to create the venv at {VENV_DIR} [rc {rc}]")

    pip = os.path.join(VENV_DIR, "bin", "pip")
    rc = subprocess.call([pip, "install"] + VENV_DEPS)
    if rc != 0:
        err("00006", f"failed to install the dependencies {', '.join(VENV_DEPS)} "
                 f"into {VENV_DIR} [rc {rc}]")

    print(f"\n >>> DONE creating python virtualenv '{VENV_DIR}'.", file=sys.stderr)
    print("=" * 64, file=sys.stderr)

    # Re-exec with venv python, preserving all arguments
    _exec_in_venv()


# ---------------------------------------------------------------------------
# --install as ROOT: the firewall half, then the drop to the user.
# ---------------------------------------------------------------------------
# The oldest python3 the tool runs on (it uses match/case) -- asked by
# _import_tool(), before every import of the tool.
MIN_PYTHON = (3, 10)

# Set in the command root hands over with, so the run as the user knows the
# firewall half is done: without it, a firewall tool that exists means a
# user's own --install, which writes the ssh half alone and says the rules
# need root.  An environment variable because `su -l` passes nothing else but
# the command line itself.
INSTALL_FROM_ROOT_ENV = "MY_PLEX_INSTALL_FROM_ROOT"

# What root's --install takes beside --install: the config to read, and -Q.
# Anything else would be dropped without a word -- the run as the user is
# `--install` and nothing more -- so it is refused instead.
_ROOT_CONFIG_FLAGS = ("--config", "--config-file", "-C")


def install_asked(argv: "list[str]") -> bool:
    """True when argv asks for --install (an attached `--install=X` too: the
    tool refuses that one with its own error, which names the X)."""
    return any(a == "--install" or a.startswith("--install=") for a in argv_options(argv))


def _root_install_config(argv: "list[str]") -> "str | None":
    """The config file a root --install names (--config FILE, -C FILE,
    --config-file FILE, or the `=FILE` forms), or None.  Any other token is
    refused: root hands over `--install` alone, so whatever else was asked
    would silently not happen."""
    config = None
    rest = argv_options(argv)
    i = 0
    while i < len(rest):
        a = rest[i]
        name, eq, value = a.partition("=")
        if a in ("--install", "-Q", "--quiet") or a.startswith("--install="):
            pass
        elif name in _ROOT_CONFIG_FLAGS and eq and value:
            config = value
        elif a in _ROOT_CONFIG_FLAGS and i + 1 < len(rest) and not rest[i + 1].startswith("-"):
            config = rest[i + 1]
            i += 1
        else:
            err("00007", f"as root, --install takes only --config FILE (and -Q) beside it, "
                         f"and got {a!r}\n"
                         f"  root writes the firewall rules and hands over `my-plex --install`,\n"
                         f"  nothing more -- anything else would silently not run.\n"
                         f"Possible reasons:\n"
                         f"  - another command: run it as the user whose Plex this is, not as root")
        i += 1
    return config


def _root_install(launcher: str, argv: "list[str]") -> "NoReturn":
    """--install as root: the firewall half, then the drop.

    The python3 check comes first (#35): importing the tool asks it, and
    every step after it needs the tool.  The tool owns what --install needs
    to know -- the config, the remotes, the user -- and writes the rules
    (install_firewall()); THIS module owns who runs next and in what
    interpreter, so the drop is here.
    No venv is built and none is entered: root runs nothing but the stdlib,
    and the rules name the python3 that runs this, which exists before any
    venv does.
    """
    tool = _import_tool()
    config = _root_install_config(argv)
    try:
        user, named = tool.install_firewall(config)
    except Exception as unexpected:  # the top of root's --install half: one ERROR line, the trace in a file, exit 70
        # Outside the tool's run(), so its bug handler is called here: one
        # ERROR line and a trace file, never a traceback -- and no drop.
        tool.report_bug(unexpected)
    _drop_to(user, launcher, named)


def _drop_to(user: str, launcher: str, config: "str | None") -> "NoReturn":
    """Hand this --install over to USER, as a fresh login: `su -l` gives the
    run that user's HOME, USER, LOGNAME and PATH and nothing of root's
    environment -- every per-user path my-plex computes comes from HOME, so a
    run that kept root's would build the venv and write ~/.ssh in /var/root.

    The run names the python3 root ran under: the venv is then built from the
    Python the rules name.  CONFIG, the file named for this run that root
    read (None: the site config), travels as --config, since su keeps no
    environment -- $MY_PLEX_CONFIG would otherwise be lost on the way."""
    import shlex
    cmd = [sys.executable, "-I", "-S", launcher, "--install"]
    if config:
        cmd += ["--config", os.path.abspath(config)]
    line = f"{INSTALL_FROM_ROOT_ENV}=1 exec {shlex.join(cmd)}"
    print(f"\n >>> dropping to {user} for the rest -- nothing below this line runs as root\n",
          flush=True)
    sys.stderr.flush()
    try:
        os.execvp("su", ["su", "-l", user, "-c", line])
    except OSError as e:
        # Not "run --install as that user": that run writes the ssh half but
        # rebuilds no venv of another Python minor, as the run root hands
        # over does.  Root's again finds every rule already there and hands
        # over.
        err("00008", f"could not hand over to {user}: su: {e.strerror}\n"
                     f"  the firewall rules are written; the ssh half, as {user}, is not.\n"
                     f"  Once su runs here, run `my-plex --install` as root again: it finds\n"
                     f"  the rules already there and hands over.")
