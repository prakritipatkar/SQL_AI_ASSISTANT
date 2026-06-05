"""Shared core: convert plain English into a safe SQL SELECT query using Google Gemini.

This module is intentionally framework-agnostic so it can be reused by:
  - the Flask website (Phase 1)
  - a VS Code extension backend (Phase 2)
"""
from __future__ import annotations

import os
import re

from google import genai
from google.genai import errors

# Only SELECT statements are allowed to run. Everything else is blocked.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|replace|grant|revoke|attach|pragma)\b",
    re.IGNORECASE,
)


class SQLGenerationError(Exception):
    """Raised when a query cannot be generated or is unsafe."""


def _client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise SQLGenerationError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return genai.Client(api_key=api_key)


def _build_prompt(question: str, schema: str) -> str:
    return f"""You are an expert SQLite analyst.
Convert the user's question into a single valid SQLite SELECT query.

Rules:
- Use ONLY the tables and columns from the schema below.
- Return ONLY the SQL. No explanation, no markdown fences.
- Generate a read-only SELECT query. Never modify data.

Database schema:
{schema}

User question: "{question}"

SQL:"""


def _clean(sql: str) -> str:
    """Strip markdown fences/backticks the model sometimes adds."""
    sql = sql.strip()
    sql = re.sub(r"^```(?:sql)?", "", sql, flags=re.IGNORECASE).strip()
    sql = re.sub(r"```$", "", sql).strip()
    return sql.rstrip(";").strip()


def is_safe(sql: str) -> bool:
    """Allow only single-statement SELECT queries."""
    if ";" in sql:  # block stacked queries
        return False
    if not sql.lower().lstrip().startswith("select"):
        return False
    if _FORBIDDEN.search(sql):
        return False
    return True


def english_to_sql(question: str, schema: str, model: str = "gemini-2.5-flash") -> str:
    """Convert an English question into a safe SQL SELECT query.

    Raises SQLGenerationError if generation fails or the result is unsafe.
    """
    if not question or not question.strip():
        raise SQLGenerationError("Please enter a question.")

    client = _client()
    try:
        response = client.models.generate_content(
            model=model, contents=_build_prompt(question, schema)
        )
    except errors.ClientError as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            raise SQLGenerationError(
                "Free tier quota exhausted. Wait a few minutes or upgrade your Gemini API plan at https://aistudio.google.com"
            )
        raise SQLGenerationError(f"API error: {e}")
    
    sql = _clean(getattr(response, "text", "") or "")

    if not sql:
        raise SQLGenerationError("The model did not return any SQL.")
    if not is_safe(sql):
        raise SQLGenerationError(
            "Generated query was blocked for safety (only SELECT queries are allowed)."
        )
    return sql
