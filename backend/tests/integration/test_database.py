from tests.support import *
from sqlalchemy.exc import IntegrityError
pytestmark = pytest.mark.usefixtures("database")

def test_database_unique_constraint(database):
    payload = dict(repository_name="constraint/"+str(uuid4()), pull_request_number=1, head_sha="b"*40)
    database.add(ReviewJob(**payload))
    database.flush()
    with pytest.raises(IntegrityError), database.begin_nested():
        database.add(ReviewJob(**payload))
        database.flush()
