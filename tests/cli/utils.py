import os
import subprocess


def run_cmd(app, cmd, is_app=True):
    env = dict(os.environ)
    if is_app:
        env["SAFFIER_DEFAULT_APP"] = app
    if "VIRTUAL_ENV" not in env:
        cmd = f"{env['PWD']}/venv/bin/{cmd}"
    result = subprocess.run(cmd, capture_output=True, env=env, shell=True)
    print("\n$ " + cmd)
    print(result.stdout.decode("utf-8"))
    print(result.stderr.decode("utf-8"))
    return result.stdout, result.stderr, result.returncode
