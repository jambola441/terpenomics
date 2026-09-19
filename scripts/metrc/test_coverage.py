"""Checks the step sequences line up with the workbook they have to fill.

A step labelled 'Step 7' on a tab that stops at Step 6, or a tab name that
does not match a sheet exactly, silently produces a blank cell. This catches
both without needing API credentials.
"""
from __future__ import annotations

import ast
import os
import unittest

from .workbook import map_workbook

HERE = os.path.dirname(__file__)
STEPS_PY = os.path.join(HERE, "steps.py")
WORKBOOK = os.path.join(
    HERE, "..", "..", "evidence", "metrc",
    "Generic_Evaluation_for_All_States_MASTER_10.2025.xlsx",
)

# Sheets used for working evidence rather than workbook answers.
SCRATCH_SHEETS = {"_bootstrap", "_reference", "_readonly"}

# NY is open loop and has no retailer deliveries, so these are out of scope.
NY_EXCLUDED = {
    "Closed Loop States PlantBatches",
    "CA ONLY Labs",
    "CA- SalesRetailDeliveries",
    "Sales",
}


def declared_calls() -> set:
    """Every (sheet, step) pair the step functions declare, read statically.

    Most steps pass sheet as a local variable rather than a literal, so each
    function's `sheet = "..."` binding is resolved first. Functions that take
    sheet as a parameter are resolved from their default.
    """
    with open(STEPS_PY, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    found = set()

    # Module-level string constants, so a sheet named by constant resolves too.
    consts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value.value, str):
                    consts[target.id] = node.value.value

    def literal(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return consts.get(node.id)
        return None

    # A step label handed to a local helper ("search(path, 'Step 1', True)")
    # is a variable at the client.get call site, so collect the literals each
    # function is actually called with and treat those as its step labels.
    step_re = __import__("re").compile(r"^Step\s*\d+[a-z]?$", __import__("re").I)
    via_callsite = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        labels = {
            a.value for a in list(node.args) + [k.value for k in node.keywords]
            if isinstance(a, ast.Constant)
            and isinstance(a.value, str)
            and step_re.match(a.value)
        }
        if labels:
            via_callsite.setdefault(node.func.id, set()).update(labels)

    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        local_sheet = None

        for default, arg in zip(
            reversed(fn.args.defaults or []), reversed(fn.args.args or [])
        ):
            if arg.arg == "sheet" and literal(default) is not None:
                local_sheet = literal(default)
        for kwarg, default in zip(fn.args.kwonlyargs, fn.args.kw_defaults):
            if kwarg.arg == "sheet" and default is not None and literal(default) is not None:
                local_sheet = literal(default)

        for node in ast.walk(fn):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id == "sheet"
                        and literal(node.value) is not None
                    ):
                        local_sheet = literal(node.value)

            if not isinstance(node, ast.Call):
                continue
            step = sheet = None
            for kw in node.keywords:
                if kw.arg == "step" and isinstance(kw.value, ast.Constant):
                    step = kw.value.value
                elif kw.arg == "sheet":
                    if isinstance(kw.value, ast.Name) and kw.value.id == "sheet":
                        sheet = local_sheet
                    else:
                        sheet = literal(kw.value)
            if step and sheet:
                found.add((sheet, step))
            elif sheet and not step:
                # step came in as a parameter — use the labels this helper is
                # called with.
                for enclosing, labels in via_callsite.items():
                    if any(
                        isinstance(inner, ast.FunctionDef) and inner.name == enclosing
                        for inner in ast.walk(fn)
                    ):
                        for label in labels:
                            found.add((sheet, label))

    return found


class TestCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sheets = map_workbook(WORKBOOK)
        cls.calls = declared_calls()

    def test_every_declared_step_exists_in_the_workbook(self):
        for sheet, step in sorted(self.calls):
            if sheet in SCRATCH_SHEETS or not step.startswith("Step"):
                continue
            with self.subTest(sheet=sheet, step=step):
                self.assertIn(sheet, self.sheets, f"no such sheet: {sheet!r}")
                self.assertIn(
                    step, self.sheets[sheet].steps,
                    f"{sheet!r} has no {step!r} (it has "
                    f"{sorted(self.sheets[sheet].steps)})",
                )

    def test_every_in_scope_sheet_step_is_covered(self):
        covered = {(s, t) for s, t in self.calls}
        for name, sheet_map in self.sheets.items():
            if name in NY_EXCLUDED:
                continue
            for step in sheet_map.steps:
                with self.subTest(sheet=name, step=step):
                    self.assertIn(
                        (name, step), covered,
                        f"{name!r} {step!r} is never driven by any step function",
                    )

    def test_answer_columns_never_land_in_column_a(self):
        for name, sheet_map in self.sheets.items():
            with self.subTest(sheet=name):
                self.assertNotIn(
                    "A", sheet_map.columns.values(),
                    f"{name!r} maps an answer column onto column A (task text)",
                )

    def test_every_in_scope_sheet_has_an_evidence_column(self):
        for name, sheet_map in self.sheets.items():
            if name in NY_EXCLUDED:
                continue
            with self.subTest(sheet=name):
                self.assertIn("evidence", sheet_map.columns)
                self.assertIn("status", sheet_map.columns)


if __name__ == "__main__":
    unittest.main()
