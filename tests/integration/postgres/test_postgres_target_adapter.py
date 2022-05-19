from pandas.core.frame import DataFrame
import pytest

from snowshu.adapters.target_adapters import BaseTargetAdapter
from snowshu.adapters.target_adapters.postgres_adapter import PostgresAdapter
from snowshu.core.models import Relation, Attribute, data_types
from snowshu.core.models.materializations import TABLE
from tests.common import rand_string


def test_create_database_if_not_exists(end_to_end):
    pg_adapter = PostgresAdapter(replica_metadata={})
    if pg_adapter.target != "localhost":
        pg_adapter._credentials.host = 'integration-test'

    DATABASE = rand_string(10)
    pg_adapter.create_database_if_not_exists(DATABASE)
    database_list = pg_adapter._get_all_databases()

    assert DATABASE in database_list


def test_create_schema_if_not_exists(end_to_end):
    pg_adapter = PostgresAdapter(replica_metadata={})
    if pg_adapter.target != "localhost":
        pg_adapter._credentials.host = 'integration-test'

    DATABASE, SCHEMA = [rand_string(10) for _ in range(2)]
    pg_adapter.create_database_if_not_exists(DATABASE)
    pg_adapter.create_schema_if_not_exists(DATABASE, SCHEMA)
    list = pg_adapter._get_all_schemas(DATABASE)

    assert SCHEMA in list


def test_get_all_databases(end_to_end):
    pg_adapter = PostgresAdapter(replica_metadata={})
    if pg_adapter.target != "localhost":
        pg_adapter._credentials.host = 'integration-test'
    
    db_list = pg_adapter._get_all_databases()
    databases = ['postgres', 'snowshu', 'snowshu_development']

    assert set(databases).issubset(db_list)


def test_get_all_schemas(end_to_end):
    pg_adapter = PostgresAdapter(replica_metadata={})
    if pg_adapter.target != "localhost":
        pg_adapter._credentials.host = 'integration-test'

    schemas_list = pg_adapter._get_all_schemas('snowshu_development')
    schemas_set = {'polymorphic_data', 'external_data', 'tests_data', 'source_system'}

    assert schemas_set.issubset(schemas_list)


def test_get_relations_from_database(end_to_end):
    pg_adapter = PostgresAdapter(replica_metadata={})
    if pg_adapter.target != "localhost":
        pg_adapter._credentials.host = 'integration-test'

    SCHEMA_OBJ = BaseTargetAdapter._DatabaseObject("snowshu",
                                                   Relation("snowshu", "snowshu", "replica_meta", "", None))
    relations_list = [Relation("snowshu", "snowshu", "replica_meta", TABLE, None)]
    received_relations_list = pg_adapter._get_relations_from_database(schema_obj=SCHEMA_OBJ)

    assert set(relations_list).issubset(received_relations_list)


def test_create_all_database_extensions(end_to_end):
    pg_adapter = PostgresAdapter(replica_metadata={})
    if pg_adapter.target != "localhost":
        pg_adapter._credentials.host = 'integration-test'

    extensions = 'citext'
    pg_adapter.create_all_database_extensions()
    statement = 'SELECT extname FROM pg_extension'
    conn = pg_adapter.get_connection()
    result = conn.execute(statement).fetchall()
    extensions_list = [r[0] for r in result]

    assert extensions in extensions_list


def test_load_data_into_relation(end_to_end):
    pg_adapter = PostgresAdapter(replica_metadata={})
    if pg_adapter.target != "localhost":
        pg_adapter._credentials.host = 'integration-test'

    id_column = "id"
    content_column = "content"
    columns = [
        Attribute(id_column, data_types.BIGINT),
        Attribute(content_column, data_types.VARCHAR)
    ]
    relation = Relation("snowshu", "snowshu", "replica_meta", TABLE, columns)
    relation.data = DataFrame({id_column: [1, 2, 3], content_column: [rand_string(5) for _ in range(3)]})
    pg_adapter.load_data_into_relation(relation)

    statement = "SELECT * FROM snowshu.snowshu.replica_meta"
    conn = pg_adapter.get_connection()
    result = conn.execute(statement).fetchall()

    assert len(result) == 3