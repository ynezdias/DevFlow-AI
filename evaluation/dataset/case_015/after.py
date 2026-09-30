from pathlib import Path
def download(name):
    return (Path("/srv/public") / name).read_text()
