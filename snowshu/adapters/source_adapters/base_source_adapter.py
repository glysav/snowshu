import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterable, List, Tuple

import pandas as pd

from snowshu.adapters import BaseSQLAdapter
from snowshu.configs import MAX_ALLOWED_DATABASES, MAX_ALLOWED_ROWS
from snowshu.core.models import DataType, Relation
from snowshu.core.models.relation import at_least_one_full_pattern_match
from snowshu.core.utils import correct_case
from snowshu.logger import Logger, duration

logger = Logger().logger


class BaseSourceAdapter(BaseSQLAdapter):
    name = ''
    MAX_ALLOWED_DATABASES = MAX_ALLOWED_DATABASES
    MAX_ALLOWED_ROWS = MAX_ALLOWED_ROWS
    DEFAULT_CASE = 'lower'
    SUPPORTS_CROSS_DATABASE = False
    SUPPORTED_FUNCTIONS = set()

    def __init__(self, preserve_case: bool = False):
        self.preserve_case = preserve_case
        super().__init__()
        for attr in ('DATA_TYPE_MAPPINGS', 'SUPPORTED_SAMPLE_METHODS',):
            if not hasattr(self, attr):
                raise NotImplementedError(
                    f'Source adapter requires attribute f{attr} but was not set.')

    def _safe_query(self, query_sql: str) -> pd.DataFrame:
        """runs the query and closes the connection."""
        logger.debug('Beginning query execution...')
        start = time.time()
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.connect()
            # we make the STRONG assumption that all responses will be small enough
            # to live in-memory (because sampling engine).
            # further safety added by the constraints in snowshu.configs
            # this allows the connection to return to the pool
            logger.debug(f'Executed query in {time.time()-start} seconds.')
            frame = pd.read_sql_query(query_sql, conn)
            logger.debug("Dataframe datatypes: %s", str(frame.dtypes).replace('\n', ' | '))
            if len(frame) > 0:
                for col in frame.columns:
                    logger.debug("Pandas loaded element 0 of column %s as %s", col, type(frame[col][0]))
            else:
                logger.debug("Dataframe is empty")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.dispose()
        return frame

    def _count_query(self, query: str) -> int:
        """wraps any query in a COUNT statement, returns that integer."""
        raise NotImplementedError()

    def check_count_and_query(self, query: str, max_count: int, unsampled: bool) -> pd.DataFrame:
        """checks the count, if count passes returns results as a dataframe."""
        raise NotImplementedError()

    def scalar_query(self, query: str) -> Any:
        """Returns only a single value.

        When the database is expected to return a single row with a single column, 
        this method will return the raw value from that cell. Will throw a :class:`TooManyRecords
        <snowshu.exceptions.TooManyRecords>` exception.

        Args:
            query: the query to execute.

        Returns:
            the raw value from cell [0][0]
        """
        return self.check_count_and_query(query, 1, False).iloc[0][0]

    def _get_data_type(self, source_type: str) -> DataType:
        try:
            return self.DATA_TYPE_MAPPINGS[source_type.lower()]
        except KeyError as err:
            logger.error(
                '%s adapter does not support data type %s.', self.CLASSNAME, source_type)
            raise err
