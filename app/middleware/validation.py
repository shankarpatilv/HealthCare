import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from jsonschema import Draft202012Validator, FormatChecker

from app.middleware.error_handler import SchemaValidationError

_schema_path = Path(__file__).resolve().parent.parent / "schemas" / "plan.schema.json"
plan_schema = json.loads(_schema_path.read_text())

_validator = Draft202012Validator(plan_schema, format_checker=FormatChecker())


def validate_plan(data: Any) -> list[dict]:
    """Return a list of ajv-style error dicts; empty list means valid."""
    return [
        {
            "instancePath": "/" + "/".join(str(p) for p in err.absolute_path),
            "schemaPath": "#/" + "/".join(str(p) for p in err.absolute_schema_path),
            "keyword": err.validator,
            "message": err.message,
        }
        for err in _validator.iter_errors(data)
    ]


async def validate_plan_body(request: Request) -> Any:
    """FastAPI dependency: parses the JSON body, validates it, and returns it."""
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    errors = validate_plan(body)
    if errors:
        raise SchemaValidationError(errors)
    return body
