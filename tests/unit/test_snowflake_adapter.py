from unittest import mock
import pytest
from psycopg2 import OperationalError

from snowshu.adapters.source_adapters.snowflake_adapter import SnowflakeAdapter
from snowshu.core.models.credentials import Credentials
from snowshu.core.models.materializations import TABLE
from snowshu.core.models.relation import Relation
from snowshu.samplings.sample_methods import BernoulliSampleMethod
from tests.common import query_equalize, rand_string


def test_get_connection():
    sf = SnowflakeAdapter()
    USER, PASSWORD, ACCOUNT, DATABASE, ROLE = [rand_string(15) for _ in range(5)]

    creds = Credentials(user=USER, password=PASSWORD,
                        account=ACCOUNT, database=DATABASE)

    sf.credentials = creds

    conn_string = sf.get_connection()

    assert str(
        conn_string.url) == f'snowflake://{USER}:{PASSWORD}@{ACCOUNT}/{DATABASE}/'

    sf.credentials.role = ROLE
    conn_string = sf.get_connection()

    assert conn_string.url.render_as_string(hide_password=False) == \
           f'snowflake://{USER}:{PASSWORD}@{ACCOUNT}/{DATABASE}/?role={ROLE}'


def test_build_conn_string():
    sf = SnowflakeAdapter()
    USER, PASSWORD, ACCOUNT, DATABASE, ROLE = [rand_string(15) for _ in range(5)]

    creds = Credentials(user=USER,
                        password=PASSWORD,
                        account=ACCOUNT,
                        database=DATABASE,
                        role=ROLE)
    sf.credentials = creds
    conn_string = sf._build_conn_string()

    assert str(conn_string) == f'snowflake://{USER}:{PASSWORD}@{ACCOUNT}/{DATABASE}/?role={ROLE}'


def test_sample_statement():
    sf = SnowflakeAdapter()
    DATABASE, SCHEMA, TABLE = [rand_string(10) for _ in range(3)]
    DATABASE = sf._correct_case(DATABASE)
    SCHEMA = sf._correct_case(SCHEMA)
    TABLE = sf._correct_case(TABLE)
    relation = Relation(database=DATABASE,
                        schema=SCHEMA,
                        name=TABLE,
                        materialization=TABLE,
                        attributes=[])
    sample = sf.sample_statement_from_relation(relation, BernoulliSampleMethod(10,units="probability"))
    assert query_equalize(sample) == query_equalize(f"""
SELECT
    *
FROM 
    {DATABASE}.{SCHEMA}.{TABLE}
    SAMPLE BERNOULLI (10)
""")


def test_directional_statement():
    sf = SnowflakeAdapter()
    DATABASE, SCHEMA, TABLE, LOCAL_KEY, REMOTE_KEY = [
        rand_string(10) for _ in range(5)]
    relation = Relation(database=DATABASE,
                        schema=SCHEMA,
                        name=TABLE,
                        materialization=TABLE,
                        attributes=[])
    relation.core_query = f"""
SELECT
    *
FROM 
    {DATABASE}.{SCHEMA}.{TABLE}
    SAMPLE BERNOULLI (10)
"""
    statement = sf.predicate_constraint_statement(
        relation, True, LOCAL_KEY, REMOTE_KEY)
    assert query_equalize(statement) == query_equalize(f"""
{LOCAL_KEY} IN 
    ( SELECT  
        {REMOTE_KEY}
      AS {LOCAL_KEY}
    FROM (
SELECT
    *
FROM 
    {DATABASE}.{SCHEMA}.{TABLE}
    SAMPLE BERNOULLI (10)
))
""")


def test_analyze_wrap_statement():
    sf = SnowflakeAdapter()
    DATABASE, SCHEMA, NAME = [rand_string(10) for _ in range(3)]
    relation = Relation(database=DATABASE, schema=SCHEMA,
                        name=NAME, materialization=TABLE, attributes=[])
    sql = f"SELECT * FROM some_crazy_query"
    statement = sf.analyze_wrap_statement(sql, relation)
    assert query_equalize(statement) == query_equalize(f"""
WITH
    {relation.scoped_cte('SNOWSHU_COUNT_POPULATION')} AS (
SELECT
    COUNT(*) AS population_size
FROM
    {sf.quoted_dot_notation(relation)}
)
,{relation.scoped_cte('SNOWSHU_CORE_SAMPLE')} AS (
{sql}
)
,{relation.scoped_cte('SNOWSHU_CORE_SAMPLE_COUNT')} AS (
SELECT
    COUNT(*) AS sample_size
FROM
    {relation.scoped_cte('SNOWSHU_CORE_SAMPLE')}
)
SELECT
    s.sample_size AS sample_size
    ,p.population_size AS population_size
FROM
    {relation.scoped_cte('SNOWSHU_CORE_SAMPLE_COUNT')} s
INNER JOIN
    {relation.scoped_cte('SNOWSHU_COUNT_POPULATION')} p
ON
    1=1
LIMIT 1
""")


def test_directionally_wrap_statement_directional():
    sf = SnowflakeAdapter()
    sampling = BernoulliSampleMethod(50,units='probability')
    query = "SELECT * FROM highly_conditional_query"
    relmock=mock.MagicMock()
    relmock.scoped_cte=lambda x : x
    assert query_equalize(sf.directionally_wrap_statement(query,relmock, sampling)) == query_equalize(f"""
WITH
    {relmock.scoped_cte('SNOWSHU_FINAL_SAMPLE')} AS (
{query}
)
,{relmock.scoped_cte('SNOWSHU_DIRECTIONAL_SAMPLE')} AS (
SELECT
    *
FROM
    {relmock.scoped_cte('SNOWSHU_FINAL_SAMPLE')}
SAMPLE BERNOULLI (50)
)
SELECT 
    *
FROM 
    {relmock.scoped_cte('SNOWSHU_DIRECTIONAL_SAMPLE')}
""")


def test_retry_count_query():
    """ Verifies that the retry decorator works as expected """
    error_list = [OperationalError, OperationalError, OperationalError, SystemError, RuntimeError]
    with mock.patch("snowshu.adapters.source_adapters.SnowflakeAdapter._count_query", side_effect=error_list):
        sf = SnowflakeAdapter()
        with pytest.raises(SystemError) as exc:
            sf.check_count_and_query("select * from unknown_table", 10, False)
        
        # assert that the 4th error was raised
        assert exc.errisinstance(SystemError)
        assert sf.check_count_and_query.retry.statistics["attempt_number"] == 4


def test_quoted():
    sf = SnowflakeAdapter()
    val = rand_string(10)
    
    assert val == sf.quoted(val)


def test_quoted_for_spaced_string():
    sf = SnowflakeAdapter()
    val = rand_string(5) + ' ' + rand_string(6)
    
    assert f'"{val}"' == sf.quoted(val)


def test_sample_type_to_query_sql():
    sf = SnowflakeAdapter()
    sample_type = BernoulliSampleMethod(10, units="probability")
    qualifier = sample_type.probability

    assert sf._sample_type_to_query_sql(sample_type) == f"SAMPLE BERNOULLI ({qualifier})"
