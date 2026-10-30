"""Run one recoverable workflow in the worker process, under an OS-held lease."""
from contextlib import redirect_stdout, redirect_stderr
import json
import os
from pathlib import Path
import runpy
import sys
import threading
import time

from .recovery import atomic_json, exclusive


def main():
    folder = Path(sys.argv[1]).resolve()
    command = sys.argv[2:]
    # The launcher supplies the fixed Python entry point, never a saved shell command.
    script = Path(command[2]).resolve()
    with exclusive(folder / 'worker.lock'):
        state = dict(status='running', exit_code=None, pid=os.getpid())
        stop = threading.Event()

        def write_state():
            atomic_json(folder / 'worker.json', {**state, 'heartbeat': time.time()})

        def publish():
            while not stop.wait(1):
                write_state()

        write_state()
        thread = threading.Thread(target=publish, daemon=True)
        thread.start()
        code = 0
        try:
            with (folder / 'execution.log').open('a', encoding='utf-8', buffering=1) as output:
                with redirect_stdout(output), redirect_stderr(output):
                    sys.argv = [str(script), *command[3:]]
                    try:
                        runpy.run_path(str(script), run_name='__main__')
                    except SystemExit as error:
                        code = error.code if isinstance(error.code, int) else 1
                    except Exception as error:
                        print(json.dumps(dict(passed=False, error=str(error))), flush=True)
                        code = 1
        finally:
            stop.set()
            thread.join()
            state.update(status='completed' if code == 0 else 'stopped', exit_code=code)
            write_state()


if __name__ == '__main__':
    main()
