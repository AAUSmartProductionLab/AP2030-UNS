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


class DualSparqlClient:
    """Writes to a primary SPARQL endpoint (blocking) and a secondary
    SPARQL endpoint (best-effort). Both endpoints receive every write
    and stay in sync. Secondary failures are logged but never propagated,
    so a rare visualization backend outage never blocks the pipeline.

    For GraphDB Free, set the update URL to:
      http://graphdb:7200/repositories/{repo}/statements
    (the /statements endpoint accepts application/sparql-update)."""

    def __init__(
        self,
        primary: SparqlClient,
        secondary: SparqlClient | None = None,
    ) -> None:
        self._primary = primary
        self._secondary = secondary
        self._logger = logging.getLogger("kg-bridge.dual-sparql")
        self._secondary_has_failed = False

    def update(self, statement: str) -> None:
        self._primary.update(statement)
        if self._secondary is not None:
            try:
                self._secondary.update(statement)
                if self._secondary_has_failed:
                    self._secondary_has_failed = False
                    self._logger.info("Secondary SPARQL endpoint recovered")
            except Exception:
                if not self._secondary_has_failed:
                    self._secondary_has_failed = True
                    self._logger.warning(
                        "Secondary SPARQL update failed (first occurrence), "
                        "subsequent failures will be logged at DEBUG level",
                        exc_info=True,
                    )
                else:
                    self._logger.debug(
                        "Secondary SPARQL update failed (repeated)", exc_info=True
                    )

    def ask(self, ask_query: str) -> bool:
        return self._primary.ask(ask_query)
