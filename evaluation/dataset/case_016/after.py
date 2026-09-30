import os
def remove(name):
    os.remove(os.path.join("/srv/uploads", name))
