from pathlib import Path
import ast
import json
import shutil
import uuid
import zipfile

from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"

MAX_UPLOAD_SIZE = 10 * 1024 * 1024
MAX_EXTRACTED_SIZE = 50 * 1024 * 1024
MAX_FILES = 1500

UPLOAD_DIR.mkdir(exist_ok=True)

PROJECTS = {}


def safe_zip_path(name):
    path = Path(name)
    return not path.is_absolute() and ".." not in path.parts


def extract_zip(zip_path, output_dir):
    with zipfile.ZipFile(zip_path) as archive:
        files = [
            item
            for item in archive.infolist()
            if not item.is_dir()
        ]

        if len(files) > MAX_FILES:
            raise ValueError("The project contains too many files.")

        total_size = 0

        for item in files:
            if not safe_zip_path(item.filename):
                raise ValueError("Unsafe path found in ZIP file.")

            total_size += item.file_size

            if total_size > MAX_EXTRACTED_SIZE:
                raise ValueError("The extracted project is too large.")

        output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        for item in files:
            target = output_dir / item.filename

            target.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            with (
                archive.open(item) as source,
                target.open("wb") as destination
            ):
                shutil.copyfileobj(
                    source,
                    destination
                )


def get_module_name(root, file_path):
    relative = file_path.relative_to(root).with_suffix("")
    parts = list(relative.parts)

    if parts and parts[-1] == "__init__":
        parts.pop()

    return ".".join(parts)


def parse_python_file(root, file_path):
    source = file_path.read_text(
        encoding="utf-8",
        errors="replace"
    )

    relative_path = file_path.relative_to(root).as_posix()
    module = get_module_name(root, file_path)

    result = {
        "path": relative_path,
        "module": module,
        "source": source,
        "lines": max(1, len(source.splitlines())),
        "functions": [],
        "classes": [],
        "imports": [],
        "todo_count": 0,
        "parse_error": None
    }

    result["todo_count"] = sum(
        line.upper().count("TODO")
        + line.upper().count("FIXME")
        for line in source.splitlines()
    )

    try:
        tree = ast.parse(
            source,
            filename=relative_path
        )
    except SyntaxError as exc:
        result["parse_error"] = (
            f"Line {exc.lineno}: {exc.msg}"
        )
        return result

    for node in ast.walk(tree):

        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef
            )
        ):
            result["functions"].append(node.name)

        elif isinstance(node, ast.ClassDef):
            result["classes"].append(node.name)

        elif isinstance(node, ast.Import):
            for alias in node.names:
                result["imports"].append({
                    "module": alias.name,
                    "type": "import"
                })

        elif isinstance(node, ast.ImportFrom):
            result["imports"].append({
                "module": node.module or "",
                "type": "from",
                "level": node.level,
                "names": [
                    alias.name
                    for alias in node.names
                ]
            })

    result["functions"] = sorted(
        set(result["functions"])
    )

    result["classes"] = sorted(
        set(result["classes"])
    )

    return result


def resolve_relative_import(
    current_module,
    level,
    imported
):
    parts = (
        current_module.split(".")
        if current_module
        else []
    )

    package = parts[:-1]

    if level:
        package = package[
            :max(
                0,
                len(package) - level + 1
            )
        ]

    prefix = ".".join(package)

    return ".".join(
        part
        for part in (
            prefix,
            imported
        )
        if part
    )


def resolve_dependencies(files):
    module_map = {
        item["module"]: item["path"]
        for item in files
        if item["module"]
    }

    local_edges = {}
    external = {}

    for file in files:

        if file["parse_error"]:
            continue

        for imported in file["imports"]:

            candidates = []

            if imported["type"] == "import":

                parts = imported["module"].split(".")

                for i in range(
                    len(parts),
                    0,
                    -1
                ):
                    candidates.append(
                        ".".join(parts[:i])
                    )

            else:

                base = resolve_relative_import(
                    file["module"],
                    imported.get("level", 0),
                    imported["module"]
                )

                if base:
                    candidates.append(base)

                    for name in imported.get(
                        "names",
                        []
                    ):
                        candidates.append(
                            f"{base}.{name}"
                        )
                else:
                    candidates.extend(
                        imported.get(
                            "names",
                            []
                        )
                    )

            target_module = next(
                (
                    candidate
                    for candidate in candidates
                    if candidate in module_map
                ),
                None
            )

            if (
                target_module
                and module_map[target_module]
                != file["path"]
            ):

                key = (
                    file["path"],
                    module_map[target_module]
                )

                local_edges[key] = {
                    "source": file["path"],
                    "target": module_map[target_module],
                    "type": "local"
                }

            else:

                external_key = (
                    file["path"],
                    imported["module"]
                )

                external[external_key] = {
                    "source": file["path"],
                    "target": imported["module"],
                    "type": "external"
                }

    return (
        list(local_edges.values()),
        list(external.values())
    )


