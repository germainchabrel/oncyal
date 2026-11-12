import ast, json
src = open("prepare_06.py", encoding="utf-8").read()
for n in ast.parse(src).body:
    if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "L0" for t in n.targets):
        L0 = ast.literal_eval(n.value)
for k in ("motorway", "trunk", "primary", "secondary", "tertiary"):
    L0[k + "_link"] = L0[k]
hw = sorted(L0)
json.dump(hw, open("out/tuiles/hw.json", "w"))
print(len(hw), hw)
