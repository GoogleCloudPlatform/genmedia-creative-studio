#!/usr/bin/env python3
"""Deterministic analyzer for Mesop apps targeted for conversion to FastAPI + Lit + Vite + Material 3.

Part of the `mesop-to-lit` Claude Code skill (ASSESS half). Point it at a Mesop app
directory and it emits a structured inventory + a conversion assessment, in BOTH
machine JSON and human-readable markdown.

    python3 analyze_mesop_app.py <app_dir> [--json out.json] [--md out.md] [--include-nested]

Design constraints (see the skill's references/analysis-method.md):
  * Python 3 standard library ONLY (ast, re, pathlib, json, argparse) -- no pip installs.
  * Deterministic: same input dir -> same output (files sorted, counts stable).
  * Robust: never hard-fail on one unparseable file; collect errors and continue.
  * Prefer AST for structure (routes, components, stateclasses, imports, in-view LLM
    calls); fall back to regex line-counting for construct intensity (matching the
    Phase-0 inventory's grep-line-count methodology).

Detection rubric and the construct->component mapping are documented inline (see
RUBRIC_* and COMPONENT_DECISIONS) and mirrored in references/analysis-method.md,
references/construct-map.md and references/component-decisions.md.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Directories excluded from the walk by default. When pointed at a repo ROOT that
# vendors multiple apps (e.g. genmedia-creative-studio), `experiments/` and
# `archive/` are *separate* apps and are excluded so ROOT counts describe the ROOT
# app only -- matching the Phase-0 inventory's "ROOT excludes experiments/archive"
# methodology. Pass --include-nested to keep them.
DEFAULT_EXCLUDES = {
    ".git", "__pycache__", ".venv", "venv", "env", "node_modules",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "site-packages", ".tox", ".idea", ".vscode",
}
NESTED_APP_DIRS = {"experiments", "archive"}

# Construct presence/intensity patterns. Counts are *lines containing >=1 match*
# across all .py files (grep -c semantics), reproducing the Phase-0 construct-usage
# matrix. Presence (count > 0) is the load-bearing signal; exact counts are
# heuristic (comments/strings can inflate them) and labelled as such in output.
CONSTRUCT_PATTERNS = {
    "stateclass": r"@me\.stateclass",
    "page_registration": r"@me\.page|me\.page\(",
    "navigate": r"me\.navigate",
    "generator_yield": r"\byield\b",
    "native_textarea": r"native_textarea",
    "on_blur": r"on_blur",
    # The `*_textarea_key++` remount hack (Mesop two-way-binding workaround,
    # deleted on conversion -- see references/state-and-transport.md).
    "key_bump_remount": r"_textarea_key|_key\s*\+\+",
    "slot_or_content_component": r"me\.slot|content_component",
    "theme_var": r"theme_var",
    "set_theme_or_brightness": r"set_theme|theme_brightness",
    "security_policy": r"SecurityPolicy",
    "allowed_iframe_parents": r"allowed_iframe_parents",
    "select": r"me\.select",
    "slider": r"me\.slider",
    "tabs": r"tab_box|\.tab|Tab",
    "modal_or_dialog": r"modal|dialog",
    "expansion_panel": r"expansion_panel",
    "markdown": r"me\.markdown",
    "box": r"me\.box",
}

# Hard-topic patterns. `legacy_vertexai` deliberately excludes the `vertexai=True`
# kwarg (that is the *new* google.genai SDK pointed at the Vertex backend, not the
# legacy vertexai SDK).
HARD_TOPIC_PATTERNS = {
    "streaming": r"generate_content_stream|\w+_stream\s*\(|stream\s*=\s*True",
    "upload_native": r"me\.uploader",
    "upload_web_component": r"@me\.web_component",
    "upload_signed_url": r"signed_url|get_signed_url|signedUrl|signed-url",
    "upload_any_token": r"upload",
    "websocket": r"[wW]eb[sS]ocket",
    "auth_iap": r"\bIAP\b|verified_identity|verify_iap|x-goog-iap|goog-iap|iap_jwt|REQUIRE_AUTHENTICATED_USER",
    "firestore": r"firestore|firebase_admin|firebase-admin",
    "cloud_tasks": r"cloud_tasks|cloudtasks|CloudTasksClient|google-cloud-tasks|BackgroundTasks",
    "legacy_vertexai": r"from\s+vertexai|import\s+vertexai|vertexai\.generative_models|vertexai\.preview|GenerativeModel\(|ImageGenerationModel\(",
}

# Direct LLM-call signatures that, when found in a module that imports mesop,
# indicate business logic living in the view layer (a conversion red flag).
IN_VIEW_LLM_PATTERNS = {
    "LLMClient": r"LLMClient\(",
    "genai_client": r"genai\.Client\(",
    "generate_content": r"\.generate_content\b",
    "GenerativeModel": r"GenerativeModel\(",
    "ImageGenerationModel": r"ImageGenerationModel\(",
}

# Fields whose names strongly suggest a classification. Used by the field-level
# heuristic (UI-only / derived-display / secret-config). Documented in
# references/state-and-transport.md.
SECRET_CONFIG_HINTS = (
    "project_id", "project", "api_key", "apikey", "secret", "token", "credential",
    "model_id", "model", "location", "region", "bucket", "endpoint", "gcs",
)
DERIVED_DISPLAY_HINTS = (
    "response", "result", "output", "analysis", "summary", "generated",
    "improved", "parsed", "commentary", "duration", "report", "plan", "answer",
)
UI_ONLY_HINTS = (
    "open", "loading", "key", "theme", "mode", "current_page", "sidenav",
    "selected", "value", "input", "text", "show", "visible", "expanded",
    "temperature", "count", "index", "tab", "chip", "char", "status", "error",
)

# Construct -> component-decision mapping (from component-decision-framework.md).
# Only rows for constructs *present* in the app are emitted.
COMPONENT_DECISIONS = {
    "button":           ("stock", "md-*-button / md-icon-button -- 1:1 stable behaviour."),
    "native_textarea":  ("stock", "md-outlined-text-field type=textarea; native 2-way binding deletes on_blur+key++ hack."),
    "select":           ("stock", "md-outlined-select + md-select-option (stable)."),
    "slider":           ("stock", "md-slider (stable)."),
    "modal_or_dialog":  ("stock", "md-dialog (stable) -- slot content in."),
    "markdown":         ("not-a-component", "md-markdown helper (marked + DOMPurify); rendering concern, sanitize mandatory."),
    "expansion_panel":  ("custom", "MWC has NO accordion -> custom app-accordion over native <details>/<summary> + M3 tokens."),
    "tabs":             ("stock+custom", "md-tabs stock; tiny custom wrapper only if collapse behaviour required."),
    "slot_or_content_component": ("compose", "Lit <slot> projection; page_scaffold -> app-root shell + router outlet."),
    "theme_var":        ("not-a-component", "M3 CSS custom properties (--md-sys-color-*) + light/dark toggle."),
    "navigate":         ("compose", "client router (@vaadin/router 2.0.1 stable); index-keyed nav -> declarative route table."),
    "security_policy":  ("not-a-component", "FastAPI header middleware (CSP); drop dangerously_disable_trusted_types (Mesop workaround)."),
    "box":              ("not-a-component", "plain HTML + CSS (flex/grid) in the parent template."),
}

RUBRIC_NOTES = (
    "Per-page difficulty score = sum of signal weights in the page's module: "
    "+1 per distinct rich primitive present (select/slider/tabs/modal-dialog/chips/expansion_panel); "
    "+2 if an in-view LLM call (logic-in-view); +1 if generator yield; "
    "+1 state size >5 fields, +1 more >12; +1 layout density >=30 me.box lines, +1 more >=80; "
    "+3 if a custom upload web component / uploader is present; +1 per bespoke in-page component (cap 2). "
    "Bands: trivial <2, mechanical 2-4, needs-design 5-7, hard >7. "
    "Heuristic only -- flags where human judgement is needed."
)


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------

# F5 (read-only hardening): cap per-file reads so a pathological/hostile target
# (a crafted giant file) cannot exhaust memory/time. Source files are tiny;
# anything above this is not real app code.
MAX_READ_BYTES = 5 * 1024 * 1024  # 5 MB


def _has_symlink_parent(path: Path, root: Path) -> bool:
    """True if any directory between `root` (exclusive) and `path` is a symlink."""
    cur = path.parent
    while cur != root:
        if cur.is_symlink():
            return True
        if cur.parent == cur:  # reached the filesystem root without hitting `root`
            return False
        cur = cur.parent
    return False


def collect_py_files(root: Path, include_nested: bool) -> list[Path]:
    excludes = set(DEFAULT_EXCLUDES)
    if not include_nested:
        excludes |= NESTED_APP_DIRS
    out: list[Path] = []
    for p in sorted(root.rglob("*.py")):
        parts = set(p.relative_to(root).parts[:-1])
        if parts & excludes:
            continue
        # F5: skip symlinked files and anything reached through a symlinked dir
        # so a hostile tree cannot loop or escape the target the operator chose.
        if p.is_symlink() or _has_symlink_parent(p, root):
            continue
        out.append(p)
    return out


def read_text(p: Path) -> str:
    # F5: skip pathologically large files instead of reading them into memory.
    try:
        if p.stat().st_size > MAX_READ_BYTES:
            return ""
    except OSError:
        return ""
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        try:
            return p.read_text(encoding="latin-1")
        except OSError:
            return ""


# ---------------------------------------------------------------------------
# AST-based structural extraction
# ---------------------------------------------------------------------------

def _attr_chain(node: ast.AST) -> str:
    """Render a dotted attribute/name chain: me.page -> 'me.page'."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _const_str(node: ast.AST):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _call_path_kwarg(call: ast.Call) -> str | None:
    for kw in call.keywords:
        if kw.arg == "path":
            v = _const_str(kw.value)
            if v is not None:
                return v
    # positional path (first str arg)
    for a in call.args:
        v = _const_str(a)
        if v is not None and v.startswith("/"):
            return v
    return None


