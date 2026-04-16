from collections.abc import Sequence
from typing import Any
import snowflake.connector
from config import Settings

class SnowflakeClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def run_query(self, sql_query: str, max_rows: int) -> list[dict[str, Any]]:
        connect_kwargs = {
            "account": self._settings.snowflake_account,
            "user": self._settings.snowflake_user,
            "warehouse": self._settings.snowflake_warehouse,
            "database": self._settings.snowflake_database,
            "schema": self._settings.snowflake_schema,
            "role": self._settings.snowflake_role,
            "authenticator": self._settings.snowflake_authenticator,
        }
        if self._settings.snowflake_authenticator.lower() == "snowflake":
            connect_kwargs["password"] = self._settings.snowflake_password

        connection = snowflake.connector.connect(**connect_kwargs)
        try:
            with connection.cursor(snowflake.connector.DictCursor) as cursor:
                cursor.execute(sql_query)
                rows: Sequence[dict[str, Any]] = cursor.fetchmany(max_rows)
                return [dict(row) for row in rows]
        finally:
            connection.close()
