# AAS2PDDL

Generates PDDL planning problems from Asset Administration Shell (AAS) models. The tool reads a set of AASX files, extracts planning-relevant information (types, predicates, actions, objects, initial states, goals), and produces standard PDDL domain and problem files.

The expected AAS structure is defined in [AAS-Planning-Metamodel](https://github.com/hsu-aut/AAS-Planning-Metamodel).

## Installation

```bash
pip install -r requirements.txt
```

Requires Python 3.9+, [BaSyx Python SDK](https://github.com/eclipse-basyx/basyx-python-sdk) for AAS parsing, and the [Unified Planning Framework](https://unified-planning.readthedocs.io/) for PDDL generation and solving.

## Usage

Point the tool at a directory containing AASX files:

```bash
python src/generate_pddl.py --input examples/mps500/aasx/
```

This writes `domain.pddl` and `problem.pddl` to a `pddl/` directory next to the input. To also solve the problem:

```bash
python src/generate_pddl.py --input examples/mps500/aasx/ --solve
python src/generate_pddl.py --input examples/mps500/aasx/ --solve --optimal
```

`--optimal` uses A* with LM-cut instead of the default LAMA-first heuristic. Other UPF-compatible planners can be selected with `--planner <name>`.

### Design Space Exploration

If the input directory contains subdirectories (each with its own AASX files), the tool runs in DSE mode — it generates and optionally solves all variants and outputs a comparison table:

```bash
python src/generate_pddl.py --input examples/mps500/ --solve --optimal
```

## Project Structure

```
src/
├── generate_pddl.py     # CLI entry point
├── aas_loader.py         # AASX loading and reference resolution
├── aas_extractor.py      # Five-phase data extraction from AAS
├── pddl_builder.py       # UPF problem construction and PDDL export
└── utils.py

examples/
├── mini_example/aasx/    # Minimal example (5 types, 7 predicates, 2 actions)
└── mps500/aasx/          # MPS500 production system (11 types, 11 predicates, 9 actions)
```

## License

MIT