def _is_me_call(call: ast.Call, name: str) -> bool:
    """True if call looks like me.<name>(...) or <name>(...)."""
    f = call.func
    if isinstance(f, ast.Attribute) and f.attr == name:
        return True
    if isinstance(f, ast.Name) and f.id == name:
        return True
    return False


def _regex_extract(text: str):
    """Best-effort structural extraction when ast.parse fails.

    Keeps the analyzer robust when a target app uses newer Python syntax than the
    interpreter running this script (e.g. PEP 701 f-strings on an older runtime).
    Detection stays line-based and conservative.
    """
    out = {"pages": [], "stateclasses": [], "components": [],
           "func_defs": [], "imports_map": {}, "func_calls": {}}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.search(r"@me\.page\b", line):
            path = None
            for j in range(i, min(i + 10, len(lines))):
                m = re.search(r"""path\s*=\s*["']([^"']+)["']""", lines[j])
                if m:
                    path = m.group(1)
                    break
            cf = None
            for j in range(i, min(i + 12, len(lines))):
                m = re.match(r"\s*def\s+(\w+)", lines[j])
                if m:
                    cf = m.group(1)
                    break
            out["pages"].append({"path": path, "content_fn": cf,
                                 "kind": "decorator", "lineno": i + 1})
        if re.search(r"@me\.stateclass\b", line):
            name = None
            cls_line = None
            for j in range(i + 1, min(i + 4, len(lines))):
                m = re.match(r"\s*class\s+(\w+)", lines[j])
                if m:
                    name, cls_line = m.group(1), j
                    break
            if name is not None:
                indent = len(lines[cls_line]) - len(lines[cls_line].lstrip())
                fields = []
                for j in range(cls_line + 1, len(lines)):
                    l = lines[j]
                    if not l.strip():
                        continue
                    cur = len(l) - len(l.lstrip())
                    if cur <= indent:
                        break
                    if l.lstrip().startswith(("def ", "@", "#", '"', "'", "class ")):
                        continue
                    fm = re.match(r"\s*(\w+)\s*[:=]", l)
                    if fm:
                        fields.append({"name": fm.group(1),
                                       "classification": classify_field(fm.group(1))})
                out["stateclasses"].append({"name": name, "lineno": i + 1, "fields": fields})
        if re.search(r"@me\.(content_)?component\b", line):
            for j in range(i, min(i + 4, len(lines))):
                m = re.match(r"\s*def\s+(\w+)", lines[j])
                if m:
                    out["components"].append({"name": m.group(1),
                                              "kind": "component", "lineno": j + 1})
                    break
    out["func_defs"] = re.findall(r"^\s*def\s+(\w+)", text, re.M)
    for m in re.finditer(r"^\s*from\s+([\w.]+)\s+import\s+(.+)$", text, re.M):
        src = m.group(1).replace(".", "/") + ".py"
        for nm in re.split(r"[,\s]+", m.group(2)):
            nm = nm.strip().strip("()")
            if nm and nm != "import":
                out["imports_map"][nm.split(" as ")[-1]] = src
    return out