def find_cycles(edges):
    graph = {}

    for edge in edges:
        graph.setdefault(
            edge["source"],
            []
        ).append(
            edge["target"]
        )

    state = {}
    stack = []
    seen = set()
    cycles = []

    def canonical(cycle):
        body = cycle[:-1]

        variants = []

        for i in range(len(body)):
            variants.append(
                tuple(
                    body[i:] + body[:i]
                )
            )

        reversed_body = list(
            reversed(body)
        )

        for i in range(
            len(reversed_body)
        ):
            variants.append(
                tuple(
                    reversed_body[i:]
                    + reversed_body[:i]
                )
            )

        return min(variants)

    def visit(node):
        state[node] = 1
        stack.append(node)

        for neighbor in graph.get(
            node,
            []
        ):

            if state.get(neighbor) == 1:

                start = stack.index(neighbor)

                cycle = (
                    stack[start:]
                    + [neighbor]
                )

                key = canonical(cycle)

                if key not in seen:
                    seen.add(key)
                    cycles.append(cycle)

            elif state.get(neighbor) != 2:
                visit(neighbor)

        stack.pop()
        state[node] = 2

    nodes = set(graph)

    for targets in graph.values():
        nodes.update(targets)

    for node in nodes:
        if state.get(node) is None:
            visit(node)

    return cycles


def analyze_project(root):
    python_files = sorted(
        path
        for path in root.rglob("*.py")
        if path.is_file()
    )

    if not python_files:
        raise ValueError(
            "No Python files were found."
        )

    parsed = [
        parse_python_file(
            root,
            path
        )
        for path in python_files
    ]

    edges, external = resolve_dependencies(
        parsed
    )

    cycles = find_cycles(edges)

    incoming = {}
    outgoing = {}

    for edge in edges:
        outgoing[edge["source"]] = (
            outgoing.get(
                edge["source"],
                0
            ) + 1
        )

        incoming[edge["target"]] = (
            incoming.get(
                edge["target"],
                0
            ) + 1
        )

    files = []

    for file in parsed:

        files.append({
            "path": file["path"],
            "module": file["module"],
            "lines": file["lines"],
            "functions": len(file["functions"]),
            "classes": len(file["classes"]),
            "imports": len(file["imports"]),
            "todo_count": file["todo_count"],
            "dependency_count": outgoing.get(
                file["path"],
                0
            ),
            "dependent_count": incoming.get(
                file["path"],
                0
            ),
            "parse_error": file["parse_error"]
        })

    hotspots = sorted(
        files,
        key=lambda item: (
            item["dependent_count"] * 4
            + item["dependency_count"] * 2
            + item["todo_count"]
            + item["lines"] // 100
        ),
        reverse=True
    )[:7]

    parse_errors = [
        file
        for file in files
        if file["parse_error"]
    ]

    todo_total = sum(
        file["todo_count"]
        for file in files
    )

    insights = []

    for file in hotspots[:4]:

        score = (
            file["dependent_count"] * 4
            + file["dependency_count"] * 2
            + file["todo_count"]
            + file["lines"] // 100
        )

        if score >= 8:
            insights.append(
                f"Review {file['path']}: "
                f"its structural score is {score}."
            )

    large_files = sorted(
        files,
        key=lambda item: item["lines"],
        reverse=True
    )[:5]

    for file in large_files:

        if file["lines"] >= 400:
            insights.append(
                f"{file['path']} contains "
                f"{file['lines']} lines."
            )

    if todo_total:
        insights.append(
            f"{todo_total} TODO/FIXME marker(s) found."
        )

    if cycles:
        insights.append(
            f"{len(cycles)} circular dependency "
            f"cycle(s) detected."
        )

    if parse_errors:
        insights.append(
            f"{len(parse_errors)} file(s) have "
            f"syntax errors."
        )

    if not insights:
        insights.append(
            "No major structural warning was found."
        )

    score = 100

    score -= min(
        35,
        len(cycles) * 15
    )

    score -= min(
        25,
        len(parse_errors) * 8
    )

    score -= min(
        15,
        todo_total
    )

    score = max(
        0,
        score
    )

    return {
        "files": files,
        "edges": edges,
        "external": external,
        "cycles": cycles,
        "hotspots": hotspots,
        "insights": insights,

        "metrics": {
            "files": len(files),

            "lines": sum(
                file["lines"]
                for file in files
            ),

            "functions": sum(
                file["functions"]
                for file in files
            ),

            "classes": sum(
                file["classes"]
                for file in files
            ),

            "dependencies": len(edges),

            "external_imports":
                len(external),

            "cycles":
                len(cycles),

            "todos":
                todo_total,

            "architecture_score":
                score
        },

        "details": {
            file["path"]: file
            for file in parsed
        }
    }


