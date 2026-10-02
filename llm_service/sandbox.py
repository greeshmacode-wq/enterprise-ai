"""Restricted evaluator for LLM-generated pandas expressions."""

import ast
import builtins
import concurrent.futures
import logging

import pandas as pd

logger = logging.getLogger(__name__)

EVAL_TIMEOUT_SECONDS = 5 #Allow the generated Pandas expression to run for a maximum of 5 seconds.
MAX_RESULT_CHARS = 4000 # This controls how much result text is returned to the LLM.

_ALLOWED_NODE_TYPES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Call, ast.Attribute, ast.Subscript, ast.Slice,
    ast.Name, ast.Load, ast.Constant,
    ast.List, ast.Tuple, ast.Dict, ast.Set,
    ast.comprehension, ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
    ast.Starred, ast.keyword,
)
_FORBIDDEN_NAMES = frozenset({
    "exec", "eval", "compile", "open", "__import__", "globals", "locals",
    "vars", "getattr", "setattr", "delattr", "input", "breakpoint", "help",
})
_SAFE_BUILTIN_NAMES = (
    "len", "min", "max", "sum", "abs", "round", "sorted", "range",
    "list", "dict", "set", "tuple", "str", "int", "float", "bool", "enumerate", "zip",
)
_SAFE_BUILTINS = {name: getattr(builtins, name) for name in _SAFE_BUILTIN_NAMES}


class SandboxViolation(Exception):
    """Raised when generated code falls outside the allowed expression subset."""


class _SafePandasNamespace:
    """Whitelisted subset of the `pd` module - deliberately excludes any I/O
    (read_csv, read_pickle, HDFStore, ...) so generated code can't reach
    outside the dataframe it's already been given.
    """

    to_datetime = staticmethod(pd.to_datetime)
    to_numeric = staticmethod(pd.to_numeric)
    isna = staticmethod(pd.isna)
    notna = staticmethod(pd.notna)
    Timestamp = pd.Timestamp
    NaT = pd.NaT


def _validate(node: ast.AST) -> None:
    if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
        raise SandboxViolation(f"attribute '{node.attr}' is not allowed")
    if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
        raise SandboxViolation(f"name '{node.id}' is not allowed")
    if not isinstance(node, _ALLOWED_NODE_TYPES):
        raise SandboxViolation(f"'{type(node).__name__}' syntax is not allowed")
    for child in ast.iter_child_nodes(node):
        _validate(child)


def run_expression(code: str, dataframe: pd.DataFrame):
    """Evaluate a single pandas expression against `dataframe`.

    Raises SandboxViolation for disallowed syntax, SyntaxError for
    unparsable input, TimeoutError if evaluation runs too long.
    """
    logger.info("run_expression code=%r", code)
    try:
        tree = ast.parse(code, mode="eval")
    except SyntaxError as exc:
        raise SandboxViolation(
            "only a single Python expression is allowed - no assignments, "
            "imports, loops, or statements"
        ) from exc
    _validate(tree)

    compiled = compile(tree, filename="<pandas_tool>", mode="eval") #This turns the checked tree into something Python can run. "<pandas_tool>" is just a label that shows up in error messages.
    namespace = {"df": dataframe, "pd": _SafePandasNamespace()} #The code can use only two names: df (your CSV data) and pd (the limited, safe pandas).

    def _evaluate():
        # AST-validated above + restricted builtins/namespace: this is the
        # narrow, intentional use of eval the whole module exists to gate.
        return eval(compiled, {"__builtins__": _SAFE_BUILTINS}, namespace)

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        return executor.submit(_evaluate).result(timeout=EVAL_TIMEOUT_SECONDS)
    except concurrent.futures.TimeoutError as exc:
        raise TimeoutError(f"evaluation exceeded {EVAL_TIMEOUT_SECONDS}s") from exc
    finally:
        executor.shutdown(wait=False)


def format_result(result) -> str:
    text = result.to_string() if isinstance(result, (pd.DataFrame, pd.Series)) else str(result)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + f"\n... (truncated at {MAX_RESULT_CHARS} chars)"
    return text