def analyze_module(path: Path, root: Path, text: str):
    """Return per-module facts. Never raises; parse errors recorded in 'error'."""
    rel = str(path.relative_to(root))
    info = {
        "module": rel,
        "imports_mesop": False,
        "pages": [],          # {path, content_fn, kind: decorator|imperative, lineno}
        "components": [],      # {name, kind, lineno}
        "stateclasses": [],    # {name, lineno, fields:[{name, classification}]}
        "in_view_llm": [],     # {signature, lineno}
        "func_defs": [],       # top-level + nested function names
        "imports_map": {},     # imported name -> source module path (best-effort)
        "func_calls": {},      # function name -> [called Name ids in its body]
        "error": None,
    }
    # mesop import (cheap textual check first, confirmed by AST below)
    try:
        tree = ast.parse(text, filename=rel)
    except (SyntaxError, ValueError) as exc:
        info["error"] = f"{type(exc).__name__}: {exc}"
        # regex fallback so detection survives newer-than-interpreter syntax
        info["imports_mesop"] = bool(re.search(r"^\s*(import mesop|from mesop)", text, re.M))
        ex = _regex_extract(text)
        info["pages"] = ex["pages"]
        info["stateclasses"] = ex["stateclasses"]
        info["components"] = ex["components"]
        info["func_defs"] = ex["func_defs"]
        info["imports_map"] = ex["imports_map"]
        if info["imports_mesop"]:
            for sig, pat in IN_VIEW_LLM_PATTERNS.items():
                for m in re.finditer(pat, text):
                    lineno = text.count("\n", 0, m.start()) + 1
                    info["in_view_llm"].append({"signature": sig, "lineno": lineno})
        return info

    for node in ast.walk(tree):
        # imports
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "mesop" or a.name.startswith("mesop."):
                    info["imports_mesop"] = True
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "mesop" or node.module.startswith("mesop")):
                info["imports_mesop"] = True
            if node.module and node.level == 0:
                src = node.module.replace(".", "/") + ".py"
                for a in node.names:
                    info["imports_map"][a.asname or a.name] = src

    # Walk function/class defs for decorators + imperative page() calls.
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info["func_defs"].append(node.name)
            called = []
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                    called.append(sub.func.id)
            info["func_calls"][node.name] = called
            for dec in node.decorator_list:
                dname = None
                page_path = None
                if isinstance(dec, ast.Call):
                    dname = _attr_chain(dec.func)
                    if _is_me_call(dec, "page"):
                        page_path = _call_path_kwarg(dec)
                        info["pages"].append({
                            "path": page_path, "content_fn": node.name,
                            "kind": "decorator", "lineno": dec.lineno,
                        })
                    if _is_me_call(dec, "component") or _is_me_call(dec, "content_component"):
                        info["components"].append({
                            "name": node.name, "kind": dname or "component",
                            "lineno": node.lineno,
                        })
                else:
                    dname = _attr_chain(dec)
                    if dname in ("me.page",):
                        info["pages"].append({
                            "path": None, "content_fn": node.name,
                            "kind": "decorator", "lineno": node.lineno,
                        })
                    if dname in ("me.component", "me.content_component"):
                        info["components"].append({
                            "name": node.name, "kind": dname.split(".")[-1],
                            "lineno": node.lineno,
                        })
        elif isinstance(node, ast.ClassDef):
            for dec in node.decorator_list:
                dname = _attr_chain(dec.func) if isinstance(dec, ast.Call) else _attr_chain(dec)
                if dname.endswith("stateclass"):
                    fields = []
                    for stmt in node.body:
                        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                            fname = stmt.target.id
                            fields.append({
                                "name": fname,
                                "classification": classify_field(fname),
                            })
                        elif isinstance(stmt, ast.Assign):
                            for t in stmt.targets:
                                if isinstance(t, ast.Name):
                                    fields.append({
                                        "name": t.id,
                                        "classification": classify_field(t.id),
                                    })
                    info["stateclasses"].append({
                        "name": node.name, "lineno": node.lineno, "fields": fields,
                    })

    # Imperative me.page(...) calls (not decorators) -- e.g. main.py test pages.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_me_call(node, "page"):
            # skip if this call is a decorator (already captured) -- decorators are
            # not Expr-wrapped Call children of the module in the same way; dedupe
            # by (path, lineno) later.
            p = _call_path_kwarg(node)
            # heuristic: imperative calls usually pass a component/path kwarg
            content_fn = None
            for kw in node.keywords:
                if kw.arg in ("component", "content", "page"):
                    if isinstance(kw.value, ast.Name):
                        content_fn = kw.value.id
                    elif isinstance(kw.value, ast.Attribute):
                        content_fn = kw.value.attr
            info["pages"].append({
                "path": p, "content_fn": content_fn,
                "kind": "imperative", "lineno": node.lineno,
            })

    # In-view LLM calls (only meaningful if the module is a view).
    if info["imports_mesop"]:
        for sig, pat in IN_VIEW_LLM_PATTERNS.items():
            for m in re.finditer(pat, text):
                lineno = text.count("\n", 0, m.start()) + 1
                info["in_view_llm"].append({"signature": sig, "lineno": lineno})

    return info


