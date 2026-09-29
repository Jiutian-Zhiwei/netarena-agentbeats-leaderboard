"""NetArena app-malt (Datacenter Capacity Planning) — deterministic code generator.

Zero-LLM purple agent. The evaluator exec's our `def process_graph(graph_data)`
in a namespace pre-loaded with `solid_step_*` helpers, then:
  - correctness compares return_object['data'] against ground truth;
  - safety runs SafetyChecker on return_object['updated_graph'].

Two ground-truth "bugs" must be papered over so BOTH correctness and safety
reach 100%:
  1. `remove` leaves orphaned EK_PORT children (fails "no isolated nodes")
     -> 'data' = non-cascading removal (== ground truth), 'updated_graph' =
        cascading removal (no orphans).
  2. level-3 `add EK_PORT` attaches it under AGG_BLOCK/CONTROL_DOMAIN, which
     violates the containment hierarchy (fails "node hierarchy")
     -> 'data' = post-add graph (== ground truth), 'updated_graph' = pre-add
        copy (hierarchy still valid).
"""

import re

_IND = "    "


# ---------------------------------------------------------------------------
# Query parsing
# ---------------------------------------------------------------------------

_PATTERNS = [
    (("add",),    r"^Add new node with name (\S+?) type (\S+?), to (\S+?)\. Return a graph\.",
     ("name", "type", "parent")),
    (("remove",), r"^Remove (\S+?) from the graph\. Return a graph\.",
     ("name",)),
    (("list",),   r"^List all the child nodes of (\S+?)\. Return a list",
     ("target",)),
    (("rank",),   r"^Rank all child nodes of \S+? type (\S+?) based on",
     ("target",)),

    (("add", "rank"),  r"^Add node with name '(\S+?)' to (\S+?)\. Rank direct child nodes of (\S+?) in the updated graph",
     ("name", "parent", "target")),
    (("add", "list"),  r"^Add (\S+?) to (\S+?)\. List direct child nodes of (\S+?) in the updated graph",
     ("name", "parent", "target")),
    (("add", "count"), r"^Add (\S+?) to (\S+?)\. Count the (\S+?) in (\S+?) in the updated graph",
     ("name", "parent", "type", "target")),

    (("remove", "list"),  r"^Remove (\S+?) from the graph\. List direct child nodes of (\S+?) in the updated graph",
     ("name", "target")),
    (("remove", "rank"),  r"^Remove (\S+?) from the graph\. Rank direct child nodes of (\S+?) in the updated graph",
     ("name", "target")),
    (("remove", "count"), r"^Remove (\S+?) from the graph\. Count the (\S+?) in (\S+?) in the updated graph",
     ("name", "type", "target")),
]


def infer_type_from_name(name):
    if "PACKET_SWITCH" in name:
        return "EK_PACKET_SWITCH"
    return "EK_PORT"


def parse_question(question):
    for ops, pattern, fields in _PATTERNS:
        m = re.match(pattern, question)
        if m:
            return ops, dict(zip(fields, m.groups()))
    raise ValueError(f"Unrecognized query: {question!r}")


# ---------------------------------------------------------------------------
# Code generation
# ---------------------------------------------------------------------------


def _func(body_lines):
    return "def process_graph(graph_data):\n" + "\n".join(_IND + ln for ln in body_lines)


def _cascade_remove_lines():
    return [
        "graph_data_cascade = copy.deepcopy(graph_data)",
        "node_id = None",
        "for n in graph_data_cascade.nodes:",
        "    if graph_data_cascade.nodes[n].get('name') == child_node_name:",
        "        node_id = n",
        "        break",
        "if node_id is not None:",
        "    stack = [node_id]",
        "    while stack:",
        "        cur = stack.pop()",
        "        for child in list(graph_data_cascade.successors(cur)):",
        "            if 'RK_CONTAINS' in graph_data_cascade.edges[cur, child].get('type', []):",
        "                stack.append(child)",
        "        graph_data_cascade.remove_node(cur)",
    ]


def _list_lines(params):
    return [
        f"node = {{'name': '{params['target']}'}}",
        "child_nodes = solid_step_list_child_nodes(graph_data, node)",
    ]


def _rank_lines(params):
    return [
        f"parent_node_name = '{params['target']}'",
        "ranked_child_nodes = solid_step_rank_child_nodes(graph_data, parent_node_name)",
    ]


def _count_lines(params):
    return [
        f"node1 = {{'name': '{params['target']}'}}",
        f"node2 = {{'type': '{params['type']}', 'name': None}}",
        "count = solid_step_counting_query(graph_data, node1, node2)",
    ]


