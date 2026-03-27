"""
Patch onshape-to-robot at build time so parts without material
(missing mass/centroid/inertia in API response) don't crash the export.
Zero mass is written to the URDF and flagged as "no weight" in the UI.
"""
import pathlib
import site

for d in site.getsitepackages():
    p = pathlib.Path(d) / "onshape_to_robot" / "robot_builder.py"
    if not p.exists():
        continue
    c = p.read_text()
    patched = c
    patched = patched.replace(
        'mass_properties["mass"]',
        'mass_properties.get("mass", [0.0])',
    )
    patched = patched.replace(
        'mass_properties["centroid"]',
        'mass_properties.get("centroid", [0.0, 0.0, 0.0, 0.0])',
    )
    patched = patched.replace(
        'mass_properties["inertia"]',
        'mass_properties.get("inertia", [0.0] * 12)',
    )
    if patched != c:
        p.write_text(patched)
        print(f"Patched {p}: parts without material now export with zero mass")
    else:
        print(f"Patch already applied or pattern not found in {p}")
    break
else:
    print("WARNING: onshape_to_robot/robot_builder.py not found — skipping patch")