def classify_field(name: str) -> str:
    low = name.lower()
    for h in SECRET_CONFIG_HINTS:
        if h in low:
            return "secret-config"
    for h in DERIVED_DISPLAY_HINTS:
        if h in low:
            return "derived-display"
    for h in UI_ONLY_HINTS:
        if h in low:
            return "ui-only"
    return "ui-only"  # default: most Mesop state is transient UI state


# ---------------------------------------------------------------------------
# Regex line-count helpers
# ---------------------------------------------------------------------------

def count_lines_matching(pattern: str, texts: dict[str, str]) -> int:
    rx = re.compile(pattern)
    total = 0
    for t in texts.values():
        for line in t.splitlines():
            if rx.search(line):
                total += 1
    return total


def files_matching(pattern: str, texts: dict[str, str]) -> list[str]:
    rx = re.compile(pattern)
    out = []
    for name, t in texts.items():
        if rx.search(t):
            out.append(name)
    return sorted(out)


# ---------------------------------------------------------------------------
# Serve model + stack facts (non-.py files)
# ---------------------------------------------------------------------------

def detect_serve_model(root: Path, all_text_blob: str):
    result = {"model": "unknown", "evidence": [], "entrypoint": None}
    procfiles = sorted(root.rglob("Procfile"))
    proc_line = None
    for pf in procfiles:
        if set(pf.relative_to(root).parts[:-1]) & (DEFAULT_EXCLUDES | NESTED_APP_DIRS):
            continue
        txt = read_text(pf)
        for line in txt.splitlines():
            if "gunicorn" in line or "uvicorn" in line:
                proc_line = line.strip()
                result["evidence"].append(f"Procfile: {proc_line}")
                break
        if proc_line:
            break

    # entrypoint target like app:me / main:me / main:app
    target = None
    if proc_line:
        m = re.search(r"([A-Za-z_][\w./]*):([A-Za-z_]\w*)", proc_line)
        if m:
            target = f"{m.group(1)}:{m.group(2)}"
            result["entrypoint"] = target

    has_wsgi_mw = bool(re.search(r"WSGIMiddleware", all_text_blob))
    has_fastapi = bool(re.search(r"FastAPI\(|from fastapi", all_text_blob))
    has_create_wsgi = bool(re.search(r"create_wsgi_app", all_text_blob))
    if has_wsgi_mw:
        result["evidence"].append("code: WSGIMiddleware present")
    if has_fastapi:
        result["evidence"].append("code: FastAPI present")

    obj = target.split(":")[-1] if target else None
    if obj == "me":
        result["model"] = "plain-wsgi"
    elif obj == "app" and (has_wsgi_mw or has_fastapi):
        result["model"] = "fastapi-hybrid"
    elif has_wsgi_mw and has_fastapi:
        result["model"] = "fastapi-hybrid"
    elif obj == "me" or (has_create_wsgi and not has_fastapi):
        result["model"] = "plain-wsgi"
    elif has_fastapi:
        result["model"] = "fastapi-hybrid"
    return result


def parse_requirements(root: Path):
    pins = {}
    for req in sorted(root.rglob("requirements.txt")):
        if set(req.relative_to(root).parts[:-1]) & (DEFAULT_EXCLUDES | NESTED_APP_DIRS):
            continue
        for line in read_text(req).splitlines():
            line = line.strip()
            m = re.match(r"^([A-Za-z0-9_.\-]+)==([0-9][^\s;#]*)", line)
            if m:
                pins[m.group(1).lower()] = m.group(2)
        break
    return pins


def parse_uv_lock(root: Path):
    resolved = {}
    for lock in sorted(root.rglob("uv.lock")):
        if set(lock.relative_to(root).parts[:-1]) & (DEFAULT_EXCLUDES | NESTED_APP_DIRS):
            continue
        txt = read_text(lock)
        # blocks: [[package]]\nname = "x"\nversion = "y"
        for block in txt.split("[[package]]"):
            nm = re.search(r'name\s*=\s*"([^"]+)"', block)
            vm = re.search(r'version\s*=\s*"([^"]+)"', block)
            if nm and vm:
                resolved[nm.group(1).lower()] = vm.group(1)
        break
    return resolved


def parse_pyproject(root: Path):
    facts = {"requires_python": None, "dependencies": []}
    for pp in sorted(root.rglob("pyproject.toml")):
        if set(pp.relative_to(root).parts[:-1]) & (DEFAULT_EXCLUDES | NESTED_APP_DIRS):
            continue
        txt = read_text(pp)
        m = re.search(r'requires-python\s*=\s*"([^"]+)"', txt)
        if m:
            facts["requires_python"] = m.group(1)
        # dependencies = [ "a>=1", "b==2", ... ]
        dm = re.search(r"dependencies\s*=\s*\[(.*?)\]", txt, re.S)
        if dm:
            for q in re.findall(r'"([^"]+)"', dm.group(1)):
                facts["dependencies"].append(q)
        break
    return facts


def detect_python_version(root: Path):
    for pv in sorted(root.rglob(".python-version")):
        if set(pv.relative_to(root).parts[:-1]) & (DEFAULT_EXCLUDES | NESTED_APP_DIRS):
            continue
        v = read_text(pv).strip()
        if v:
            return v
    return None


