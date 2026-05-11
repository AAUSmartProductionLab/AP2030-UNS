from __future__ import annotations

import logging

from SPARQLWrapper import JSON, POST, SPARQLWrapper


class SparqlClient:
    def __init__(
        self,
        update_url: str,
        query_url: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._update_url = update_url
        self._query_url = query_url
        self._username = username
        self._password = password
        self._logger = logging.getLogger("kg-bridge.sparql")

    def _configure_auth(self, wrapper: SPARQLWrapper) -> None:
        if self._username and self._password:
            wrapper.setCredentials(self._username, self._password)

    def update(self, statement: str) -> None:
        self._logger.debug("Executing SPARQL UPDATE with %d chars", len(statement))
        wrapper = SPARQLWrapper(self._update_url)
        wrapper.setMethod(POST)
        wrapper.setQuery(statement)
        self._configure_auth(wrapper)
        wrapper.query()

    def ask(self, ask_query: str) -> bool:
        wrapper = SPARQLWrapper(self._query_url)
        wrapper.setMethod(POST)
        wrapper.setQuery(ask_query)
        wrapper.setReturnFormat(JSON)
        self._configure_auth(wrapper)

        data = wrapper.query().convert()
        return bool(data.get("boolean", False))
