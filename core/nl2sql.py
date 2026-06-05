"""Shared core: convert plain English into a safe SQL SELECT query using Google Gemini.

Falls back to a keyword-based rule engine if Gemini is unavailable.

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


# ============================================================================
# Gemini-based generation
# ============================================================================

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


# ============================================================================
# Keyword-based fallback (no AI required)
# ============================================================================

def _parse_schema_tables(schema: str) -> dict:
    """Parse schema string into {table_name: [col1, col2, ...]}."""
    tables = {}
    for line in schema.splitlines():
        line = line.strip()
        match = re.match(r"(\w+)\((.+)\)", line)
        if match:
            table = match.group(1).lower()
            cols_raw = match.group(2)
            cols = [re.split(r"\s+", c.strip())[0].lower() for c in cols_raw.split(",")]
            tables[table] = cols
    return tables


def _keyword_fallback(question: str, schema: str):
    """
    Rule-based SQL generator for common English patterns.
    Returns a SQL string or None if no rule matched.

    Supported patterns (case-insensitive):
      - show all / list all / get all       -> SELECT * FROM <table>
      - count [rows] [in] <table>           -> SELECT COUNT(*) FROM <table>
      - top N <table> [by <col>]            -> SELECT * ORDER BY <col> DESC LIMIT N
      - show <table> where <col> = <value>  -> SELECT * WHERE col = value
      - sum/total <col> [from] <table>      -> SELECT SUM(col) FROM table
      - average/avg <col> [from] <table>    -> SELECT AVG(col) FROM table
      - max/min <col> [from] <table>        -> SELECT MAX/MIN(col) FROM table
      - order <table> by <col> [asc/desc]   -> SELECT * ORDER BY col
    """
    q = question.lower().strip()
    tables = _parse_schema_tables(schema)

    if not tables:
        return None

    def find_table(text):
        for t in tables:
            if t in text:
                return t
        words = re.findall(r"\w+", text)
        for w in words:
            for t in tables:
                if w in t or t in w:
                    return t
        return next(iter(tables))

    def find_col(table, hint):
        cols = tables.get(table, [])
        hint_words = re.findall(r"\w+", hint.lower())
        for hw in hint_words:
            for c in cols:
                if hw in c or c in hw:
                    return c
        return None

    # COUNT
    if re.search(r"\b(count|how many)\b", q):
        table = find_table(q)
        if table:
            return f"SELECT COUNT(*) AS total FROM {table}"

    # SUM / TOTAL
    m = re.search(r"\b(sum|total)\b\s+(\w+)", q)
    if m:
        col_hint = m.group(2)
        table = find_table(q)
        if table:
            col = find_col(table, col_hint) or col_hint
            return f"SELECT SUM({col}) AS total_{col} FROM {table}"

    # AVERAGE / AVG
    m = re.search(r"\b(average|avg)\b\s+(\w+)", q)
    if m:
        col_hint = m.group(2)
        table = find_table(q)
        if table:
            col = find_col(table, col_hint) or col_hint
            return f"SELECT AVG({col}) AS avg_{col} FROM {table}"

    # MAX
    m = re.search(r"\bmax(?:imum)?\b\s+(\w+)", q)
    if m:
        col_hint = m.group(1)
        table = find_table(q)
        if table:
            col = find_col(table, col_hint) or col_hint
            return f"SELECT MAX({col}) AS max_{col} FROM {table}"

    # MIN
    m = re.search(r"\bmin(?:imum)?\b\s+(\w+)", q)
    if m:
        col_hint = m.group(1)
        table = find_table(q)
        if table:
            col = find_col(table, col_hint) or col_hint
            return f"SELECT MIN({col}) AS min_{col} FROM {table}"

    # TOP N [table] BY [col]
    m = re.search(r"\btop\s+(\d+)\b", q)
    if m:
        limit = int(m.group(1))
        table = find_table(q)
        if table:
            by_match = re.search(r"\bby\s+(\w+)", q)
            if by_match:
                col = find_col(table, by_match.group(1)) or by_match.group(1)
                order = "ASC" if re.search(r"\b(asc|ascending|lowest|cheapest|smallest)\b", q) else "DESC"
                return f"SELECT * FROM {table} ORDER BY {col} {order} LIMIT {limit}"
            return f"SELECT * FROM {table} LIMIT {limit}"

    # WHERE col = value
    m = re.search(r"\bwhere\s+(\w+)\s+(?:is|=|equals?)\s+['\"]?([^'\"]+?)['\"]?(?:\s|$)", q)
    if m:
        col_hint, value = m.group(1), m.group(2).strip()
        table = find_table(q)
        if table:
            col = find_col(table, col_hint) or col_hint
            val_sql = value if re.match(r"^\d+(\.\d+)?$", value) else f"'{value}'"
            return f"SELECT * FROM {table} WHERE {col} = {val_sql}"

    # ORDER BY
    m = re.search(r"\border(?:ed)?\s+by\s+(\w+)", q)
    if m:
        col_hint = m.group(1)
        table = find_table(q)
        if table:
            col = find_col(table, col_hint) or col_hint
            order = "ASC" if re.search(r"\b(asc|ascending|lowest)\b", q) else "DESC"
            return f"SELECT * FROM {table} ORDER BY {col} {order}"

    # SHOW ALL / LIST / GET / DISPLAY
    if re.search(r"\b(show|list|get|display|fetch|select|give)\b", q):
        table = find_table(q)
        if table:
            limit_match = re.search(r"\blimit\s+(\d+)\b", q)
            limit_clause = f" LIMIT {limit_match.group(1)}" if limit_match else ""
            return f"SELECT * FROM {table}{limit_clause}"

    return None


# ============================================================================
# Public API
# ============================================================================

def english_to_sql(question: str, schema: str, model: str = "gemini-2.5-flash") -> str:
    """Convert an English question into a safe SQL SELECT query.

    Tries Gemini first. If Gemini is unavailable (no key, quota exhausted,
    or any API error), falls back to the keyword rule engine.

    Raises SQLGenerationError if both methods fail.
    """
    if not question or not question.strip():
        raise SQLGenerationError("Please enter a question.")

    gemini_error = None

    # --- Try Gemini ---
    try:
        client = _client()
        response = client.models.generate_content(
            model=model, contents=_build_prompt(question, schema)
        )
        sql = _clean(getattr(response, "text", "") or "")
        if sql and is_safe(sql):
            return sql
        gemini_error = "The model did not return valid SQL."
    except SQLGenerationError as e:
        gemini_error = str(e)
    except errors.ClientError as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            gemini_error = "Gemini quota exhausted — using keyword fallback."
        else:
            gemini_error = f"Gemini API error: {e}"
    except Exception as e:
        gemini_error = f"Gemini unavailable: {e}"

    # --- Keyword fallback ---
    sql = _keyword_fallback(question, schema)
    if sql and is_safe(sql):
        return sql  # fallback succeeded silently

    # Both failed
    raise SQLGenerationError(
        f"{gemini_error} — Keyword fallback also couldn't match your query. "
        "Try rephrasing (e.g. 'show all orders', 'count customers', 'top 5 products by amount')."
    )
