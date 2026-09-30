def save(db):
    try:
        db.commit()
    except Exception:
        pass
    return True
