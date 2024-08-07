import os
import subprocess


def run_cmd(app, cmd, is_app=True):
    env = dict(os.environ)
    if is_app:
        env["SAFFIER_DEFAULT_APP"] = app
    # CI uses something different as workdir and we aren't hatch test yet.
    if "VIRTUAL_ENV" not in env:
        basedir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if os.path.isdir(f"{basedir}/venv/bin/"):
            cmd = f"{basedir}/venv/bin/{cmd}"
    result = subprocess.run(cmd, capture_output=True, env=env, shell=True)
    print("\n$ " + cmd)
    print(result.stdout.decode("utf-8"))
    print(result.stderr.decode("utf-8"))
    return result.stdout, result.stderr, result.returncode
