import subprocess
def run(name):
    subprocess.run("echo " + name, shell=True)