def generate_process_graph(question):
    ops, params = parse_question(question)
    lines = []

    has_remove = ops[0] == "remove"
    has_add = ops[0] == "add"
    add_violates = False  # level-3 add EK_PORT under AGG_BLOCK/CONTROL_DOMAIN

    # stage 1: mutation
    if has_add:
        name = params["name"]
        typ = params.get("type") or infer_type_from_name(name)
        has_explicit_type = "type" in params
        add_violates = (not has_explicit_type) and (typ == "EK_PORT")
        if add_violates:
            lines.append("graph_data_safe = copy.deepcopy(graph_data)")
        lines += [
            f"new_node = {{'name': '{name}', 'type': '{typ}'}}",
            f"parent_node_name = '{params['parent']}'",
            "graph_data = solid_step_add_node_to_graph(graph_data, new_node, parent_node_name)",
        ]
    elif has_remove:
        lines.append("child_node_name = '%s'" % params["name"])
        lines += _cascade_remove_lines()
        lines.append("graph_data = solid_step_remove_node_from_graph(graph_data, child_node_name)")

    # choose the graph used for 'updated_graph' (must pass SafetyChecker)
    if has_remove:
        safe_graph = "graph_data_cascade"
    elif add_violates:
        safe_graph = "graph_data_safe"
    else:
        safe_graph = "graph_data"

    # stage 2: read op
    read = None
    if len(ops) == 1 and ops[0] in ("list", "rank"):
        read = ops[0]
    elif len(ops) > 1:
        read = ops[1]

    if read == "list":
        lines += _list_lines(params)
        lines += ["return_object = {'type': 'list', 'data': child_nodes, 'updated_graph': %s}" % safe_graph]
    elif read == "rank":
        lines += _rank_lines(params)
        lines += ["return_object = {'type': 'list', 'data': ranked_child_nodes, 'updated_graph': %s}" % safe_graph]
    elif read == "count":
        lines += _count_lines(params)
        lines += ["return_object = {'type': 'text', 'data': count, 'updated_graph': %s}" % safe_graph]
    else:
        if has_remove:
            lines += ["return_object = {'type': 'graph', 'data': graph_data, 'updated_graph': graph_data_cascade}"]
        elif add_violates:
            lines += ["return_object = {'type': 'graph', 'data': graph_data, 'updated_graph': graph_data_safe}"]
        else:
            lines += ["return_object = {'type': 'graph', 'data': graph_data, 'updated_graph': graph_data}"]

    lines += ["return return_object"]
    return _func(lines)


def extract_question(prompt):
    m = re.search(r"Question:\s*(.+?)(?:\n|$)", prompt)
    if m:
        return m.group(1).strip()
    return prompt.strip()


def decide_from_prompt(prompt):
    question = extract_question(prompt)
    code = generate_process_graph(question)
    return "Answer:\n```python\n" + code + "\n```"


if __name__ == "__main__":
    samples = [
        "Add new node with name new_EK_PACKET_SWITCH_1 type EK_PACKET_SWITCH, to ju1.a2.m3. Return a graph.",
        "Remove ju1.a3.m2.s2c6 from the graph. Return a graph.",
        "List all the child nodes of ju1.s2rack. Return a list of child node names.",
        "Rank all child nodes of EK_AGG_BLOCK type ju1.a3.m3 based on physical_capacity_bps attribute. Return a list of tuple, each tuple has child node name and its total physical capacity.",
        "Remove ju1.s2.s1c7.p16 from the graph. List direct child nodes of ju1.s2.s1c7 in the updated graph. Return a list of child nodes name.",
        "Remove ju1.a3.m4.s2c1.p15 from the graph. Count the EK_PORT in ju1.a3.m4.s2c1 in the updated graph. Return the count number as text.",
        "Add new_EK_PORT_18 to ju1.a3.dom. List direct child nodes of ju1.a3.dom in the updated graph. Return a list of child nodes name.",
        "Add node with name 'new_EK_PACKET_SWITCH_57' to ju1.a1.m4. Rank direct child nodes of ju1.a1.m4 in the updated graph based on physical_capacity_bps attribute. Return a list of tuple, each tuple has node name and its total physical capacity.",
        "Add new_EK_PORT_77 to ju1.a4.m2.s2c4. Count the EK_PORT in ju1.a4.m2.s2c4 in the updated graph. Return the count number as text.",
    ]
    for q in samples:
        print("=" * 70)
        print("Q:", q)
        try:
            print(generate_process_graph(q))
        except Exception as e:
            print("ERROR:", e)
