import os
BASE = "/Users/riccardo.bedogni/Desktop/uni/business_intelligence/experiments"
SRC = os.path.join(BASE, "source")

# (name, props, columns, approx)
scenarios = {
 # Unionable: horizontal split, 0% row overlap, noisy schema (abbrev=2) + noisy instances
 "patients_horizontal_0_ac2_av": dict(
    vertical=False, horizontal=True, overlap=0,
    pk=0, columns=30,
    approx=True, approx_columns=True, approx_columns_type=2),
 # Joinable: vertical split, 50% column overlap, noisy schema (drop vowels=3), verbatim instances
 "patients_vertical_50_ac3_ev": dict(
    vertical=True, horizontal=False, overlap=100,
    pk=0, columns=50,
    approx=False, approx_columns=True, approx_columns_type=3),
 # View-Unionable: both splits, 0% row / 50% col overlap, noisy schema(2), noisy instances
 "patients_both_0_50_ac2_av": dict(
    vertical=True, horizontal=True, overlap=0,
    pk=0, columns=50,
    approx=True, approx_columns=True, approx_columns_type=2),
 # Semantically-Joinable: vertical split, 50% col overlap, verbatim schema, noisy instances
 "patients_vertical_50_ec_av": dict(
    vertical=True, horizontal=False, overlap=100,
    pk=0, columns=50,
    approx=True, approx_columns=False, approx_columns_type=5),
}

tmpl = """[Paths]
home_dir: {base}
input_dir: ${{Paths:home_dir}}/source
output_dir: ${{Paths:home_dir}}/target/

[Files]
source_data: ${{Paths:input_dir}}/patients.csv
source_schema: ${{Paths:input_dir}}/patients_schema.csv
output_files: {name}

[Properties]
overlap: {overlap}
random_overlap: False
vertical_split: {vertical}
horizontal_split: {horizontal}

[Columns]
PK: {pk}
split_pk: True
split_random: False
columns: {columns}

[Approximation]
approx: {approx}
percentage: 100
approx_percentage: 20
approx_columns: {approx_columns}
approx_columns_type: {approx_columns_type}
"""

os.makedirs(os.path.join(BASE,"configs"), exist_ok=True)
for name, s in scenarios.items():
    cfg = tmpl.format(base=BASE, name=name,
        overlap=s["overlap"], vertical=s["vertical"], horizontal=s["horizontal"],
        pk=s["pk"], columns=s["columns"], approx=s["approx"],
        approx_columns=s["approx_columns"], approx_columns_type=s["approx_columns_type"])
    p = os.path.join(BASE,"configs", name+".ini")
    open(p,"w").write(cfg)
    print("wrote", p)
