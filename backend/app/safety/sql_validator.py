"""Static validation of SQL before it reaches PostgreSQL (sqlglot, Postgres dialect).

Every query — compiled from a plan or written by the LLM — passes through here.
A query is accepted only if ALL of these hold:

* exactly one statement, which is a SELECT (or UNION of SELECTs), with no comments;
* no data-changing or session-changing node anywhere (INSERT/UPDATE/DELETE/MERGE,
  DDL, COPY, GRANT, SET, SELECT INTO, FOR UPDATE ...), including inside CTEs;
* every table is a declared analytics source (no raw/app/pg_catalog/... schemas);
* every column exists in the semantic catalog for its table;
* no dangerous functions (pg_sleep, pg_read_file, dblink, lo_*, set_config ...);
  unknown functions must be on an explicit allowlist;
* joins between base tables follow a declared relationship; no cartesian joins
  (except between single-row aggregates);
* it reads at least one analytics table (no hand-typed numbers);
* the outer LIMIT is a literal <= MAX_ROWS — otherwise the query is wrapped.

The original SQL text is what gets executed (sqlglot regeneration would change the
parameter syntax); the parse tree is only used for checking.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError
from sqlglot.optimizer.scope import Scope, traverse_scope

from app.semantic.loader import SemanticModel

MAX_SQL_LENGTH = 10_000
MAX_JOINS = 8

#: Unknown-to-sqlglot functions that are safe to call.
ALLOWED_ANONYMOUS_FUNCTIONS = {
    "date_part",
    "age",
    "justify_days",
    "justify_interval",
    "width_bucket",
    "mode",
    "percentile_disc",
    "stddev",
    "stddev_pop",
    "stddev_samp",
    "var_pop",
    "var_samp",
    "corr",
    "covar_pop",
    "covar_samp",
    "regr_slope",
    "regr_intercept",
    "trunc",
    "make_date",
    "to_date",
    "to_number",
    "isodow",
    "split_part",
    "btrim",
    "initcap",
    "cume_dist",
    "percent_rank",
    "ntile",
    "bool_and",
    "bool_or",
    "every",
}

#: Function names that are never allowed (checked on every function node).
DENIED_FUNCTIONS = {
    "pg_sleep",
    "pg_sleep_for",
    "pg_sleep_until",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "pg_reload_conf",
    "pg_rotate_logfile",
    "dblink",
    "dblink_exec",
    "dblink_connect",
    "lo_import",
    "lo_export",
    "lo_get",
    "lo_put",
    "lo_open",
    "lo_create",
    "lo_unlink",
    "current_setting",
    "set_config",
    "query_to_xml",
    "query_to_xml_and_xmlschema",
    "table_to_xml",
    "xpath",
    "copy",
    "generate_series",
    "exploding_generate_series",
    "generate_date_array",
    "current_user",
    "session_user",
    "current_version",
    "version",
    "current_schema",
    "current_database",
    "inet_server_addr",
    "inet_client_addr",
    "txid_current",
    "read_csv",
    "read_parquet",
}
DENIED_PREFIXES = ("pg_", "lo_", "dblink", "txid_", "file_", "http_")

#: Statement / clause types that must never appear anywhere in the tree.
_FORBIDDEN_NODE_NAMES = (
    "Insert",
    "Update",
    "Delete",
    "Merge",
    "Create",
    "Drop",
    "Alter",
    "AlterTable",
    "TruncateTable",
    "Command",
    "Copy",
    "Grant",
    "Revoke",
    "Set",
    "SetItem",
    "Transaction",
    "Commit",
    "Rollback",
    "Use",
    "Pragma",
    "LoadData",
    "Analyze",
    "Kill",
    "Into",
    "Lock",
    "Refresh",
    "Cache",
    "Uncache",
    "Describe",
    "Show",
    "Summarize",
)
FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = tuple(
    getattr(exp, name) for name in _FORBIDDEN_NODE_NAMES if hasattr(exp, name)
)


@dataclass
class ValidationResult:
    """Outcome of validating one SQL string."""

    ok: bool
    sql: str  # the SQL to execute (original text, possibly wrapped to enforce LIMIT)
    errors: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    limit: int | None = None
    limit_enforced: bool = False

    @property
    def message(self) -> str:
        return "; ".join(self.errors)


class SQLValidator:
    """Validates SQL against the semantic layer's allowed tables, columns and joins."""

    def __init__(self, model: SemanticModel, max_rows: int) -> None:
        self.model = model
        self.max_rows = max_rows
        # "fact_orders" -> source name; tables are always in the analytics schema
        self.table_to_source = {
            src.table.split(".", 1)[1]: name for name, src in model.sources.items()
        }
        self.join_pairs = model.allowed_join_pairs()

    # ------------------------------------------------------------------ public

    def validate(self, sql: str, allow_parameters: bool = False) -> ValidationResult:
        """Validate ``sql``; ``allow_parameters`` permits :name binds (compiled SQL only)."""
        errors: list[str] = []
        original = (sql or "").strip()
        if not original:
            return ValidationResult(False, original, ["The query is empty."])
        if len(original) > MAX_SQL_LENGTH:
            return ValidationResult(False, original, ["The query is too long."])
        stripped = original.rstrip().rstrip(";").rstrip()

        try:
            tokens = sqlglot.tokenize(stripped, read="postgres")
        except (TokenError, ParseError) as exc:
            return ValidationResult(
                False, original, [f"The query could not be parsed: {exc}"[:300]]
            )
        if any(t.comments for t in tokens):
            errors.append("Comments are not allowed in queries.")
        if any(t.token_type == sqlglot.tokens.TokenType.SEMICOLON for t in tokens):
            errors.append("Only a single statement is allowed.")

        try:
            statements = [s for s in sqlglot.parse(stripped, read="postgres") if s is not None]
        except (ParseError, TokenError) as exc:
            return ValidationResult(
                False, original, [f"The query could not be parsed: {exc}"[:300]]
            )
        if len(statements) != 1:
            errors.append("Only a single statement is allowed.")
            return ValidationResult(False, original, list(dict.fromkeys(errors)))
        tree = statements[0]

        if not isinstance(tree, exp.Select | exp.Union | exp.Intersect | exp.Except):
            errors.append(f"Only SELECT queries are allowed (got {tree.key.upper()}).")
            return ValidationResult(False, original, errors)

        errors += self._check_forbidden_nodes(tree)
        errors += self._check_functions(tree)
        if not allow_parameters and any(
            isinstance(n, exp.Placeholder | exp.Parameter) for n in tree.walk()
        ):
            errors.append("Query parameters are not allowed here.")
        if any(isinstance(n, exp.With) and n.args.get("recursive") for n in tree.walk()):
            errors.append("Recursive queries are not allowed.")

        tables: list[str] = []
        try:
            scopes = traverse_scope(tree)
        except Exception as exc:  # noqa: BLE001 - sqlglot raises various errors here
            errors.append(f"The query structure could not be analysed: {exc}"[:300])
            scopes = []
        for scope in scopes:
            errors += self._check_scope(scope, tables)
        if not tables and not errors:
            errors.append("The query must read from the analytics tables.")
        join_count = sum(1 for _ in tree.find_all(exp.Join))
        if join_count > MAX_JOINS:
            errors.append(f"Too many joins ({join_count}); at most {MAX_JOINS} are allowed.")

        limit, limit_errors = self._outer_limit(tree)
        errors += limit_errors
        errors = list(dict.fromkeys(errors))
        if errors:
            return ValidationResult(False, original, errors, sorted(set(tables)))

        final_sql, enforced = stripped, False
        if limit is None or limit > self.max_rows:
            final_sql = f"SELECT *\nFROM (\n{stripped}\n) AS limited_result\nLIMIT {self.max_rows}"
            limit, enforced = self.max_rows, True
        return ValidationResult(True, final_sql, [], sorted(set(tables)), limit, enforced)

    # ----------------------------------------------------------------- checks

    def _check_forbidden_nodes(self, tree: exp.Expression) -> list[str]:
        errors = []
        for node in tree.walk():
            if isinstance(node, FORBIDDEN_NODES):
                errors.append(f"{node.key.upper()} is not allowed; only read-only SELECT queries.")
            if isinstance(node, exp.Select):
                if node.args.get("into"):
                    errors.append("SELECT INTO is not allowed.")
                if node.args.get("locks"):
                    errors.append("Row locking (FOR UPDATE/SHARE) is not allowed.")
        return errors

    def _check_functions(self, tree: exp.Expression) -> list[str]:
        errors = []
        for fn in tree.find_all(exp.Func):
            if isinstance(fn, exp.Anonymous):
                name = str(fn.name).lower()
                if name in DENIED_FUNCTIONS or name.startswith(DENIED_PREFIXES):
                    errors.append(f"Function {name}() is not allowed.")
                elif name not in ALLOWED_ANONYMOUS_FUNCTIONS:
                    errors.append(f"Function {name}() is not on the allowed list.")
            else:
                name = fn.sql_name().lower()
                if name in DENIED_FUNCTIONS or name.startswith(DENIED_PREFIXES):
                    errors.append(f"Function {name}() is not allowed.")
        return errors

    def _source_name(self, table: exp.Table) -> tuple[str | None, str | None]:
        """Map a table node to (source name, error)."""
        if table.args.get("catalog"):
            return None, f"Table {table.sql()} is not allowed (cross-database reference)."
        schema = (table.db or "").lower()
        name = (table.name or "").lower()
        if schema not in ("", "analytics"):
            return (
                None,
                f"Table {table.sql()} is not allowed: only the analytics schema can be queried.",
            )
        if name not in self.table_to_source:
            return None, f"Table {table.sql()} is not part of the semantic layer."
        return self.table_to_source[name], None

    @staticmethod
    def _outputs(scope: Scope) -> set[str] | None:
        """Column names a derived source exposes (None = SELECT *)."""
        expr = scope.expression
        if any(isinstance(s, exp.Star) for s in getattr(expr, "selects", [])):
            return None
        if isinstance(expr, exp.Union | exp.Intersect | exp.Except):
            left = expr.left
            names = set(getattr(left, "named_selects", []))
            return names or None
        return set(getattr(expr, "named_selects", []))

    @staticmethod
    def _single_row(source: object) -> bool:
        """True for a derived source that is a plain aggregate without GROUP BY."""
        if not isinstance(source, Scope):
            return False
        expr = source.expression
        if not isinstance(expr, exp.Select) or expr.args.get("group"):
            return False
        return any(s.find(exp.AggFunc) for s in expr.selects)

    def _check_scope(self, scope: Scope, tables: list[str]) -> list[str]:
        errors: list[str] = []
        base: dict[str, str] = {}  # alias -> source name
        derived: dict[str, Scope] = {}
        for alias, source in scope.sources.items():
            if isinstance(source, exp.Table):
                name, err = self._source_name(source)
                if err:
                    errors.append(err)
                    continue
                base[alias] = name  # type: ignore[assignment]
                tables.append(self.model.sources[name].table)  # type: ignore[index]
            elif isinstance(source, Scope):
                derived[alias] = source
        if errors:
            return errors

        select_aliases = {
            s.alias for s in getattr(scope.expression, "selects", []) if isinstance(s, exp.Alias)
        }
        for column in scope.columns:
            col, qualifier = column.name, column.table
            if not col or isinstance(column.this, exp.Star):
                continue
            if (
                isinstance(scope.expression, exp.Select)
                and column.find_ancestor(exp.Select) is not scope.expression
            ):
                continue  # belongs to a nested subquery, which is checked in its own scope
            if qualifier:
                if qualifier in base:
                    if col not in self.model.sources[base[qualifier]].columns:
                        errors.append(
                            f"Column {qualifier}.{col} does not exist in the semantic layer."
                        )
                elif qualifier in derived:
                    outputs = self._outputs(derived[qualifier])
                    if outputs is not None and col not in outputs:
                        errors.append(f"Column {qualifier}.{col} is not produced by '{qualifier}'.")
                elif not self._resolves_in_parent(scope, qualifier):
                    errors.append(f"Unknown table or alias '{qualifier}'.")
                continue
            in_base = any(col in self.model.sources[s].columns for s in base.values())
            in_derived = any((o := self._outputs(d)) is None or col in o for d in derived.values())
            if not (
                in_base
                or in_derived
                or col in select_aliases
                or self._resolves_in_parent(scope, None, col)
            ):
                errors.append(f"Column '{col}' does not exist in the semantic layer.")

        errors += self._check_joins(scope, base, derived)
        errors += self._check_fan_out(scope, base)
        return errors

    def _check_fan_out(self, scope: Scope, base: dict[str, str]) -> list[str]:
        """Block joins of facts at different grains that would multiply measures.

        Joining order items (or payments) to orders repeats each order row once per
        item; summing order-level columns over that join double counts them.
        """
        facts = {alias: src for alias, src in base.items() if src.startswith("fact_")}
        if len(set(facts.values())) < 2:
            return []
        if len(set(facts.values())) > 2:
            return [
                "Joining more than two fact tables would double count; "
                "aggregate each fact table separately."
            ]
        (a1, s1), (a2, s2) = list(facts.items())[:2]
        many_one = None
        for rel in self.model.relationships:
            (fs, _), (ts, _) = rel.endpoints()
            if {fs, ts} == {s1, s2}:
                many_one = (fs, ts)
        if many_one is None:
            return [
                f"{s1} and {s2} cannot be joined: they are at different grains "
                "and would double count."
            ]
        one_alias = a1 if s1 == many_one[1] else a2
        one_cols = set(self.model.sources[many_one[1]].columns)
        errors = []
        for agg in scope.expression.find_all(exp.AggFunc):
            if isinstance(agg, exp.Count) and isinstance(agg.this, exp.Distinct):
                continue
            for col in agg.find_all(exp.Column):
                owner = col.table or (
                    one_alias
                    if col.name in one_cols
                    and not any(
                        col.name in self.model.sources[s].columns
                        for a, s in base.items()
                        if a != one_alias
                    )
                    else ""
                )
                if owner == one_alias:
                    errors.append(
                        f"Aggregating {many_one[1]}.{col.name} after joining {many_one[0]} "
                        "would double count it; aggregate it on its own table first."
                    )
        return errors

    def _resolves_in_parent(
        self, scope: Scope, qualifier: str | None, col: str | None = None
    ) -> bool:
        parent = scope.parent
        while parent is not None:
            for alias, source in parent.sources.items():
                if qualifier is not None and alias == qualifier:
                    return True
                if qualifier is None and col and isinstance(source, exp.Table):
                    name = self.table_to_source.get((source.name or "").lower())
                    if name and col in self.model.sources[name].columns:
                        return True
            parent = parent.parent
        return False

    def _check_joins(
        self, scope: Scope, base: dict[str, str], derived: dict[str, Scope]
    ) -> list[str]:
        select = scope.expression
        if not isinstance(select, exp.Select):
            return []
        joins = select.args.get("joins") or []
        if not joins:
            return []
        errors: list[str] = []
        from_expr = select.args.get("from_") or select.args.get("from")
        left_aliases: list[str] = []
        if from_expr is not None and from_expr.this is not None:
            left_aliases.append(from_expr.this.alias_or_name)

        def source_of(alias: str) -> object:
            return base.get(alias) or derived.get(alias)

        for join in joins:
            right = join.this.alias_or_name
            on = join.args.get("on")
            using = join.args.get("using")
            kind = (join.args.get("kind") or "").upper()
            if kind == "CROSS" or (on is None and not using):
                sides = [source_of(a) for a in [*left_aliases, right]]
                if not all(self._single_row(s) for s in sides):
                    errors.append(f"Join with '{right}' has no join condition (cartesian product).")
                left_aliases.append(right)
                continue
            pairs: list[tuple[str, str, str, str]] = []  # (alias, col, alias, col)
            if using:
                for ident in using:
                    for left in left_aliases:
                        pairs.append((left, ident.name, right, ident.name))
            if on is not None:
                for eq in on.find_all(exp.EQ, exp.NullSafeEQ):
                    a, b = eq.this, eq.expression
                    if isinstance(a, exp.Column) and isinstance(b, exp.Column):
                        pairs.append(
                            (
                                self._qualify(a, base, derived),
                                a.name,
                                self._qualify(b, base, derived),
                                b.name,
                            )
                        )
            linking = [
                p
                for p in pairs
                if {p[0], p[2]} & {right} and ({p[0], p[2]} - {right}) & set(left_aliases)
            ]
            if not linking:
                errors.append(f"Join with '{right}' must use an equality on key columns.")
            elif right in base and all(p[0] in base and p[2] in base for p in linking):
                declared = any(
                    frozenset({(base[p[0]], p[1]), (base[p[2]], p[3])}) in self.join_pairs
                    for p in linking
                )
                if not declared:
                    errors.append(
                        f"Join between {base[linking[0][0]]} and {base[linking[0][2]]} on "
                        f"{linking[0][1]} = {linking[0][3]} is not a declared relationship."
                    )
            left_aliases.append(right)
        return errors

    def _qualify(self, column: exp.Column, base: dict[str, str], derived: dict[str, Scope]) -> str:
        if column.table:
            return column.table
        owners = [a for a, s in base.items() if column.name in self.model.sources[s].columns]
        owners += [
            a for a, d in derived.items() if (o := self._outputs(d)) is None or column.name in o
        ]
        return owners[0] if len(owners) == 1 else ""

    def _outer_limit(self, tree: exp.Expression) -> tuple[int | None, list[str]]:
        limit = tree.args.get("limit")
        if limit is None:
            return None, []
        value = limit.expression if isinstance(limit, exp.Limit) else limit
        if isinstance(value, exp.Literal) and not value.is_string:
            try:
                n = int(value.this)
            except ValueError:
                return None, ["LIMIT must be a whole number."]
            if n < 0:
                return None, ["LIMIT must not be negative."]
            return n, []
        return None, ["LIMIT must be a literal number."]
