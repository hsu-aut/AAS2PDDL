"""
PDDL Builder - Convert extracted AAS data into UPF objects.

Uses the Unified Planning Framework (UPF) for:
- Type definitions (UserType)
- Predicates (Fluent)
- Actions (InstantaneousAction)
- Objects (Object)
- Problem definition (Problem)
"""

from pathlib import Path
from typing import Dict, List, Optional

from unified_planning.shortcuts import (
    UserType, BoolType, Fluent, InstantaneousAction, Object, Problem, Not
)
from unified_planning.io import PDDLWriter
from unified_planning.model.metrics import MinimizeSequentialPlanLength


class UPFProblemBuilder:
    """Convert extracted AAS data into UPF objects."""

    def __init__(self, domainName: str):
        """
        Args:
            domainName: Name of the PDDL domain
        """
        self.problem = Problem(domainName)
        self.typeMap: Dict[str, UserType] = {}
        self.fluentMap: Dict[str, Fluent] = {}
        self.objectMap: Dict[str, Object] = {}
        self._predicateParamOrder: Dict[str, List[str]] = {}

    def buildTypes(self, hierarchy: Dict[str, Optional[str]]):
        """Create UPF UserType objects from the type hierarchy.

        Args:
            hierarchy: Dict of {typeName: parentName}
        """
        print("=" * 80)
        print("[1] BUILD UPF TYPES (UserType)")
        print("=" * 80)

        processed = set()

        # "object" is implicit in PDDL, no UPF type needed
        if "object" in hierarchy:
            processed.add("object")

        # Iteratively create types whose parent has already been created
        changed = True
        while changed:
            changed = False
            for typeName, parentName in hierarchy.items():
                if typeName in processed:
                    continue

                if parentName is None or parentName == "object":
                    self.typeMap[typeName] = UserType(typeName)
                    processed.add(typeName)
                    print(f"  + {typeName} (root)")
                    changed = True
                elif parentName in self.typeMap:
                    self.typeMap[typeName] = UserType(typeName, father=self.typeMap[parentName])
                    processed.add(typeName)
                    print(f"  + {typeName} -> {parentName}")
                    changed = True

        print(f"\n[OK] {len(self.typeMap)} UPF types created\n")

    def buildFluents(self, predicateDefs: List[Dict]):
        """Create UPF Fluent objects from DataElementType definitions.

        Args:
            predicateDefs: List of {'name': str, 'params': [{'var': str, 'type': str}]}
        """
        print("=" * 80)
        print("[2] BUILD UPF FLUENTS (Fluent)")
        print("=" * 80)

        for pred in predicateDefs:
            predName = pred['name']
            params = {}
            paramOrder = []

            for p in pred['params']:
                cleanVar = p['var'].lstrip('?')
                if p['type'] not in self.typeMap:
                    raise KeyError(f"Type '{p['type']}' for fluent '{predName}' not found!")
                params[cleanVar] = self.typeMap[p['type']]
                paramOrder.append(cleanVar)

            fluent = Fluent(predName, BoolType(), **params)
            self.fluentMap[predName] = fluent
            self.problem.add_fluent(fluent, default_initial_value=False)
            self._predicateParamOrder[predName] = paramOrder

            paramsStr = ", ".join([f"{v}: {t}" for v, t in params.items()])
            print(f"  + {predName}({paramsStr})")

        print(f"\n[OK] {len(self.fluentMap)} UPF fluents created\n")

    def buildActions(self, operators: List[Dict]):
        """Create UPF InstantaneousAction objects from ProcessOperators.

        Args:
            operators: List of operator dicts
        """
        print("=" * 80)
        print("[3] BUILD UPF ACTIONS (InstantaneousAction)")
        print("=" * 80)

        for op in operators:
            self._buildAction(op)

        print(f"\n[OK] {len(self.problem.actions)} UPF actions created\n")

    def _buildAction(self, operator: Dict):
        """Create a single UPF action."""
        actionName = operator['name']

        actionParams = {}
        for p in operator['params']:
            cleanVar = p['var'].lstrip('?')
            if p['type'] not in self.typeMap:
                raise KeyError(f"Type '{p['type']}' for action '{actionName}' not found!")
            actionParams[cleanVar] = self.typeMap[p['type']]

        action = InstantaneousAction(actionName, **actionParams)

        # Map var -> UPF parameter object
        varToParam = {}
        for p in operator['params']:
            cleanVar = p['var'].lstrip('?')
            varToParam[cleanVar] = action.parameter(cleanVar)
            varToParam[f"?{cleanVar}"] = action.parameter(cleanVar)

        # Preconditions
        for cond in operator['preconditions']:
            fluent = self.fluentMap[cond['predicate']]
            fluentArgs = []
            for v in cond['paramRefs']:
                cleanV = v.lstrip('?')
                if cleanV in varToParam:
                    fluentArgs.append(varToParam[cleanV])
                elif v in varToParam:
                    fluentArgs.append(varToParam[v])
                else:
                    raise KeyError(f"Parameter '{v}' not found for action '{actionName}'")

            fluentCall = fluent(*fluentArgs)

            if cond['interpretationLogic'] == 'NotEqual':
                action.add_precondition(Not(fluentCall))
            else:
                action.add_precondition(fluentCall)

        # Effects
        for eff in operator['effects']:
            fluent = self.fluentMap[eff['predicate']]
            fluentArgs = []
            for v in eff['paramRefs']:
                cleanV = v.lstrip('?')
                if cleanV in varToParam:
                    fluentArgs.append(varToParam[cleanV])
                elif v in varToParam:
                    fluentArgs.append(varToParam[v])
                else:
                    raise KeyError(f"Parameter '{v}' not found for action '{actionName}'")

            fluentCall = fluent(*fluentArgs)

            if eff['interpretationLogic'] == 'NotEqual':
                action.add_effect(fluentCall, False)
            else:
                action.add_effect(fluentCall, True)

        self.problem.add_action(action)
        print(f"  + {actionName} ({len(operator['preconditions'])} pre, {len(operator['effects'])} eff)")

    def buildObjects(self, instances: List[Dict]):
        """Create UPF Object instances.

        Args:
            instances: List of {'name': str, 'type': str}
        """
        print("=" * 80)
        print("[4] BUILD UPF OBJECTS (Object)")
        print("=" * 80)

        for inst in instances:
            if inst['type'] not in self.typeMap:
                raise KeyError(f"Type '{inst['type']}' for instance '{inst['name']}' not found!")
            obj = Object(inst['name'], self.typeMap[inst['type']])
            self.objectMap[inst['name']] = obj
            self.problem.add_object(obj)
            print(f"  + {inst['name']} : {inst['type']}")

        print(f"\n[OK] {len(self.objectMap)} UPF objects created\n")

    def buildInit(self, initialStates: List[Dict]):
        """Set UPF initial values from extracted states.

        Args:
            initialStates: List of state dicts
        """
        print("=" * 80)
        print("[5] BUILD UPF INITIAL STATE (set_initial_value)")
        print("=" * 80)

        count = 0
        for state in initialStates:
            predName = state['predicate']
            if predName not in self.fluentMap:
                raise KeyError(f"Predicate '{predName}' not found in fluent map!")
            if predName not in self._predicateParamOrder:
                raise KeyError(f"Parameter order for '{predName}' unknown!")

            fluent = self.fluentMap[predName]
            paramOrder = self._predicateParamOrder[predName]

            args = []
            for var in paramOrder:
                if var not in state['bindings']:
                    raise ValueError(f"Parameter '{var}' missing in bindings for predicate '{predName}'!")
                objName = state['bindings'][var]
                if objName not in self.objectMap:
                    raise KeyError(f"Object '{objName}' not found in object map!")
                args.append(self.objectMap[objName])

            self.problem.set_initial_value(fluent(*args), True)
            argsStr = " ".join([a.name for a in args])
            print(f"  + ({predName} {argsStr})")
            count += 1

        print(f"\n[OK] {count} initial values set\n")

    def buildGoals(self, goals: List[Dict]):
        """Set UPF goals from extracted goal states.

        Args:
            goals: List of goal dicts
        """
        print("=" * 80)
        print("[6] BUILD UPF GOALS (add_goal)")
        print("=" * 80)

        count = 0
        for goal in goals:
            predName = goal['predicate']
            if predName not in self.fluentMap:
                raise KeyError(f"Predicate '{predName}' not found in fluent map!")

            fluent = self.fluentMap[predName]
            paramOrder = self._predicateParamOrder[predName]

            args = []
            for var in paramOrder:
                if var not in goal['bindings']:
                    raise ValueError(f"Parameter '{var}' missing in goal bindings for predicate '{predName}'!")
                objName = goal['bindings'][var]
                if objName not in self.objectMap:
                    raise KeyError(f"Object '{objName}' not found in object map!")
                args.append(self.objectMap[objName])

            self.problem.add_goal(fluent(*args))
            argsStr = " ".join([a.name for a in args])
            print(f"  + ({predName} {argsStr})")
            count += 1

        print(f"\n[OK] {count} goals set\n")

    def addPlanLengthMetric(self):
        """Add a sequential-plan-length objective.

        Without a quality metric an optimal planner cannot certify optimality,
        so UPF reports the result as satisficing. With it, "optimal" means the
        shortest plan (fewest sequential steps).
        """
        self.problem.add_quality_metric(MinimizeSequentialPlanLength())

    def exportPddl(self, outputDir: Path):
        """Export the UPF problem as PDDL files.

        Args:
            outputDir: Output directory
        """
        print("=" * 80)
        print("PDDL EXPORT (via UPF PDDLWriter)")
        print("=" * 80)

        outputDir.mkdir(exist_ok=True, parents=True)

        domainName = self.problem.name
        domainFile = outputDir / f"{domainName}_domain.pddl"
        problemFile = outputDir / f"{domainName}_problem.pddl"

        writer = PDDLWriter(self.problem, needs_requirements=True)
        writer.write_domain(str(domainFile))
        writer.write_problem(str(problemFile))

        print(f"  [OK] Domain:  {domainFile}")
        print(f"  [OK] Problem: {problemFile}")
        print()

        return domainFile, problemFile
