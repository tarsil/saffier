import os
import subprocess
import sys


def run_cmd(app, cmd, is_app=True):
    env = dict(os.environ)
    basedir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env["PATH"] = f"{os.path.dirname(sys.executable)}{os.pathsep}{env.get('PATH', '')}"
    pythonpath = env.get("PYTHONPATH")
    if pythonpath:
        paths = pythonpath.split(os.pathsep)
        if basedir not in paths:
            env["PYTHONPATH"] = f"{basedir}{os.pathsep}{pythonpath}"
    else:
        env["PYTHONPATH"] = basedir
    if is_app:
        env["SAFFIER_DEFAULT_APP"] = app
    result = subprocess.run(cmd, capture_output=True, env=env, shell=True)
    print("\n$ " + cmd)
    print(result.stdout.decode("utf-8"))
    print(result.stderr.decode("utf-8"))
    return result.stdout, result.stderr, result.returncode
