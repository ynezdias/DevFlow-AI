import subprocess
def echo(name):
    return subprocess.run(["echo", name], check=True)
