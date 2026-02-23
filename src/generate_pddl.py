#!/usr/bin/env python3
"""
AAS2PDDL - PDDL Generator from Asset Administration Shells

Generates PDDL planning problems from AAS models and optionally solves them.

Modes:
  Single:  --input points to a directory with AASX files
  DSE:     --input points to a directory with subdirectories, each containing AASX files

Standards:
  - IDTA 02011: HierarchicalStructures (Types)
  - VDI 3682:   ProcessOperator (Actions)
  - IEC 61360:  DataElementType (Predicates, States)
  - IDTA 02016: ComponentInstances (Objects, Init, Goals)

Usage:
    python generate_pddl.py --input examples/mps500/aasx/
    python generate_pddl.py --input examples/mps500/aasx/ --solve
    python generate_pddl.py --input examples/mps500/aasx/ --solve --optimal
    python generate_pddl.py --input examples/mps500/ --solve --optimal   # DSE mode
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import unified_planning as up
from unified_planning.shortcuts import get_environment, OneshotPlanner

from aas_loader import AASLoader
from aas_extractor import AASExtractor
from pddl_builder import UPFProblemBuilder


def extractAndBuild(inputDir: Path, domainName: str = None) -> Tuple[UPFProblemBuilder, Dict]:
    """Load AASX files, extract planning data, build UPF problem.

    Returns:
        (builder, stats) - The UPF problem builder and extraction statistics
    """
    loader = AASLoader(inputDir, domainName=domainName)
    loader.load()

    extractor = AASExtractor(loader)
    hierarchy = extractor.extractTypeHierarchy()
    predicates = extractor.extractDataElementTypes()
    operators = extractor.extractProcessOperators()
    instances = extractor.extractInstances()
    initStates, goals = extractor.extractInitialStatesAndGoals()

    builder = UPFProblemBuilder(loader.domainName)
    builder.buildTypes(hierarchy)
    builder.buildFluents(predicates)
    builder.buildActions(operators)
    builder.buildObjects(instances)
    builder.buildInit(initStates)
    builder.buildGoals(goals)

    stats = {
        'domain': loader.domainName,
        'types': len(builder.typeMap),
        'predicates': len(builder.fluentMap),
        'actions': len(builder.problem.actions),
        'objects': len(builder.objectMap),
        'init': len(builder.problem.initial_values),
        'goals': len(builder.problem.goals),
    }

    return builder, stats


def listApplicablePlanners(problem) -> List[str]:
    """Query UPF for planners that can handle this problem."""
    env = get_environment()
    factory = env.factory
    kind = problem.kind
    applicable = factory.get_all_applicable_engines(kind)
    # Filter to only actual planners (not compilers, validators, etc.)
    plannerNames = [name for name in applicable
                    if not name.startswith('up_')
                    and 'remover' not in name
                    and 'grounder' not in name
                    and 'validator' not in name
                    and 'simulator' not in name
                    and 'replanner' not in name
                    and 'oversubscription' not in name]
    return plannerNames


def solveProblem(problem, plannerName: str = None, optimal: bool = False) -> Tuple[str, int]:
    """Solve a UPF problem.

    Args:
        problem: UPF Problem
        plannerName: Explicit planner name (e.g. 'fast-downward')
        optimal: Use optimal planner variant if available

    Returns:
        (status, planLength)
    """
    if plannerName:
        name = plannerName
    elif optimal:
        name = 'fast-downward-opt'
    else:
        name = 'fast-downward'

    try:
        with OneshotPlanner(name=name) as planner:
            result = planner.solve(problem)

            if result.status in [
                up.engines.results.PlanGenerationResultStatus.SOLVED_SATISFICING,
                up.engines.results.PlanGenerationResultStatus.SOLVED_OPTIMALLY
            ]:
                planLength = len(result.plan.actions) if result.plan else 0
                statusStr = "Optimal" if result.status == up.engines.results.PlanGenerationResultStatus.SOLVED_OPTIMALLY else "Satisficing"
                return (statusStr, planLength, result)
            elif result.status == up.engines.results.PlanGenerationResultStatus.UNSOLVABLE_PROVEN:
                return ("Unsolvable", 0, result)
            else:
                return (str(result.status), 0, result)

    except Exception as e:
        print(f"  [ERROR] {e}")
        return ("Error", 0, None)


def detectMode(inputPath: Path) -> str:
    """Detect whether input is single AASX dir or DSE with subdirectories."""
    aasxFiles = list(inputPath.glob("*.aasx"))
    if aasxFiles:
        return "single"

    # Check for subdirectories with AASX files
    subdirs = [d for d in sorted(inputPath.iterdir())
               if d.is_dir() and list(d.glob("*.aasx"))]
    if subdirs:
        return "dse"

    return "empty"


def runSingle(inputDir: Path, outputDir: Path, args) -> Optional[Tuple[str, int]]:
    """Run single-mode: one AASX directory -> PDDL + optional solve."""
    builder, stats = extractAndBuild(inputDir, domainName=args.domain)

    print()
    print("=" * 70)
    print(f"  Domain:     {stats['domain']}")
    print(f"  Types:      {stats['types']}")
    print(f"  Predicates: {stats['predicates']}")
    print(f"  Actions:    {stats['actions']}")
    print(f"  Objects:    {stats['objects']}")
    print(f"  Init:       {stats['init']}")
    print(f"  Goals:      {stats['goals']}")
    print("=" * 70)

    # Export PDDL
    domainFile, problemFile = builder.exportPddl(outputDir)

    # List applicable planners
    applicable = listApplicablePlanners(builder.problem)
    if applicable:
        print(f"\n  Applicable planners (UPF): {', '.join(applicable)}")

    # Solve
    solveResult = None
    if args.solve:
        print(f"\n  Solving with {'optimal' if args.optimal else 'satisficing'} planner...")
        status, length, result = solveProblem(builder.problem, args.planner, args.optimal)
        print(f"  Result: {status} ({length} steps)")
        solveResult = (status, length)

        if result and result.plan:
            # Save solution
            solutionDir = outputDir / "solutions"
            solutionDir.mkdir(exist_ok=True, parents=True)
            solutionFile = solutionDir / f"{stats['domain']}_plan.txt"
            with open(solutionFile, 'w', encoding='utf-8') as f:
                f.write(f"Domain: {stats['domain']}\n")
                f.write(f"Status: {status}\n")
                f.write(f"Steps:  {length}\n\n")
                for i, action in enumerate(result.plan.actions, 1):
                    f.write(f"{i}. {action}\n")
            print(f"  Solution: {solutionFile}")

    print(f"\n  PDDL Domain:  {domainFile}")
    print(f"  PDDL Problem: {problemFile}")

    return solveResult


def runDSE(inputDir: Path, args):
    """Run DSE mode: subdirectories with AASX files -> compare variants."""
    subdirs = sorted([d for d in inputDir.iterdir()
                      if d.is_dir() and list(d.glob("*.aasx"))])

    print("=" * 70)
    print("DESIGN SPACE EXPLORATION")
    print("=" * 70)
    print(f"  Input: {inputDir}")
    print(f"  Variants: {len(subdirs)}")
    for d in subdirs:
        aasxCount = len(list(d.glob("*.aasx")))
        print(f"    {d.name}/ ({aasxCount} AASX files)")
    print()

    results = {}

    for variantDir in subdirs:
        variantName = variantDir.name
        print(f"\n{'='*70}")
        print(f"VARIANT: {variantName}")
        print(f"{'='*70}")

        outputDir = variantDir.parent / f"pddl_{variantName}"
        builder, stats = extractAndBuild(variantDir, domainName=variantName)

        # Export PDDL
        domainFile, problemFile = builder.exportPddl(outputDir)

        result = {
            'stats': stats,
            'domainFile': domainFile,
            'problemFile': problemFile,
            'status': None,
            'planLength': 0,
        }

        # List applicable planners (only for first variant)
        if not results:
            applicable = listApplicablePlanners(builder.problem)
            if applicable:
                print(f"\n  Applicable planners (UPF): {', '.join(applicable)}")

        # Solve
        if args.solve:
            print(f"\n  Solving ({('optimal' if args.optimal else 'satisficing')})...")
            status, length, solveResult = solveProblem(builder.problem, args.planner, args.optimal)
            result['status'] = status
            result['planLength'] = length
            print(f"  Result: {status} ({length} steps)")

            if solveResult and solveResult.plan:
                solutionDir = outputDir / "solutions"
                solutionDir.mkdir(exist_ok=True, parents=True)
                solutionFile = solutionDir / f"{variantName}_plan.txt"
                with open(solutionFile, 'w', encoding='utf-8') as f:
                    f.write(f"Variant: {variantName}\n")
                    f.write(f"Status: {status}\n")
                    f.write(f"Steps:  {length}\n\n")
                    for i, action in enumerate(solveResult.plan.actions, 1):
                        f.write(f"{i}. {action}\n")

        results[variantName] = result

    # Summary
    print(f"\n\n{'='*70}")
    print("RESULTS")
    print(f"{'='*70}")

    # Stats table
    print(f"\n{'Variant':<25} {'Types':>6} {'Preds':>6} {'Actions':>8} {'Objects':>8} {'Init':>6} {'Goals':>6}", end='')
    if args.solve:
        print(f" {'Status':>12} {'Steps':>6}", end='')
    print()
    print("-" * (67 + (20 if args.solve else 0)))

    for name, r in results.items():
        s = r['stats']
        print(f"{name:<25} {s['types']:>6} {s['predicates']:>6} {s['actions']:>8} {s['objects']:>8} {s['init']:>6} {s['goals']:>6}", end='')
        if args.solve:
            status = r['status'] or '---'
            length = r['planLength'] or '---'
            print(f" {status:>12} {length:>6}", end='')
        print()

    print(f"{'='*70}")

    # PDDL file locations
    print("\nPDDL files:")
    for name, r in results.items():
        print(f"  {name}: {r['domainFile']}")


def main():
    parser = argparse.ArgumentParser(
        description="AAS2PDDL - Generate PDDL from Asset Administration Shells",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  Single:  --input dir/with/aasx-files/
  DSE:     --input dir/with/variant-subdirs/

Examples:
  python generate_pddl.py --input examples/mps500/aasx/
  python generate_pddl.py --input examples/mps500/aasx/ --solve
  python generate_pddl.py --input examples/mps500/aasx/ --solve --optimal
  python generate_pddl.py --input examples/mps500/ --solve --optimal
        """
    )

    parser.add_argument(
        '--input', '-i',
        type=str,
        required=True,
        help='Directory with AASX files (single) or with subdirectories containing AASX files (DSE)'
    )

    parser.add_argument(
        '--domain',
        type=str,
        default=None,
        help='Explicit domain name (overrides automatic derivation, single mode only)'
    )

    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help='Output directory for PDDL files (default: pddl/ next to input)'
    )

    parser.add_argument(
        '--solve',
        action='store_true',
        help='Solve the problem after PDDL generation'
    )

    parser.add_argument(
        '--optimal',
        action='store_true',
        help='Use optimal planner (A* + LM-cut, slower but guarantees shortest plan)'
    )

    parser.add_argument(
        '--planner',
        type=str,
        default=None,
        help='Explicit UPF planner name (e.g. fast-downward, fast-downward-opt)'
    )

    args = parser.parse_args()

    # Suppress UPF credit messages
    env = get_environment()
    env.credits_stream = None

    inputPath = Path(args.input)
    if not inputPath.exists():
        print(f"[ERROR] Path not found: {inputPath}")
        sys.exit(1)

    mode = detectMode(inputPath)

    if mode == "single":
        print("=" * 70)
        print("AAS2PDDL - Single Mode")
        print("=" * 70)
        print(f"  Input: {inputPath}")

        if args.output:
            outputDir = Path(args.output)
        else:
            outputDir = inputPath.parent / "pddl"

        runSingle(inputPath, outputDir, args)

    elif mode == "dse":
        print("=" * 70)
        print("AAS2PDDL - Design Space Exploration Mode")
        print("=" * 70)

        runDSE(inputPath, args)

    else:
        print(f"[ERROR] No AASX files found in {inputPath} or its subdirectories")
        sys.exit(1)


if __name__ == "__main__":
    main()
