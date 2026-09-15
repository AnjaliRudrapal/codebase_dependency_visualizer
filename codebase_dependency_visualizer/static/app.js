let projectId = null;
let project = null;
let graph = null;
let selectedPath = "";

const $ = id =>
    document.getElementById(id);


function escapeHtml(value) {

    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function showError(message = "") {

    $("error").textContent = message;
    $("landingStatus").textContent = "";
}


function showStatus(message = "") {

    $("landingStatus").textContent = message;
    $("error").textContent = "";
}


async function uploadProject(file) {

    if (!file) {
        return;
    }

    if (!file.name.toLowerCase().endsWith(".zip")) {

        showStatus(
            "Please select a ZIP file."
        );

        return;
    }

    showStatus(
        "Analyzing project..."
    );

    const formData =
        new FormData();

    formData.append(
        "file",
        file
    );

    try {

        const response =
            await fetch(
                "/api/analyze",
                {
                    method: "POST",
                    body: formData
                }
            );

        const result =
            await response.json();

        if (!response.ok) {

            throw new Error(
                result.error ||
                "Analysis failed."
            );
        }

        projectId =
            result.project_id;

        $("projectName")
            .textContent =
            result.project_name;

        $("landing")
            .classList
            .add("hidden");

        $("dashboard")
            .classList
            .remove("hidden");

        $("exportBtn")
            .href =
            `/api/project/${projectId}/export`;

        $("exportBtn")
            .classList
            .remove("disabled");

        await loadProject();

        showStatus("");

    } catch (error) {

        showStatus(
            error.message
        );
    }
}


async function loadProject() {

    const response =
        await fetch(
            `/api/project/${projectId}`
        );

    const result =
        await response.json();

    if (!response.ok) {

        throw new Error(
            result.error ||
            "Could not load project."
        );
    }

    project = result;

    renderMetrics();
    renderScore();
    renderFiles();
    renderGraph();
    renderHotspots();
    renderInsights();
    renderCycles();
}


function renderMetrics() {

    const values = [

        ["Files", project.metrics.files],

        ["Lines", project.metrics.lines],

        [
            "Functions",
            project.metrics.functions
        ],

        [
            "Classes",
            project.metrics.classes
        ],

        [
            "Dependencies",
            project.metrics.dependencies
        ],

        [
            "Cycles",
            project.metrics.cycles
        ],

        [
            "TODOs",
            project.metrics.todos
        ]

    ];

    $("metrics")
        .innerHTML =
        values
            .map(
                ([label, value]) => `

                    <div class="metric">

                        <span>
                            ${label}
                        </span>

                        <strong>
                            ${
                                Number(
                                    value
                                ).toLocaleString()
                            }
                        </strong>

                    </div>

                `
            )
            .join("");
}


function renderScore() {

    const score =
        project.metrics
            .architecture_score;

    $("score")
        .textContent =
        score;

    if (score >= 85) {

        $("scoreLabel")
            .textContent =
            "Healthy";

        $("scoreText")
            .textContent =
            "The current checks look good.";

    } else if (score >= 65) {

        $("scoreLabel")
            .textContent =
            "Fair";

        $("scoreText")
            .textContent =
            "A few areas deserve review.";

    } else {

        $("scoreLabel")
            .textContent =
            "Needs attention";

        $("scoreText")
            .textContent =
            "Several structural signals need review.";
    }
}


function renderFiles() {

    const query =
        $("searchInput")
            .value
            .trim()
            .toLowerCase();

    const files =
        project.files.filter(
            file =>
                !query ||
                `${file.path} ${file.module}`
                    .toLowerCase()
                    .includes(query)
        );

    $("fileList")
        .innerHTML =
        files.length

            ? files
                .map(
                    file => `

                        <button
                            class="file-item ${
                                file.path === selectedPath
                                    ? "active"
                                    : ""
                            }"
                            data-path="${escapeHtml(
                                file.path
                            )}"
                        >

                            ${escapeHtml(
                                file.path
                            )}

                        </button>

                    `
                )
                .join("")

            : `
                <div class="empty">
                    No matching files.
                </div>
            `;

    document
        .querySelectorAll(
            ".file-item"
        )
        .forEach(
            button => {

                button.addEventListener(
                    "click",
                    () =>
                        selectFile(
                            button.dataset.path
                        )
                );

            }
        );
}


function renderGraph() {

    if (!window.cytoscape) {

        showError(
            "Cytoscape could not be loaded."
        );

        return;
    }

    if (graph) {
        graph.destroy();
    }

    const nodes =
        project.files.map(
            file => ({

                data: {

                    id:
                        file.path,

                    label:
                        file.path
                            .split("/")
                            .pop(),

                    dependents:
                        file.dependent_count
                }

            })
        );

    const edges =
        project.edges.map(
            edge => ({

                data: {

                    id:
                        `${edge.source}->${edge.target}`,

                    source:
                        edge.source,

                    target:
                        edge.target

                }

            })
        );

    graph =
        cytoscape({

            container:
                $("graph"),

            elements:
                [
                    ...nodes,
                    ...edges
                ],

            layout: {

                name: "cose",

                animate: false,

                padding: 45,

                idealEdgeLength: 130,

                nodeRepulsion: 8000

            },

            style: [

                {
                    selector: "node",

                    style: {

                        "background-color":
                            "#67b5ff",

                        "border-color":
                            "#c2e4ff",

                        "border-width":
                            1,

                        "label":
                            "data(label)",

                        "color":
                            "#dce9f7",

                        "font-size":
                            9,

                        "text-valign":
                            "bottom",

                        "text-margin-y":
                            7,

                        "text-wrap":
                            "ellipsis",

                        "text-max-width":
                            100,

                        "width":
                            "mapData(dependents,0,6,20,46)",

                        "height":
                            "mapData(dependents,0,6,20,46)"
                    }
                },

                {
                    selector:
                        "node.selected",

                    style: {

                        "background-color":
                            "#9788ff",

                        "border-color":
                            "#ffffff",

                        "border-width":
                            3
                    }
                },

                {
                    selector:
                        "node.related",

                    style: {

                        "background-color":
                            "#55d5a5",

                        "border-color":
                            "#d0f7e7"
                    }
                },

                {
                    selector:
                        "node.dim",

                    style: {

                        "opacity":
                            0.14
                    }
                },

                {
                    selector:
                        "edge",

                    style: {

                        "curve-style":
                            "bezier",

                        "line-color":
                            "#536e88",

                        "target-arrow-color":
                            "#536e88",

                        "target-arrow-shape":
                            "triangle",

                        "width":
                            1.5
                    }
                }

            ]

        });

    graph.on(
        "tap",
        "node",
        event => {

            selectFile(
                event.target.id()
            );

        }
    );
}


async function selectFile(path) {

    selectedPath =
        path;

    renderFiles();

    try {

        const response =
            await fetch(
                `/api/project/${projectId}/file?path=${encodeURIComponent(
                    path
                )}`
            );

        const file =
            await response.json();

        if (!response.ok) {

            throw new Error(
                file.error ||
                "Could not load file."
            );
        }

        renderFileDetails(
            file
        );

        if (graph) {

            graph
                .elements()
                .removeClass(
                    "selected related dim"
                );

            const selectedNode =
                graph.getElementById(
                    path
                );

            const related =
                selectedNode
                    .closedNeighborhood()
                    .nodes()
                    .not(
                        selectedNode
                    );

            graph
                .elements()
                .addClass(
                    "dim"
                );

            selectedNode
                .removeClass(
                    "dim"
                )
                .addClass(
                    "selected"
                );

            related
                .removeClass(
                    "dim"
                )
                .addClass(
                    "related"
                );

            graph.fit(
                selectedNode.union(
                    related
                ),
                80
            );
        }

    } catch (error) {

        showError(
            error.message
        );
    }
}


function renderFileDetails(file) {

    $("detailTitle")
        .textContent =
        file.path
            .split("/")
            .pop();

    $("detailPath")
        .textContent =
        file.path;

    $("detailStats")
        .innerHTML = [

            ["Lines", file.lines],

            [
                "Functions",
                file.functions.length
            ],

            [
                "Classes",
                file.classes.length
            ],

            [
                "Imports",
                file.imports.length
            ],

            [
                "TODOs",
                file.todo_count
            ],

            [
                "Dependencies",
                file.dependencies.length
            ]

        ]

        .map(
            ([label, value]) => `

                <div class="detail-stat">

                    <span>
                        ${label}
                    </span>

                    <strong>
                        ${value}
                    </strong>

                </div>

            `
        )

        .join("");

    $("dependencies")
        .innerHTML =
        makeChips(
            file.dependencies
        );

    $("dependents")
        .innerHTML =
        makeChips(
            file.dependents
        );

    $("imports")
        .innerHTML =
        makeChips(
            file.imports.map(
                item =>
                    item.module
            )
        );

    $("sourceBtn")
        .disabled =
        false;

    $("sourceBtn")
        .onclick =
        () => {

            $("sourceTitle")
                .textContent =
                file.path
                    .split("/")
                    .pop();

            $("sourcePath")
                .textContent =
                file.path;

            $("sourceCode")
                .textContent =
                file.source;

            $("sourceDialog")
                .showModal();
        };
}


function makeChips(values) {

    const unique =
        [...new Set(values)];

    if (!unique.length) {

        return `
            <span class="chip">
                None
            </span>
        `;
    }

    return unique
        .map(
            value => `

                <span class="chip">

                    ${escapeHtml(
                        value
                    )}

                </span>

            `
        )
        .join("");
}


function renderHotspots() {

    const hotspots =
        project.hotspots || [];

    if (!hotspots.length) {

        $("hotspots")
            .innerHTML = `
                <div class="empty">
                    No hotspots found.
                </div>
            `;

        return;
    }

    $("hotspots")
        .innerHTML =
        hotspots
            .map(
                file => {

                    const score =
                        file.dependent_count * 4
                        +
                        file.dependency_count * 2
                        +
                        file.todo_count
                        +
                        Math.floor(
                            file.lines / 100
                        );

                    return `

                        <div class="hotspot">

                            <div class="hotspot-title">

                                ${escapeHtml(
                                    file.path
                                )}

                            </div>

                            <div class="hotspot-meta">

                                ${file.lines} lines
                                ·
                                ${file.dependent_count} dependents
                                ·
                                ${file.todo_count} TODOs
                                ·
                                score ${score}

                            </div>

                        </div>

                    `;
                }
            )
            .join("");
}


function renderInsights() {

    $("insights")
        .innerHTML =
        project.insights
            .map(
                insight => `

                    <div class="insight">

                        ${escapeHtml(
                            insight
                        )}

                    </div>

                `
            )
            .join("");
}


function renderCycles() {

    if (!project.cycles.length) {

        $("cycles")
            .innerHTML = `
                <div class="empty">
                    No circular dependencies found.
                </div>
            `;

        return;
    }

    $("cycles")
        .innerHTML =
        project.cycles
            .map(
                cycle => `

                    <div class="cycle">

                        ${
                            cycle
                                .map(
                                    escapeHtml
                                )
                                .join(
                                    " → "
                                )
                        }

                    </div>

                `
            )
            .join("");
}


$("fileInput")
    .addEventListener(
        "change",
        event =>
            uploadProject(
                event.target.files[0]
            )
    );


$("dropInput")
    .addEventListener(
        "change",
        event =>
            uploadProject(
                event.target.files[0]
            )
    );


$("searchInput")
    .addEventListener(
        "input",
        renderFiles
    );


$("fitBtn")
    .addEventListener(
        "click",
        () => {

            if (graph) {

                graph.fit(
                    undefined,
                    40
                );

            }

        }
    );


$("resetBtn")
    .addEventListener(
        "click",
        () => {

            selectedPath = "";

            renderFiles();

            $("detailTitle")
                .textContent =
                "Select a file";

            $("detailPath")
                .textContent =
                "No file selected";

            $("detailStats")
                .innerHTML = "";

            $("dependencies")
                .textContent =
                "—";

            $("dependents")
                .textContent =
                "—";

            $("imports")
                .textContent =
                "—";

            $("sourceBtn")
                .disabled =
                true;

            if (graph) {

                graph
                    .elements()
                    .removeClass(
                        "selected related dim"
                    );
            }
        }
    );


$("closeDialog")
    .addEventListener(
        "click",
        () =>
            $("sourceDialog").close()
    );


const dropzone =
    $("dropzone");


[
    "dragenter",
    "dragover"
]
.forEach(
    type => {

        dropzone.addEventListener(
            type,
            event => {

                event.preventDefault();

                dropzone.classList.add(
                    "dragging"
                );
            }
        );

    }
);


[
    "dragleave",
    "drop"
]
.forEach(
    type => {

        dropzone.addEventListener(
            type,
            event => {

                event.preventDefault();

                dropzone.classList.remove(
                    "dragging"
                );
            }
        );

    }
);


dropzone.addEventListener(
    "drop",
    event => {

        uploadProject(
            event.dataTransfer.files[0]
        );

    }
);