def compute_drift(pins: dict, resolved: dict):
    drift = []
    for pkg in ("mesop", "google-genai"):
        rp = pins.get(pkg)
        lk = resolved.get(pkg)
        if rp and lk and rp != lk:
            drift.append({"package": pkg, "requirements_txt": rp, "uv_lock": lk})
    return drift


# ---------------------------------------------------------------------------
# Derived analysis: routes, nav, duplicates, difficulty, decisions
# ---------------------------------------------------------------------------

def collect_nav_route_refs(texts: dict[str, str], root: Path, include_nested: bool):
    """Route-path strings referenced (uncommented) by nav sources.

    Nav sources = .py files whose name contains 'nav' + navigation.json. Used to
    flag registered-but-hidden routes (a route with no nav reference).
    """
    refs = set()
    nav_py = {n: t for n, t in texts.items() if "nav" in Path(n).name.lower()}
    for t in nav_py.values():
        for line in t.splitlines():
            code = line.split("#", 1)[0]  # strip comments
            for m in re.finditer(r'["\'](/[A-Za-z0-9_\-/]*)["\']', code):
                refs.add(m.group(1))
    # navigation json files
    excludes = DEFAULT_EXCLUDES | (set() if include_nested else NESTED_APP_DIRS)
    for jf in sorted(root.rglob("*.json")):
        if set(jf.relative_to(root).parts[:-1]) & excludes:
            continue
        if "nav" not in jf.name.lower():
            continue
        for m in re.finditer(r'"(/[A-Za-z0-9_\-/]*)"', read_text(jf)):
            refs.add(m.group(1))
    return refs


def build_route_table(modules, nav_refs):
    raw = []
    seen = set()
    for mod in modules:
        for pg in mod["pages"]:
            key = (mod["module"], pg["lineno"], pg.get("path"))
            if key in seen:
                continue
            seen.add(key)
            raw.append({**pg, "module": mod["module"]})
    # group by path to find double-registration
    by_path = {}
    for r in raw:
        p = r.get("path")
        by_path.setdefault(p, []).append(r)
    routes = []
    for p, regs in sorted(by_path.items(), key=lambda kv: (kv[0] is None, kv[0] or "")):
        if p is None:
            # registrations we couldn't resolve a path for
            for r in regs:
                routes.append({
                    "path": None, "registrations": 1, "content_fns": [r.get("content_fn")],
                    "modules": [r["module"]], "double_registered": False,
                    "hidden_from_nav": False, "kind": r["kind"],
                    "unresolved_path": True,
                })
            continue
        hidden = bool(nav_refs) and p not in nav_refs and p != "/"
        routes.append({
            "path": p,
            "registrations": len(regs),
            "content_fns": [r.get("content_fn") for r in regs],
            "modules": sorted({r["module"] for r in regs}),
            "regs_detail": [{"module": r["module"], "content_fn": r.get("content_fn"),
                             "kind": r["kind"], "lineno": r["lineno"]} for r in regs],
            "double_registered": len(regs) > 1,
            "hidden_from_nav": hidden,
            "kind": sorted({r["kind"] for r in regs}),
        })
    return routes


def resolve_page_module(route, module_by_name):
    """Resolve a route to the real page-content module.

    Routes are often registered in a thin registrar (app.py/main.py) whose wrapper
    calls a `*_page_content` fn imported from pages/. Follow the import to the real
    module so difficulty scoring reads the page body, not the registrar.
    """
    candidates = []
    for reg in route.get("regs_detail", []):
        reg_mod = module_by_name.get(reg["module"])
        if reg_mod is None:
            continue
        # if the registrar is itself a page module (decorator on the content fn), use it
        if _path_has_dir(reg["module"], "pages") or Path(reg["module"]).name not in ("app.py", "main.py"):
            candidates.append(reg["module"])
        cf = reg.get("content_fn")
        if cf and cf in reg_mod["func_calls"]:
            for name in reg_mod["func_calls"][cf]:
                tgt = reg_mod["imports_map"].get(name)
                if tgt and tgt in module_by_name:
                    candidates.append(tgt)
        elif cf:
            tgt = reg_mod["imports_map"].get(cf)
            if tgt and tgt in module_by_name:
                candidates.append(tgt)
    # prefer a module under pages/ that is not the shared scaffold/header
    for c in candidates:
        if _path_has_dir(c, "pages"):
            return c
    for c in candidates:
        if Path(c).name not in ("page_scaffold.py", "header.py", "side_nav.py", "styles.py"):
            return c
    if candidates:
        return candidates[0]
    # fallback: first registering module
    return route["modules"][0] if route["modules"] else None


def find_duplicate_components(modules):
    """Function names defined in >=2 modules (copy-paste signal)."""
    name_to_modules = {}
    comp_names = set()
    for mod in modules:
        for c in mod["components"]:
            comp_names.add(c["name"])
        for fn in mod["func_defs"]:
            name_to_modules.setdefault(fn, set()).add(mod["module"])
    dups = []
    for name, mods in sorted(name_to_modules.items()):
        if len(mods) >= 2:
            dups.append({
                "name": name,
                "count": len(mods),
                "modules": sorted(mods),
                "is_mesop_component": name in comp_names,
            })
    # strongest signals first: mesop components, then raw recurrence
    dups.sort(key=lambda d: (not d["is_mesop_component"], -d["count"], d["name"]))
    return dups


