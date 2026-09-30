def authenticate(client):
    token = "synthetic-test-token"
    return client.authorize(token)
