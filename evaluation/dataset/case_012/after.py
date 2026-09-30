def delete(cursor, user_id):
    cursor.execute(f"DELETE FROM users WHERE id = {user_id}")
