"""Legacy external-dataset importer is retained as an explicit disabled entrypoint.

Its source rights, location precision and incident assertions have not been
qualified for the public release. No fetch or database mutation is performed.
"""
raise SystemExit("Disabled: external dataset import requires a qualified, provenance-preserving adapter.")
