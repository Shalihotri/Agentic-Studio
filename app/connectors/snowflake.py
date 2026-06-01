from collections.abc import Sequence
import base64
from typing import Any

from cryptography.hazmat.primitives import serialization
import snowflake.connector
from app.config import Settings
from app.models import SnowflakeMetadataResponse, SnowflakeSelection

class SnowflakeClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _connect_kwargs(self) -> dict[str, Any]:
        connect_kwargs: dict[str, Any] = {
            "account": self._settings.snowflake_account,
            "user": self._settings.snowflake_user,
            "warehouse": self._settings.snowflake_warehouse,
            "authenticator": self._settings.snowflake_authenticator,
        }
        if self._settings.snowflake_database:
            connect_kwargs["database"] = self._settings.snowflake_database
        if self._settings.snowflake_schema:
            connect_kwargs["schema"] = self._settings.snowflake_schema
        if self._settings.snowflake_role:
            connect_kwargs["role"] = self._settings.snowflake_role

        authenticator = self._settings.snowflake_authenticator.lower()
        if authenticator == "snowflake":
            connect_kwargs["password"] = self._settings.snowflake_password
        elif authenticator == "snowflake_jwt":
            if self._settings.snowflake_private_key:
                connect_kwargs["private_key"] = self._load_private_key_bytes(
                    self._settings.snowflake_private_key
                )
            else:
                connect_kwargs["private_key_file"] = str(
                    self._settings.snowflake_private_key_file
                )
                if self._settings.snowflake_private_key_file_pwd:
                    connect_kwargs["private_key_file_pwd"] = (
                        self._settings.snowflake_private_key_file_pwd
                    )
        return connect_kwargs

    def _connect(self):
        return snowflake.connector.connect(**self._connect_kwargs())

    def _load_private_key_bytes(self, raw_key: str) -> bytes:
        key_text = raw_key.strip()
        if "BEGIN" not in key_text:
            key_bytes = base64.b64decode(key_text)
        else:
            key_bytes = key_text.replace("\\n", "\n").encode("utf-8")

        password = (
            self._settings.snowflake_private_key_file_pwd.encode("utf-8")
            if self._settings.snowflake_private_key_file_pwd
            else None
        )
        private_key = serialization.load_pem_private_key(
            key_bytes,
            password=password,
        )
        return private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return f'"{identifier.replace(chr(34), chr(34) * 2)}"'

    def _apply_selection(self, cursor, selection: SnowflakeSelection | None) -> None:
        if not selection:
            return
        if selection.role:
            cursor.execute(f"USE ROLE {self._quote_identifier(selection.role)}")
        if selection.warehouse:
            cursor.execute(f"USE WAREHOUSE {self._quote_identifier(selection.warehouse)}")
        if selection.database:
            cursor.execute(f"USE DATABASE {self._quote_identifier(selection.database)}")
        if selection.schema_name:
            cursor.execute(f"USE SCHEMA {self._quote_identifier(selection.schema_name)}")

    def _selected_table_query(
        self, selection: SnowflakeSelection | None, max_rows: int
    ) -> str | None:
        if not selection or not selection.table:
            return None
        parts = [
            item
            for item in (selection.database, selection.schema_name, selection.table)
            if item
        ]
        if len(parts) != 3:
            return None
        qualified_table = ".".join(self._quote_identifier(part) for part in parts)
        return f"SELECT * FROM {qualified_table} LIMIT {max_rows}"

    def run_query(
        self,
        sql_query: str,
        max_rows: int,
        selection: SnowflakeSelection | None = None,
    ) -> list[dict[str, Any]]:
        selected_table_query = self._selected_table_query(selection, max_rows)
        if selected_table_query and sql_query.strip() == "Provide your SQL Query.":
            sql_query = selected_table_query

        connection = self._connect()
        try:
            with connection.cursor(snowflake.connector.DictCursor) as cursor:
                self._apply_selection(cursor, selection)
                cursor.execute(sql_query)
                rows: Sequence[dict[str, Any]] = cursor.fetchmany(max_rows)
                return [dict(row) for row in rows]
        finally:
            connection.close()

    def get_metadata(
        self, selection: SnowflakeSelection | None = None
    ) -> SnowflakeMetadataResponse:
        connection = self._connect()
        try:
            with connection.cursor(snowflake.connector.DictCursor) as cursor:
                self._apply_selection(cursor, selection)
                roles = self._show_roles(cursor)
                warehouses = self._show_values(cursor, "SHOW WAREHOUSES", "name")
                if self._settings.snowflake_warehouse:
                    warehouses = sorted(
                        set([*warehouses, self._settings.snowflake_warehouse])
                    )
                databases = self._show_values(cursor, "SHOW DATABASES", "name")
                schemas: list[str] = []
                tables: list[str] = []
                if selection and selection.database:
                    database = self._quote_identifier(selection.database)
                    schemas = self._show_values(
                        cursor,
                        f"SHOW SCHEMAS IN DATABASE {database}",
                        "name",
                    )
                if selection and selection.database and selection.schema_name:
                    schema = (
                        f"{self._quote_identifier(selection.database)}."
                        f"{self._quote_identifier(selection.schema_name)}"
                    )
                    tables = self._show_values(
                        cursor,
                        f"SHOW TABLES IN SCHEMA {schema}",
                        "name",
                    )
                return SnowflakeMetadataResponse(
                    roles=roles,
                    warehouses=warehouses,
                    databases=databases,
                    schemas=schemas,
                    tables=tables,
                )
        finally:
            connection.close()

    def _show_roles(self, cursor) -> list[str]:
        try:
            user = self._quote_identifier(self._settings.snowflake_user)
            return self._show_values(cursor, f"SHOW GRANTS TO USER {user}", "role")
        except Exception:
            return self._show_values(cursor, "SELECT CURRENT_ROLE() AS role", "ROLE")

    @staticmethod
    def _show_values(cursor, statement: str, key: str) -> list[str]:
        cursor.execute(statement)
        rows: Sequence[dict[str, Any]] = cursor.fetchall()
        values = []
        for row in rows:
            normalized = {str(k).lower(): v for k, v in dict(row).items()}
            value = normalized.get(key.lower())
            if value:
                values.append(str(value))
        return sorted(set(values))