def page_difficulty(module_info, texts):
    """Transparent scoring -- see RUBRIC_NOTES."""
    t = texts.get(module_info["module"], "")
    score = 0
    reasons = []
    for prim, pat in (
        ("select", r"me\.select"), ("slider", r"me\.slider"),
        ("tabs", r"tab_box|md-tab"), ("modal/dialog", r"modal|dialog"),
        ("chips", r"chip"), ("expansion_panel", r"expansion_panel"),
    ):
        if re.search(pat, t):
            score += 1
            reasons.append(f"+1 {prim}")
    if module_info["in_view_llm"]:
        score += 2
        reasons.append("+2 in-view LLM call")
    if re.search(r"\byield\b", t):
        score += 1
        reasons.append("+1 generator yield")
    nfields = sum(len(sc["fields"]) for sc in module_info["stateclasses"])
    fadd = (1 if nfields > 5 else 0) + (1 if nfields > 12 else 0)
    if fadd:
        score += fadd
        reasons.append(f"+{fadd} state size ({nfields} fields)")
    nbox = len(re.findall(r"me\.box", t))
    badd = (1 if nbox >= 30 else 0) + (1 if nbox >= 80 else 0)
    if badd:
        score += badd
        reasons.append(f"+{badd} me.box layout density ({nbox})")
    if re.search(r"me\.uploader|@me\.web_component", t):
        score += 3
        reasons.append("+3 upload component")
    ncomp = len(module_info["components"])
    cadd = min(ncomp, 2)
    if cadd:
        score += cadd
        reasons.append(f"+{cadd} bespoke in-page component(s) ({ncomp})")
    if score < 2:
        band = "trivial"
    elif score <= 4:
        band = "mechanical"
    elif score <= 7:
        band = "needs-design"
    else:
        band = "hard"
    return {"score": score, "band": band, "reasons": reasons}


# ---------------------------------------------------------------------------
# Top-level analysis
# ---------------------------------------------------------------------------

def analyze(app_dir: str, include_nested: bool):
    root = Path(app_dir).resolve()
    if not root.is_dir():
        raise SystemExit(f"error: not a directory: {app_dir}")

    py_files = collect_py_files(root, include_nested)
    texts = {}
    modules = []
    parse_errors = []
    for p in py_files:
        txt = read_text(p)
        rel = str(p.relative_to(root))
        texts[rel] = txt
        mi = analyze_module(p, root, txt)
        modules.append(mi)
        if mi["error"]:
            parse_errors.append({"module": rel, "error": mi["error"]})

    blob = "\n".join(texts.values())

    # construct counts
    construct_counts = {
        name: count_lines_matching(pat, texts)
        for name, pat in CONSTRUCT_PATTERNS.items()
    }

    # hard topics
    hard_topics = {}
    for name, pat in HARD_TOPIC_PATTERNS.items():
        lines = count_lines_matching(pat, texts)
        hard_topics[name] = {
            "present": lines > 0,
            "line_count": lines,
            "files": files_matching(pat, texts)[:25],
        }
    # Correct streaming/legacy semantics are presence-based; also surface the custom
    # gcs uploader by file presence.
    gcs_uploader_files = [n for n in texts if "gcs_uploader" in n or "uploader" in Path(n).name.lower()]
    hard_topics["custom_gcs_uploader_files"] = sorted(gcs_uploader_files)

    # seam analysis
    view_modules = [m["module"] for m in modules if m["imports_mesop"]]
    logic_modules = [m["module"] for m in modules if not m["imports_mesop"]]
    services_mesopfree = _dir_is_mesop_free(modules, "services")
    models_mesopfree = _dir_is_mesop_free(modules, "models")
    in_view_llm = []
    for m in modules:
        if m["in_view_llm"]:
            sigs = sorted({c["signature"] for c in m["in_view_llm"]})
            in_view_llm.append({
                "module": m["module"],
                "signatures": sigs,
                "sites": m["in_view_llm"],
            })
    # headline count: distinct view modules that instantiate LLMClient directly
    llmclient_view_modules = sorted({
        m["module"] for m in modules
        if m["imports_mesop"] and any(c["signature"] == "LLMClient" for c in m["in_view_llm"])
    })

    # routes + nav
    nav_refs = collect_nav_route_refs(texts, root, include_nested)
    routes = build_route_table(modules, nav_refs)
    distinct_paths = sorted({r["path"] for r in routes if r.get("path")})
    double_registered = [r for r in routes if r.get("double_registered")]
    hidden = [r for r in routes if r.get("hidden_from_nav")]

    # components
    shared_components = []
    for m in modules:
        for c in m["components"]:
            shared_components.append({**c, "module": m["module"]})
    duplicate_components = find_duplicate_components(modules)

    # stateclasses
    stateclasses = []
    for m in modules:
        for sc in m["stateclasses"]:
            scope = _state_scope(m["module"], sc["name"])
            stateclasses.append({**sc, "module": m["module"], "scope": scope})

    # serve + stack
    serve = detect_serve_model(root, blob)
    pins = parse_requirements(root)
    resolved = parse_uv_lock(root)
    pyproject = parse_pyproject(root)
    pyver = detect_python_version(root)
    drift = compute_drift(pins, resolved)

    # per-page difficulty
    page_assessments = []
    module_by_name = {m["module"]: m for m in modules}
    for r in routes:
        if not r.get("path"):
            continue
        mod_name = resolve_page_module(r, module_by_name)
        mi = module_by_name.get(mod_name)
        if mi is None:
            continue
        diff = page_difficulty(mi, texts)
        page_assessments.append({
            "path": r["path"],
            "module": mod_name,
            "content_fns": r["content_fns"],
            "difficulty": diff["band"],
            "score": diff["score"],
            "reasons": diff["reasons"],
            "double_registered": r["double_registered"],
            "hidden_from_nav": r["hidden_from_nav"],
        })

    # component decisions (only present constructs)
    decisions = []
    present = {k for k, v in construct_counts.items() if v > 0}
    # map a few compound keys
    for key, (call, rationale) in COMPONENT_DECISIONS.items():
        hit = key in present
        if not hit and key == "button":
            hit = bool(re.search(r"me\.button|me\.content_button", blob))
        if hit:
            decisions.append({"construct": key, "decision": call, "rationale": rationale})
    for d in duplicate_components:
        if d["is_mesop_component"]:
            decisions.append({
                "construct": f"duplicated component '{d['name']}' (x{d['count']})",
                "decision": "promote-shared",
                "rationale": "DRY gate: copy-pasted across modules -> promote to ONE shared Lit element at first reuse.",
            })

    result = {
        "app_dir": str(root),
        "include_nested": include_nested,
        "summary": {
            "py_files": len(py_files),
            "view_modules": len(view_modules),
            "logic_modules": len(logic_modules),
            "route_registrations": sum(r["registrations"] for r in routes),
            "distinct_routes": len(distinct_paths),
            "double_registered_routes": [r["path"] for r in double_registered],
            "hidden_routes": [r["path"] for r in hidden],
            "stateclasses": len(stateclasses),
            "shared_components": len(shared_components),
            "duplicated_component_names": [d["name"] for d in duplicate_components if d["is_mesop_component"]],
            "in_view_llm_modules": llmclient_view_modules,
            "in_view_llm_count": len(llmclient_view_modules),
            "services_mesop_free": services_mesopfree,
            "models_mesop_free": models_mesopfree,
            "serve_model": serve["model"],
            "streaming_present": hard_topics["streaming"]["present"],
            "upload_present": hard_topics["upload_native"]["present"] or hard_topics["upload_web_component"]["present"],
            "parse_errors": len(parse_errors),
        },
        "routes": routes,
        "nav_route_refs": sorted(nav_refs),
        "shared_components": shared_components,
        "duplicate_components": duplicate_components,
        "stateclasses": stateclasses,
        "seam": {
            "services_mesop_free": services_mesopfree,
            "models_mesop_free": models_mesopfree,
            "view_modules": sorted(view_modules),
            "logic_modules": sorted(logic_modules),
            "in_view_llm": in_view_llm,
            "in_view_llmclient_modules": llmclient_view_modules,
        },
        "construct_counts": construct_counts,
        "hard_topics": hard_topics,
        "serve_model": serve,
        "stack": {
            "python_version_file": pyver,
            "requires_python": pyproject["requires_python"],
            "dependencies": pyproject["dependencies"],
            "requirements_pins": pins,
            "uv_lock_resolved_subset": {k: resolved.get(k) for k in ("mesop", "google-genai", "fastapi", "pydantic") if k in resolved},
            "requirements_vs_lock_drift": drift,
        },
        "page_assessments": page_assessments,
        "component_decisions": decisions,
        "rubric": RUBRIC_NOTES,
        "parse_errors": parse_errors,
    }
    return result


