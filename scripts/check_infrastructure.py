import json
from pathlib import Path
import networkx as nx

root = Path(__file__).resolve().parents[1]
template = json.loads(
    (root / "infrastructure/cdk.out/AquaAgent.template.json").read_text()
)
resources = template["Resources"]
graph = nx.DiGraph()
graph.add_nodes_from(resources)


def dependencies(value):
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "Ref" and item in resources:
                found.add(item)
            elif key == "Fn::GetAtt":
                name = item[0] if isinstance(item, list) else item.split(".")[0]
                if name in resources:
                    found.add(name)
            else:
                found.update(dependencies(item))
    elif isinstance(value, list):
        for item in value:
            found.update(dependencies(item))
    return found


for name, resource in resources.items():
    graph.add_edges_from((name, dep) for dep in dependencies(resource) if dep != name)
    deps = resource.get("DependsOn", [])
    graph.add_edges_from(
        (name, dep) for dep in ([deps] if isinstance(deps, str) else deps)
    )
assert nx.is_directed_acyclic_graph(graph), list(nx.simple_cycles(graph))
types = [r["Type"] for r in resources.values()]
required = [
    "AWS::DynamoDB::Table",
    "AWS::S3::Bucket",
    "AWS::Cognito::UserPool",
    "AWS::StepFunctions::StateMachine",
    "AWS::Amplify::App",
    "AWS::Amplify::Branch",
    "AWS::ApiGatewayV2::Api",
]
assert all(t in types for t in required)
assert sum(t == "AWS::Lambda::Function" for t in types) == 7
machine = next(
    r for r in resources.values() if r["Type"] == "AWS::StepFunctions::StateMachine"
)
assert "waitForTaskToken" in json.dumps(machine)
assert machine["Properties"]["StateMachineType"] == "STANDARD"
public_routes = [
    r
    for r in resources.values()
    if r["Type"] == "AWS::ApiGatewayV2::Route"
    and "/public/" in r.get("Properties", {}).get("RouteKey", "")
]
assert all(r["Properties"]["AuthorizationType"] == "NONE" for r in public_routes)
print(
    f"Verified {len(resources)} synthesized resources, no dependency cycles, callback workflow, protected/public API split"
)
