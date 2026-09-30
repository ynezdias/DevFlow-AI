def lookup(cursor, name):
    return cursor.execute("SELECT * FROM users WHERE name = '" + name + "'")
