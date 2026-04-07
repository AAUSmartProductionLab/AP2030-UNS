from __future__ import annotations

import contextlib
import io
import json
import re
from pathlib import Path
from typing import Any


def _issue(message: str, *, severity: str = "Violation", field: str | None = None) -> dict:
    return {
        "source": "metamodel",
        "severity": severity,
        "message": message,
        "field": field,
    }


_VERIFY_RE = re.compile(r"\[\s*VERIFY\s*:", re.IGNORECASE)
_IDSHORT_ALLOWED_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _path_join(base: str, segment: str) -> str:
    if not base:
        return segment
    return f"{base}.{segment}"


def _prevalidate_identifiers(node: Any, path: str = "") -> list[dict]:
    issues: list[dict] = []

    if isinstance(node, dict):
        for key, value in node.items():
            child_path = _path_join(path, str(key))

            if key == "idShort":
                value_str = str(value or "")
                if not value_str:
                    issues.append(_issue("idShort must not be empty.", field=child_path))
                else:
                    if _VERIFY_RE.search(value_str):
                        issues.append(
                            _issue(
                                "idShort contains a [VERIFY: ...] marker. idShort must be a stable identifier and cannot contain placeholders.",
                                field=child_path,
                            )
                        )
                    if not _IDSHORT_ALLOWED_RE.fullmatch(value_str):
                        issues.append(
                            _issue(
                                "idShort must contain only letters, digits, and underscore (AASd-002).",
                                field=child_path,
                            )
                        )

            if key in {"id", "globalAssetId"} and isinstance(value, str) and _VERIFY_RE.search(value):
                issues.append(
                    _issue(
                        f"{key} contains a [VERIFY: ...] marker. Identifiers/references must not contain placeholders.",
                        field=child_path,
                    )
                )

            issues.extend(_prevalidate_identifiers(value, child_path))

    elif isinstance(node, list):
        for index, item in enumerate(node):
            issues.extend(_prevalidate_identifiers(item, f"{path}[{index}]"))

    return issues


def _run_basyx_deserialization(json_text: str, json_path: Path) -> list[dict]:
    errors: list[dict] = []

    try:
        from basyx.aas.adapter import json as basyx_json_deserialization  # type: ignore
    except Exception as exc:
        return [_issue(f"BaSyx SDK unavailable or import failed: {exc}", severity="Warning")]

    reader_names = [
        "read_aas_json_file",
        "read_aas_json_string",
        "read_aas_json_stream",
    ]
    readers = [getattr(basyx_json_deserialization, name, None) for name in reader_names]
    readers = [reader for reader in readers if callable(reader)]

    if not readers:
        return [_issue("BaSyx JSON reader functions not found in installed SDK.", severity="Warning")]

    def parse_basyx_output(output: str, reader_name: str) -> list[dict]:
        issues: list[dict] = []
        if not output:
            return issues

        interesting_prefixes = (
            "Error while trying to convert JSON object",
            "Expected a SubmodelElement",
            "AASConstraintViolation",
        )

        seen: set[str] = set()
        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("Traceback") or line.startswith("File "):
                continue
            if not any(prefix in line for prefix in interesting_prefixes):
                continue
            if line in seen:
                continue
            seen.add(line)
            issues.append(_issue(f"BaSyx ({reader_name}): {line}"))
        return issues

    def call_reader(callable_reader, arg, reader_name: str) -> tuple[bool, Exception | None, list[dict]]:
        capture_out = io.StringIO()
        capture_err = io.StringIO()
        try:
            with contextlib.redirect_stdout(capture_out), contextlib.redirect_stderr(capture_err):
                callable_reader(arg)
            output_issues = parse_basyx_output(capture_out.getvalue() + "\n" + capture_err.getvalue(), reader_name)
            return True, None, output_issues
        except Exception as exc:
            output_issues = parse_basyx_output(capture_out.getvalue() + "\n" + capture_err.getvalue(), reader_name)
            return False, exc, output_issues

    for reader in readers:
        reader_name = getattr(reader, "__name__", "reader")

        success, exc, output_issues = call_reader(reader, json_path, reader_name)
        errors.extend(output_issues)
        if success:
            return errors
        if not isinstance(exc, TypeError):
            errors.append(_issue(f"BaSyx deserialization error via {reader_name}: {exc}"))

        try:
            with json_path.open("r", encoding="utf-8") as file_handle:
                success, exc, output_issues = call_reader(reader, file_handle, reader_name)
            errors.extend(output_issues)
            if success:
                return errors
            if not isinstance(exc, TypeError):
                errors.append(_issue(f"BaSyx deserialization error via {reader_name}: {exc}"))
        except Exception as exc:
            errors.append(_issue(f"BaSyx deserialization error via {reader_name}: {exc}"))

        success, exc, output_issues = call_reader(reader, json_text, reader_name)
        errors.extend(output_issues)
        if success:
            return errors
        if not isinstance(exc, TypeError):
            errors.append(_issue(f"BaSyx deserialization error via {reader_name}: {exc}"))

        success, exc, output_issues = call_reader(reader, io.StringIO(json_text), reader_name)
        errors.extend(output_issues)
        if success:
            return errors
        if exc is not None:
            errors.append(_issue(f"BaSyx deserialization error via {reader_name}: {exc}"))

    if errors:
        deduped: list[dict] = []
        seen_messages: set[str] = set()
        for issue in errors:
            message = str(issue.get("message", "")).strip()
            if not message or message in seen_messages:
                continue
            seen_messages.add(message)
            deduped.append(issue)
        return deduped
    return [_issue("BaSyx deserialization failed using all known reader signatures.")]


def _run_basyx_schema_if_available(json_text: str) -> list[dict]:
    try:
        from aas_compliance_tool import compliance_check_json  # type: ignore
    except Exception:
        return []

    check_schema = getattr(compliance_check_json, "_check_schema", None)
    if not callable(check_schema):
        return []

    try:
        stream = io.StringIO(json_text)
        check_schema(stream, None)
        return []
    except TypeError:
        return []
    except Exception as exc:
        return [_issue(f"BaSyx JSON schema check reported: {exc}")]


def validate_json_with_basyx(input_json: Path) -> dict[str, Any]:
    json_text = input_json.read_text(encoding="utf-8")

    try:
        document = json.loads(json_text)
    except json.JSONDecodeError as exc:
        return {
            "conforms": False,
            "issues": [_issue(f"Input is not valid JSON for BaSyx validation: {exc}", field=f"line:{exc.lineno}")],
            "warnings": [],
        }

    identifier_issues = _prevalidate_identifiers(document)

    deserialization_issues = _run_basyx_deserialization(json_text, input_json)
    schema_issues = _run_basyx_schema_if_available(json_text)

    issues: list[dict] = []
    warnings: list[dict] = []
    for item in [*identifier_issues, *deserialization_issues, *schema_issues]:
        if item.get("severity") == "Warning":
            warnings.append(item)
        else:
            issues.append(item)

    return {
        "conforms": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
    }
