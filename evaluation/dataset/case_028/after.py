import os
def connect(client):
    return client.login(password=os.environ["APP_PASSWORD"])
