"""Opt-in real Herdr popup test using an isolated HOME, config and server."""
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import struct
import subprocess
import tempfile
import termios
import time
import unittest


@unittest.skipUnless(os.environ.get("RUN_HERDR_INTEGRATION") == "1", "requires installed Herdr")
class HerdrIntegration(unittest.TestCase):
    def test_menu_cancel_launch_cwd_and_keep_output(self):
        binary = shutil.which("herdr")
        self.assertIsNotNone(binary)
        plugin = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix="ft-qa-", dir="/tmp") as temp:
            root = Path(temp); work = root / "project 한글"; work.mkdir()
            for name in ("home", "config", "state", "data"): (root / name).mkdir()
            report = root / "report.json"
            tool = root / "tool.py"
            tool.write_text('import json,os,sys\nfrom pathlib import Path\n' +
                            f'Path({str(report)!r}).write_text(json.dumps([os.getcwd(),sys.argv[1:]]))\n' +
                            'print("TOOL_OUTPUT_VISIBLE",flush=True)\nsys.exit(7)\n')
            shell = root / "shell"
            import shlex
            shell.write_text('#!/bin/sh\ncd ' + shlex.quote(str(work)) + '\nprintf "READY_FOR_MENU\\n"\nexec /bin/sh\n'); shell.chmod(0o755)
            config = root / "config.toml"
            config.write_text(f'onboarding=false\n[terminal]\ndefault_shell={json.dumps(str(shell))}\n'
                              '[update]\nversion_check=false\nmanifest_check=false\n'
                              '[keys]\nprefix="ctrl+a"\n[[keys.command]]\nkey="prefix+f"\n'
                              'type="plugin_action"\ncommand="ds-argus.floating-tools.open"\n')
            env = {k:v for k,v in os.environ.items() if not k.startswith("HERDR_")}
            env.update(HOME=str(root / "home"), XDG_CONFIG_HOME=str(root / "config"),
                       XDG_STATE_HOME=str(root / "state"), XDG_DATA_HOME=str(root / "data"),
                       HERDR_CONFIG_PATH=str(config), TERM="xterm-256color", SHELL=str(shell))
            userconfig = root / "config/herdr/plugins/config/ds-argus.floating-tools"
            userconfig.mkdir(parents=True)
            (userconfig / "config.toml").write_text('[[tools]]\nid="test"\nkey="t"\nname="Test tool"\nicon="󰊢"\n' +
                f'command={json.dumps([shutil.which("python3"), str(tool), "space arg", "$(id)"], ensure_ascii=False)}\n'
                'close_on_exit=false\nwidth="70%"\nheight="60%"\n')
            server = None; client = None; fd = None
            with (root / "server.log").open("wb") as log:
                try:
                    server = subprocess.Popen([binary,"--session","qa","server"],cwd=work,env=env,stdout=log,stderr=log,start_new_session=True)
                    sock = root / "config/herdr/sessions/qa/herdr.sock"
                    deadline = time.monotonic()+10
                    while not sock.exists():
                        if time.monotonic()>deadline or server.poll() is not None: self.fail("server did not start")
                        time.sleep(0.05)
                    subprocess.run([binary,"--session","qa","plugin","link",str(plugin)],env=env,check=True,stdout=log,stderr=log,timeout=10)
                    client,fd=pty.fork()
                    if client==0:
                        os.chdir(work); os.execve(binary,[binary,"--session","qa"],env)
                    fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',32,100,0,0))
                    output=bytearray()
                    def pump(predicate,timeout=10):
                        end=time.monotonic()+timeout
                        while time.monotonic()<end:
                            if select.select([fd],[],[],0.05)[0]:
                                try: output.extend(os.read(fd,65536))
                                except OSError: pass
                            if predicate(): return
                        import re
                        clean = re.sub(rb'\x1b\[[0-?]*[ -/]*[@-~]', b'', bytes(output))
                        self.fail('PTY timeout: ' + repr(clean[-6000:]))
                    def settle():
                        start=time.monotonic(); pump(lambda:time.monotonic()-start>0.25,1)
                    pump(lambda:b'READY_FOR_MENU' in output)
                    os.write(fd,b'\x01f'); pump(lambda:b'TOOLS' in output)
                    os.write(fd,b'q'); settle(); self.assertFalse(report.exists())
                    output.clear(); os.write(fd,b'\x01f'); pump(lambda:b'TOOLS' in output)
                    os.write(fd,b't'); pump(lambda:report.exists())
                    self.assertEqual(json.loads(report.read_text()),[str(work.resolve()),['space arg','$(id)']])
                    import re
                    def visible_text():
                        clean = re.sub(rb'\x1b\[[0-?]*[ -/]*[@-~]', b'', bytes(output))
                        return re.sub(rb'\s+', b'', clean)
                    pump(lambda: b'PressEntertoclose' in visible_text())
                    self.assertIn(b'status7', visible_text())
                    os.write(fd,b'\r'); settle()
                    output.clear(); os.write(fd,b'\x01f'); pump(lambda:b'TOOLS' in output)
                    os.write(fd,b'q'); settle()
                finally:
                    if client:
                        try: os.kill(client,signal.SIGKILL)
                        except ProcessLookupError: pass
                        os.waitpid(client,0)
                    if fd is not None: os.close(fd)
                    if server and server.poll() is None:
                        os.killpg(server.pid,signal.SIGKILL); server.wait(timeout=5)


if __name__ == '__main__': unittest.main()
