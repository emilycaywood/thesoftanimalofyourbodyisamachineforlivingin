"""Graph engine: typed DAG, incremental recompute, expensive nodes, clusters."""

import pytest
from calflab.graph import Evaluator, Graph, GraphEdge, GraphNode, default_graph, node_types
from calflab.graph.nodes import SOCKET_TYPES


def test_default_graph_is_the_documented_pipeline():
    g = default_graph()
    assert g.topo_order().index("genome") < g.topo_order().index("morphology") < g.topo_order().index("mjcf")
    assert set(g.roles) == {"genome", "design", "model", "controller", "simulation", "metrics", "fitness"}
    types = node_types()
    for n in g.nodes:
        assert n.type in types
        for s in types[n.type].inputs + types[n.type].outputs:
            assert s.type in SOCKET_TYPES


def test_node_types_come_from_plugin_schemas():
    types = node_types()
    for key in ("genome:calf", "part_generator:calf", "controller:cpg", "simulator:mujoco",
                "fitness_term:forward_speed", "exporter:gltf", "mjcf", "metrics", "fitness", "slider"):
        assert key in types
    desc = types["controller:cpg"].describe()
    assert {f["name"] for f in desc["schema"]["fields"]} >= {"gait", "frequency"}
    assert "simulator:mjx" not in types, "stubs are not offered as nodes"


def test_cheap_nodes_evaluate_and_expensive_nodes_wait():
    ev = Evaluator()
    res = ev.evaluate(default_graph())
    assert res["morphology"].status == "ok" and res["mjcf"].status == "ok" and res["mass"].status == "ok"
    assert res["sim"].status == "stale"
    assert res["metrics"].status == "stale" and res["fitness"].status == "stale"


def test_incremental_recompute_only_downstream():
    ev = Evaluator()
    g = default_graph()
    ev.evaluate(g)
    again = ev.evaluate(g)
    assert all(again[n].cached for n in ("genome", "morphology", "mjcf", "controller"))

    g.node("controller").params["frequency"] = 2.0
    res = ev.evaluate(g)
    assert res["morphology"].cached and res["mjcf"].cached
    assert not res["controller"].cached

    g.node("genome").params["shank_length"] = 190
    res = ev.evaluate(g)
    assert not res["genome"].cached and not res["morphology"].cached and not res["mjcf"].cached
    assert res["controller"].cached


def test_running_the_sim_fills_the_pipeline_and_is_cached():
    ev = Evaluator()
    g = default_graph()
    g.node("sim").params["duration_s"] = 1.0
    res = ev.evaluate(g, run_expensive={"sim"})
    assert res["sim"].status == "ok" and res["metrics"].status == "ok"
    assert isinstance(res["fitness"].outputs["total"], float)
    res2 = ev.evaluate(g)  # no run flag needed any more
    assert res2["sim"].cached and res2["fitness"].status == "ok"
    assert res2["sim"].key == res["sim"].key


def test_errors_and_disabled_nodes_are_reported_on_nodes():
    ev = Evaluator()
    g = default_graph()
    g.edges = [e for e in g.edges if e.target != "morphology"]
    res = ev.evaluate(g)
    assert res["morphology"].status == "error" and "not connected" in res["morphology"].messages[0]
    assert res["mjcf"].status == "blocked"

    g = default_graph()
    g.node("morphology").enabled = False
    res = ev.evaluate(g)
    assert res["morphology"].status == "disabled" and res["mjcf"].status == "blocked"

    g = default_graph()
    g.node("mjcf").params["timestep_ms"] = 999
    assert ev.evaluate(g)["mjcf"].status == "error"

    g = default_graph()
    g.nodes.append(GraphNode(id="x", type="no_such_type"))
    assert "Unknown node type" in ev.evaluate(g)["x"].messages[0]


def test_cycles_are_rejected():
    g = Graph(
        nodes=[GraphNode(id="a", type="panel"), GraphNode(id="b", type="panel")],
        edges=[
            GraphEdge(id="1", source="a", source_socket="out", target="b", target_socket="in"),
            GraphEdge(id="2", source="b", source_socket="out", target="a", target_socket="in"),
        ],
    )
    with pytest.raises(ValueError, match="cycle"):
        g.topo_order()
    assert all(r.status == "error" for r in Evaluator().evaluate(g).values())


def test_slider_drives_a_gene():
    g = default_graph()
    g.nodes += [
        GraphNode(id="s", type="slider", params={"value": 200, "min": 100, "max": 260}),
        GraphNode(id="set", type="gene_set", params={"gene": "thigh_length"}),
    ]
    g.edges = [e for e in g.edges if e.target != "morphology"]
    g.edges += [
        GraphEdge(id="e1", source="genome", source_socket="genome", target="set", target_socket="genome"),
        GraphEdge(id="e2", source="s", source_socket="value", target="set", target_socket="value"),
        GraphEdge(id="e3", source="set", source_socket="genome", target="morphology", target_socket="genome"),
    ]
    res = Evaluator().evaluate(g)
    design = res["morphology"].outputs["design"]
    assert design.genome.values["thigh_length"] == 200


def test_cluster_evaluates_like_its_contents():
    inner = Graph(
        nodes=[
            GraphNode(id="i", type="cluster_input", params={"name": "genome", "type": "genome"}),
            GraphNode(id="set", type="gene_set", params={"gene": "trunk_length"}),
            GraphNode(id="n", type="number", params={"value": 500}),
            GraphNode(id="o", type="cluster_output", params={"name": "genome", "type": "genome"}),
        ],
        edges=[
            GraphEdge(id="1", source="i", source_socket="value", target="set", target_socket="genome"),
            GraphEdge(id="2", source="n", source_socket="value", target="set", target_socket="value"),
            GraphEdge(id="3", source="set", source_socket="genome", target="o", target_socket="value"),
        ],
    )
    g = default_graph()
    g.nodes.append(GraphNode(id="c", type="cluster", params={"graph": inner.model_dump()}))
    g.edges = [e for e in g.edges if e.target != "morphology"]
    g.edges += [
        GraphEdge(id="a", source="genome", source_socket="genome", target="c", target_socket="genome"),
        GraphEdge(id="b", source="c", source_socket="genome", target="morphology", target_socket="genome"),
    ]
    ev = Evaluator()
    res = ev.evaluate(g)
    assert res["c"].status == "ok"
    assert res["morphology"].outputs["design"].genome.values["trunk_length"] == 500
    g.node("genome").params["trunk_width"] = 180  # upstream change flows through the cluster
    assert ev.evaluate(g)["morphology"].outputs["design"].genome.values["trunk_width"] == 180