@app.get("/")
def home():
    return render_template(
        "index.html"
    )


@app.post("/api/analyze")
def analyze():

    uploaded = request.files.get(
        "file"
    )

    if (
        not uploaded
        or not uploaded.filename
    ):
        return jsonify({
            "error":
                "Choose a ZIP file."
        }), 400

    filename = secure_filename(
        uploaded.filename
    )

    if not filename.lower().endswith(
        ".zip"
    ):
        return jsonify({
            "error":
                "Only ZIP files are supported."
        }), 400

    project_id = uuid.uuid4().hex

    zip_path = (
        UPLOAD_DIR
        / f"{project_id}.zip"
    )

    workdir = (
        UPLOAD_DIR
        / project_id
    )

    try:

        uploaded.save(zip_path)

        if zip_path.stat().st_size > MAX_UPLOAD_SIZE:
            raise ValueError(
                "The uploaded file is too large."
            )

        if not zipfile.is_zipfile(
            zip_path
        ):
            raise ValueError(
                "Invalid ZIP file."
            )

        extract_zip(
            zip_path,
            workdir
        )

        result = analyze_project(
            workdir
        )

        result["project_name"] = (
            filename[:-4]
        )

        PROJECTS[project_id] = result

        return jsonify({
            "project_id":
                project_id,

            "project_name":
                result["project_name"]
        })

    except ValueError as exc:

        return jsonify({
            "error":
                str(exc)
        }), 400

    except Exception as exc:

        return jsonify({
            "error":
                f"Analysis failed: {exc}"
        }), 500

    finally:

        zip_path.unlink(
            missing_ok=True
        )

        shutil.rmtree(
            workdir,
            ignore_errors=True
        )


@app.get(
    "/api/project/<project_id>"
)
def get_project(project_id):

    project = PROJECTS.get(
        project_id
    )

    if not project:
        return jsonify({
            "error":
                "Project not found."
        }), 404

    return jsonify({
        "project_name":
            project["project_name"],

        "files":
            project["files"],

        "edges":
            project["edges"],

        "external":
            project["external"],

        "cycles":
            project["cycles"],

        "hotspots":
            project["hotspots"],

        "insights":
            project["insights"],

        "metrics":
            project["metrics"]
    })


@app.get(
    "/api/project/<project_id>/file"
)
def get_file(project_id):

    project = PROJECTS.get(
        project_id
    )

    path = request.args.get(
        "path",
        ""
    )

    if not project:
        return jsonify({
            "error":
                "Project not found."
        }), 404

    file = project["details"].get(
        path
    )

    if not file:
        return jsonify({
            "error":
                "File not found."
        }), 404

    dependencies = [
        edge["target"]
        for edge in project["edges"]
        if edge["source"] == path
    ]

    dependents = [
        edge["source"]
        for edge in project["edges"]
        if edge["target"] == path
    ]

    return jsonify({
        "path":
            path,

        "module":
            file["module"],

        "lines":
            file["lines"],

        "functions":
            file["functions"],

        "classes":
            file["classes"],

        "imports":
            file["imports"],

        "dependencies":
            dependencies,

        "dependents":
            dependents,

        "todo_count":
            file["todo_count"],

        "source":
            file["source"],

        "parse_error":
            file["parse_error"]
    })


@app.get(
    "/api/project/<project_id>/export"
)
def export_project(project_id):

    project = PROJECTS.get(
        project_id
    )

    if not project:
        return jsonify({
            "error":
                "Project not found."
        }), 404

    data = {
        "project_name":
            project["project_name"],

        "metrics":
            project["metrics"],

        "files":
            project["files"],

        "edges":
            project["edges"],

        "external":
            project["external"],

        "cycles":
            project["cycles"],

        "hotspots":
            project["hotspots"],

        "insights":
            project["insights"]
    }

    response = app.response_class(
        response=json.dumps(
            data,
            indent=2
        ),
        mimetype="application/json"
    )

    response.headers["Content-Disposition"] = (
        f'attachment; '
        f'filename="{project["project_name"]}-analysis.json"'
    )

    return response


if __name__ == "__main__":
    app.run(debug=True)