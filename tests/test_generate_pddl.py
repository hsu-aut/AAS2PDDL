#!/usr/bin/env python3
"""
Tests fuer AAS2PDDL
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from aas_loader import AASLoader
from aas_extractor import AASExtractor
from pddl_builder import UPFProblemBuilder


def test_mps500():
    """Test mit MPS500 Beispiel."""
    print("=" * 80)
    print("TEST: MPS500")
    print("=" * 80)

    examplesDir = Path(__file__).parent.parent / 'examples' / 'mps500' / 'aasx'

    if not examplesDir.exists():
        print(f"[SKIP] Beispiel-Verzeichnis nicht gefunden: {examplesDir}")
        return False

    try:
        # 1. Laden
        loader = AASLoader(examplesDir, domainName='mps500_test')
        loader.load()

        assert loader.domainName == 'mps500_test', f"Domain Name falsch: {loader.domainName}"
        assert len(loader.componentAasList) > 0, "Keine AAS geladen"

        print(f"[OK] {len(loader.componentAasList)} AAS geladen")

        # 2. Extrahieren
        extractor = AASExtractor(loader)

        hierarchy = extractor.extractTypeHierarchy()
        assert len(hierarchy) > 0, "Keine Typen extrahiert"
        print(f"[OK] {len(hierarchy)} Typen extrahiert")

        predicates = extractor.extractDataElementTypes()
        assert len(predicates) > 0, "Keine Praedikate extrahiert"
        print(f"[OK] {len(predicates)} Praedikate extrahiert")

        operators = extractor.extractProcessOperators()
        assert len(operators) > 0, "Keine Aktionen extrahiert"
        print(f"[OK] {len(operators)} Aktionen extrahiert")

        instances = extractor.extractInstances()
        assert len(instances) > 0, "Keine Instanzen extrahiert"
        print(f"[OK] {len(instances)} Instanzen extrahiert")

        initStates, goals = extractor.extractInitialStatesAndGoals()
        print(f"[OK] {len(initStates)} Initial States, {len(goals)} Goals")

        # 3. UPF Problem aufbauen
        builder = UPFProblemBuilder(loader.domainName)
        builder.buildTypes(hierarchy)
        builder.buildFluents(predicates)
        builder.buildActions(operators)
        builder.buildObjects(instances)
        builder.buildInit(initStates)
        builder.buildGoals(goals)

        print(f"[OK] UPF Problem aufgebaut")
        print(f"    Typen:    {len(builder.typeMap)}")
        print(f"    Fluents:  {len(builder.fluentMap)}")
        print(f"    Aktionen: {len(builder.problem.actions)}")
        print(f"    Objekte:  {len(builder.objectMap)}")

        # 4. PDDL exportieren
        outputDir = Path(__file__).parent.parent / 'examples' / 'mps500' / 'pddl'
        domainFile, problemFile = builder.exportPddl(outputDir)

        assert domainFile.exists(), f"Domain-Datei nicht erstellt: {domainFile}"
        assert problemFile.exists(), f"Problem-Datei nicht erstellt: {problemFile}"

        print(f"[OK] PDDL exportiert:")
        print(f"    Domain:  {domainFile}")
        print(f"    Problem: {problemFile}")

        print("\n[SUCCESS] Alle Tests bestanden!")
        return True

    except Exception as e:
        print(f"\n[FAILED] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_mini_example():
    """Test mit Mini-Beispiel."""
    print("\n" + "=" * 80)
    print("TEST: Mini Example")
    print("=" * 80)

    examplesDir = Path(__file__).parent.parent / 'examples' / 'mini_example' / 'aasx'

    if not examplesDir.exists() or not list(examplesDir.glob("*.aasx")):
        print(f"[SKIP] Beispiel nicht gefunden: {examplesDir}")
        return True  # Skip ist OK

    try:
        loader = AASLoader(examplesDir, domainName='mini_test')
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

        outputDir = Path(__file__).parent.parent / 'examples' / 'mini_example' / 'pddl'
        builder.exportPddl(outputDir)

        print("[SUCCESS] Mini Example Test bestanden!")
        return True

    except Exception as e:
        print(f"[FAILED] {type(e).__name__}: {e}")
        return False


if __name__ == '__main__':
    success = True

    success = test_mps500() and success
    success = test_mini_example() and success

    print("\n" + "=" * 80)
    if success:
        print("ALLE TESTS BESTANDEN")
    else:
        print("EINIGE TESTS FEHLGESCHLAGEN")
    print("=" * 80)

    sys.exit(0 if success else 1)