def _dir_is_mesop_free(modules, dirname):
    mods = [m for m in modules if _path_has_dir(m["module"], dirname)]
    if not mods:
        return None  # dir absent
    return not any(m["imports_mesop"] for m in mods)


def _path_has_dir(module_path, dirname):
    return dirname in Path(module_path).parts[:-1]


def _state_scope(module_path, classname):
    name = Path(module_path).name.lower()
    low = classname.lower()
    if "appstate" in low.replace("_", "") or _path_has_dir(module_path, "state") and "app" in low:
        return "global"
    if _path_has_dir(module_path, "state"):
        return "global-or-feature"
    if _path_has_dir(module_path, "pages") or name.startswith("page"):
        return "per-page"
    return "other"


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def render_markdown(r: dict) -> str:
    s = r["summary"]
    L = []
    a = L.append
    a(f"# Mesop App Conversion Assessment\n")
    a(f"> Generated by `analyze_mesop_app.py` (mesop-to-lit skill, ASSESS half).")
    a(f"> Target stack: FastAPI + Lit + Vite + Material 3 (Material Web).\n")
    a(f"**App directory:** `{r['app_dir']}`  ")
    a(f"**Nested apps (experiments/archive) {'INCLUDED' if r['include_nested'] else 'excluded'}**\n")

    a("## Headline\n")
    a(f"- **Serve model:** `{s['serve_model']}`")
    a(f"- **Routes:** {s['distinct_routes']} distinct ({s['route_registrations']} registrations)")
    if s["double_registered_routes"]:
        a(f"  - **Double-registered:** {', '.join(x for x in s['double_registered_routes'] if x)}")
    if s["hidden_routes"]:
        a(f"  - **Routed but hidden from nav:** {', '.join(x for x in s['hidden_routes'] if x)}")
    a(f"- **State classes:** {s['stateclasses']}")
    a(f"- **Seam:** services mesop-free = `{s['services_mesop_free']}`, models mesop-free = `{s['models_mesop_free']}`")
    if s["duplicated_component_names"]:
        a(f"- **Duplicated components (copy-paste):** {', '.join(s['duplicated_component_names'])}")
    a(f"- **In-view LLM calls (logic-in-view red flag):** {s['in_view_llm_count']} module(s): {', '.join(s['in_view_llm_modules']) or 'none'}")
    a(f"- **Streaming present:** {s['streaming_present']}  |  **Upload present:** {s['upload_present']}")
    a(f"- **Python files analyzed:** {s['py_files']}  (parse errors: {s['parse_errors']})\n")

    a("## Routes\n")
    a("| Path | Regs | Content fn(s) | Module(s) | Flags |")
    a("|---|---|---|---|---|")
    for rt in r["routes"]:
        flags = []
        if rt.get("double_registered"):
            flags.append("DOUBLE")
        if rt.get("hidden_from_nav"):
            flags.append("HIDDEN")
        if rt.get("unresolved_path"):
            flags.append("path?")
        a(f"| `{rt.get('path')}` | {rt['registrations']} | "
          f"{', '.join(str(x) for x in rt['content_fns'] if x) or '?'} | "
          f"{', '.join(rt['modules'])} | {', '.join(flags)} |")
    a("")

    a("## Seam (UI <-> logic boundary)\n")
    a(f"- `services/` mesop-free: **{r['seam']['services_mesop_free']}**")
    a(f"- `models/` mesop-free: **{r['seam']['models_mesop_free']}**")
    a(f"- View modules (import mesop): {len(r['seam']['view_modules'])}")
    a(f"- Logic modules (no mesop): {len(r['seam']['logic_modules'])}")
    if r["seam"]["in_view_llm"]:
        a("\n**In-view LLM calls (lift into `services/` before porting):**")
        for iv in r["seam"]["in_view_llm"]:
            sites = ", ".join(f"{c['signature']}@{c['lineno']}" for c in iv["sites"])
            a(f"- `{iv['module']}`: {sites}")
    a("")

    a("## State classes\n")
    a("| Class | Module | Scope | Fields (classified) |")
    a("|---|---|---|---|")
    for sc in r["stateclasses"]:
        fc = {}
        for f in sc["fields"]:
            fc[f["classification"]] = fc.get(f["classification"], 0) + 1
        fsummary = ", ".join(f"{k}:{v}" for k, v in sorted(fc.items())) or "(none)"
        a(f"| `{sc['name']}` | {sc['module']} | {sc['scope']} | {fsummary} |")
    a("")

    a("## Duplicated components (DRY gate)\n")
    if r["duplicate_components"]:
        a("| Name | Copies | Mesop component? | Modules |")
        a("|---|---|---|---|")
        for d in r["duplicate_components"]:
            a(f"| `{d['name']}` | {d['count']} | {d['is_mesop_component']} | {', '.join(d['modules'])} |")
    else:
        a("_None detected._")
    a("")

    a("## Construct inventory (line-count heuristic; presence is the load-bearing signal)\n")
    a("| Construct | Lines | Present |")
    a("|---|---|---|")
    for k, v in r["construct_counts"].items():
        a(f"| {k} | {v} | {'YES' if v else 'no'} |")
    a("")

    a("## Hard topics\n")
    a("| Topic | Present | Lines | Example files |")
    a("|---|---|---|---|")
    for k, v in r["hard_topics"].items():
        if k == "custom_gcs_uploader_files":
            continue
        files = ", ".join(v["files"][:4])
        a(f"| {k} | {'YES' if v['present'] else 'no'} | {v['line_count']} | {files} |")
    if r["hard_topics"].get("custom_gcs_uploader_files"):
        a(f"\n**Custom uploader files:** {', '.join(r['hard_topics']['custom_gcs_uploader_files'])}")
    a("")

    a("## Serve model & stack\n")
    a(f"- **Serve model:** `{r['serve_model']['model']}` (entrypoint `{r['serve_model']['entrypoint']}`)")
    for e in r["serve_model"]["evidence"]:
        a(f"  - {e}")
    a(f"- **Python:** version-file `{r['stack']['python_version_file']}`, requires-python `{r['stack']['requires_python']}`")
    if r["stack"]["requirements_vs_lock_drift"]:
        a("- **requirements.txt vs uv.lock drift:**")
        for d in r["stack"]["requirements_vs_lock_drift"]:
            a(f"  - `{d['package']}`: requirements={d['requirements_txt']} vs uv.lock={d['uv_lock']}")
    else:
        a("- requirements/lock drift: none detected (or files absent)")
    a("")

    a("## Per-page difficulty\n")
    a(f"> Rubric: {r['rubric']}\n")
    a("| Path | Difficulty | Score | Signals |")
    a("|---|---|---|---|")
    for pa in r["page_assessments"]:
        a(f"| `{pa['path']}` | **{pa['difficulty']}** | {pa['score']} | {'; '.join(pa['reasons']) or '-'} |")
    a("")

    a("## Construct -> component decisions\n")
    a("| Construct | Decision | Rationale |")
    a("|---|---|---|")
    for d in r["component_decisions"]:
        a(f"| {d['construct']} | **{d['decision']}** | {d['rationale']} |")
    a("")

    if r["parse_errors"]:
        a("## Parse errors (non-fatal)\n")
        for pe in r["parse_errors"]:
            a(f"- `{pe['module']}`: {pe['error']}")
        a("")

    a("---")
    a("_Fixed facts encoded by this skill: `@material/web` 2.5.0 is in MAINTENANCE MODE "
      "(stable components only; build custom Lit for tooltip/accordion/nav-drawer; never labs). "
      "lit 3.3.3; router @vaadin/router 2.0.1. There is NO LLM token streaming in any surveyed app "
      "(do not add it). Two serve models exist: plain Mesop WSGI and FastAPI+Mesop hybrid._")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Analyze a Mesop app for Mesop->Lit/FastAPI conversion.")
    ap.add_argument("app_dir", help="Path to the Mesop app directory (or repo root).")
    ap.add_argument("--json", dest="json_out", help="Write machine JSON report to this path.")
    ap.add_argument("--md", dest="md_out", help="Write markdown assessment to this path.")
    ap.add_argument("--include-nested", action="store_true",
                    help="Include experiments/ and archive/ subdirs (default: excluded as separate apps).")
    args = ap.parse_args()

    result = analyze(args.app_dir, args.include_nested)
    md = render_markdown(result)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.md_out:
        Path(args.md_out).write_text(md, encoding="utf-8")
    if not args.json_out and not args.md_out:
        print(md)
    else:
        s = result["summary"]
        print(f"[analyze_mesop_app] {result['app_dir']}")
        print(f"  routes={s['distinct_routes']} (regs={s['route_registrations']}) "
              f"states={s['stateclasses']} serve={s['serve_model']} "
              f"streaming={s['streaming_present']} upload={s['upload_present']} "
              f"in_view_llm={s['in_view_llm_count']} parse_errors={s['parse_errors']}")
        if args.json_out:
            print(f"  JSON -> {args.json_out}")
        if args.md_out:
            print(f"  MD   -> {args.md_out}")


if __name__ == "__main__":
    main()
