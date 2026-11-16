"""Types a real session into bash and the Python REPL, for asciinema to record.

Every output on screen comes from the real programs; only the typing is scripted.
"""
import os
import sys
import time

import pexpect

VENV = sys.argv[1]
WORK = sys.argv[2]

env = dict(os.environ)
env.update({
    "PS1": "$ ",
    "PATH": os.path.join(VENV, "bin") + os.pathsep + env["PATH"],
    "VIRTUAL_ENV": VENV,
    "PYTHON_BASIC_REPL": "1",
    "PYTHON_COLORS": "0",
    "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    "PIP_NO_CACHE_DIR": "1",
    "TERM": "xterm-256color",
})

child = pexpect.spawn("bash", ["--norc", "--noprofile"], cwd=WORK, env=env,
                      dimensions=(26, 96), timeout=300)
child.logfile_read = sys.stdout.buffer


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        try:
            child.read_nonblocking(65536, timeout=0.05)
        except pexpect.TIMEOUT:
            pass
        sys.stdout.buffer.flush()


def type_line(text, prompt, pause=1.4):
    for ch in text:
        child.send(ch)
        pump(0.035 if ch != " " else 0.05)
    child.send("\r")
    child.expect_exact(prompt)
    sys.stdout.buffer.flush()
    pump(pause)


child.expect_exact("$ ")
pump(0.8)
type_line("pip install -q persistent-memory-mcp", "$ ", 0.8)
type_line("persistent-memory --version", "$ ", 1.2)
type_line("python", ">>> ", 0.6)

steps = [
    ("from persistent_memory import PersistentMemory", 0.6),
    ('m = PersistentMemory("store", "team", create=True)', 0.8),
    ('port = m.remember("The staging database listens on port 6543.", source_id="db-port")', 0.8),
    ('note = m.derive("Open port 6543 on the staging firewall.", parents=[port["ref"]])', 0.8),
    ('[i["text"] for i in m.search("staging port")["items"]]', 2.6),
    ('v = port["ref"]["version_id"]   # the port changes: correct the source', 0.6),
    ('c = m.correct("db-port", "The staging database listens on port 6544.", expected_version=v)', 0.8),
    ('m.read(note["ref"])["state"]   # the note built on 6543 is no longer served', 2.4),
    ('[i["text"] for i in m.search("staging port")["items"]]', 2.6),
    ('gone = m.withdraw("db-port", "database decommissioned")', 0.8),
    ('m.search("staging port")["items"]', 2.0),
    ('m.explain("db-port")["reason"]', 3.0),
]
for line, pause in steps:
    type_line(line, ">>> ", pause)

child.sendcontrol("d")
child.expect_exact("$ ")
pump(0.5)
child.sendline("exit")
child.expect(pexpect.EOF)
