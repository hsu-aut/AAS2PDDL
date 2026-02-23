"""
AAS Extractor - Extract planning data from AAS submodels.

Standards:
- IDTA 02011: HierarchicalStructures (TypeHierarchy)
- VDI 3682: ProcessOperator (Capabilities)
- IEC 61360: DataElementType (DataElementTypes)
"""

from typing import Dict, List, Optional

from basyx.aas import model

try:
    from .aas_loader import AASLoader
    from .utils import derivePredicateNameFromIdShort
except ImportError:
    from aas_loader import AASLoader
    from utils import derivePredicateNameFromIdShort


class AASExtractor:
    """Extract planning data from AAS submodels into plain data structures."""

    def __init__(self, loader: AASLoader):
        self.loader = loader

    def extractTypeHierarchy(self) -> Dict[str, Optional[str]]:
        """Extract TypeHierarchy from AAS (IDTA 02011 HierarchicalStructures).

        Returns:
            Dict of {typeName: parentName} (None = root)
        """
        print("=" * 80)
        print("[1] EXTRACT TYPES (IDTA 02011 HierarchicalStructures)")
        print("=" * 80)

        hierarchy = {}

        def extractFromEntity(entity: model.Entity, parentName: str = None):
            typeName = entity.id_short
            hierarchy[typeName] = parentName
            for statement in entity.statement:
                if isinstance(statement, model.Entity):
                    extractFromEntity(statement, typeName)

        for sm in self.loader.getComponentSubmodels('TypeHierarchy'):
            for elem in sm.submodel_element:
                if isinstance(elem, model.Entity) and elem.id_short == "EntryNode":
                    for statement in elem.statement:
                        if isinstance(statement, model.Entity):
                            extractFromEntity(statement, None)
                    break

        print(f"  [OK] {len(hierarchy)} types extracted")
        for name, parent in hierarchy.items():
            if parent:
                print(f"    {name} -> {parent}")
            else:
                print(f"    {name} (root)")
        print()

        return hierarchy

    def extractDataElementTypes(self) -> List[Dict]:
        """Extract DataElementTypes from AAS (IEC 61360 DataElementType pattern).

        Returns:
            List of dicts: [{'name': str, 'params': [{'var': str, 'type': str}]}]
        """
        print("=" * 80)
        print("[2] EXTRACT PREDICATES (IEC 61360 DataElementTypes)")
        print("=" * 80)

        predicates = []

        for sm in self.loader.getComponentSubmodels('DataElementTypes'):
            for elem in sm.submodel_element:
                if isinstance(elem, model.SubmodelElementCollection):
                    pred = self._extractDataElementType(elem)
                    if pred and not any(p['name'] == pred['name'] for p in predicates):
                        predicates.append(pred)

        print(f"  [OK] {len(predicates)} predicates extracted")
        for p in predicates:
            paramsStr = ", ".join([f"{pr['var']}: {pr['type']}" for pr in p['params']])
            print(f"    {p['name']}({paramsStr})")
        print()

        return predicates

    def _extractDataElementType(self, elementSmec: model.SubmodelElementCollection) -> Optional[Dict]:
        """Extract a DataElementType from an SMC.

        PDDL name is derived from idShort (e.g. "DataElementType_On" -> "on").
        Parameter types are read ONLY from typeDefinitionRef (no redundant strings).
        """
        predName = derivePredicateNameFromIdShort(elementSmec.id_short)
        params = []

        for elem in elementSmec.value:
            if elem.id_short == 'parameters':
                for paramSmec in elem.value:
                    paramVar = None
                    paramType = None

                    for prop in paramSmec.value:
                        if prop.id_short == 'variable' and isinstance(prop, model.Property):
                            paramVar = prop.value.lstrip('?')
                        elif prop.id_short == 'typeDefinitionRef' and isinstance(prop, model.ReferenceElement):
                            paramType = self.loader.resolveTypeDefinitionRef(prop)

                    # Fallback: legacy format with string properties
                    if not paramVar or not paramType:
                        for prop in paramSmec.value:
                            if prop.id_short == 'Property' and isinstance(prop, model.Property):
                                paramVar = prop.value.lstrip('?')
                            elif prop.id_short == 'Type' and isinstance(prop, model.Property):
                                if not paramType:
                                    paramType = prop.value

                    if paramVar and paramType:
                        params.append({'var': paramVar, 'type': paramType})

        if predName:
            return {'name': predName, 'params': params}
        return None

    def extractProcessOperators(self) -> List[Dict]:
        """Extract Capabilities/ProcessOperators from AAS (VDI 3682).

        Returns:
            List of dicts with action definitions
        """
        print("=" * 80)
        print("[3] EXTRACT ACTIONS (VDI 3682 ProcessOperator)")
        print("=" * 80)

        operators = []

        for sm in self.loader.getComponentSubmodels('Capabilities'):
            for elem in sm.submodel_element:
                if isinstance(elem, model.SubmodelElementCollection):
                    op = self._extractOperator(elem)
                    if op:
                        operators.append(op)

        print(f"  [OK] {len(operators)} actions extracted")
        for op in operators:
            print(f"    {op['name']} ({len(op['preconditions'])} pre, {len(op['effects'])} eff)")
        print()

        return operators

    def _extractOperator(self, opSmec: model.SubmodelElementCollection) -> Optional[Dict]:
        """Extract a ProcessOperator from an SMC.

        IEC 61360 pattern:
        - expressionGoal == "Requirement" -> precondition
        - expressionGoal == "Assurance" -> effect
        """
        actionName = None
        paramDefs = []
        preconditions = []
        effects = []

        allConditionsSmecs = []

        for elem in opSmec.value:
            if elem.id_short == 'name' and isinstance(elem, model.Property):
                actionName = elem.value
            elif elem.id_short == 'Name' and isinstance(elem, model.Property):
                actionName = elem.value

            elif elem.id_short in ('processParameters', 'ProcessParameters'):
                for paramSmec in elem.value:
                    paramVar = None
                    paramType = None

                    for prop in paramSmec.value:
                        if prop.id_short == 'variable' and isinstance(prop, model.Property):
                            paramVar = prop.value.lstrip('?')
                        elif prop.id_short == 'typeDefinitionRef' and isinstance(prop, model.ReferenceElement):
                            paramType = self.loader.resolveTypeDefinitionRef(prop)

                    # Fallback: legacy format
                    if not paramVar or not paramType:
                        for prop in paramSmec.value:
                            if prop.id_short == 'Property' and isinstance(prop, model.Property):
                                paramVar = prop.value.lstrip('?')
                            elif prop.id_short == 'Type' and isinstance(prop, model.Property):
                                if not paramType:
                                    paramType = prop.value

                    if paramVar and paramType:
                        paramDefs.append({'var': paramVar, 'type': paramType})

            elif elem.id_short in ('hasInput', 'hasOutput'):
                for condSmec in elem.value:
                    allConditionsSmecs.append(condSmec)

        # Sort conditions by expressionGoal
        for condSmec in allConditionsSmecs:
            cond = self._extractCondition(condSmec)
            if cond:
                if cond['expressionGoal'] == 'Requirement':
                    preconditions.append(cond)
                elif cond['expressionGoal'] == 'Assurance':
                    effects.append(cond)

        if not actionName:
            return None

        return {
            'name': actionName,
            'params': paramDefs,
            'preconditions': preconditions,
            'effects': effects
        }

    def _extractCondition(self, condSmec: model.SubmodelElementCollection) -> Optional[Dict]:
        """Extract a condition from an InstanceDescription.

        IEC 61360 pattern:
        - dataElementTypeRef for predicate (reference only, no string)
        - expressionGoal (Requirement/Assurance)
        - interpretationLogic (Equal/NotEqual)
        """
        predicateName = None
        expressionGoal = None
        interpretationLogic = None
        paramBindings = []

        for elem in condSmec.value:
            if isinstance(elem, model.SubmodelElementCollection) and elem.id_short == 'InstanceDescription':
                for descElem in elem.value:
                    if descElem.id_short == 'dataElementTypeRef' and isinstance(descElem, model.ReferenceElement):
                        predicateName = self.loader.resolveDataElementTypeRef(descElem)
                    elif descElem.id_short == 'expressionGoal' and isinstance(descElem, model.Property):
                        expressionGoal = descElem.value
                    elif descElem.id_short == 'interpretationLogic' and isinstance(descElem, model.Property):
                        interpretationLogic = descElem.value
                    elif descElem.id_short == 'parameterBindingRefs':
                        for refElem in descElem.value:
                            if isinstance(refElem, model.ReferenceElement):
                                variable = self.loader.resolveParameterBindingRef(refElem)
                                if variable:
                                    paramBindings.append(variable)

        if not predicateName:
            return None

        return {
            'predicate': predicateName,
            'expressionGoal': expressionGoal,
            'interpretationLogic': interpretationLogic,
            'paramRefs': paramBindings
        }

    def extractInstances(self) -> List[Dict]:
        """Extract instances from AAS.

        Type is read ONLY from instanceTypeRef (no redundant strings).

        Returns:
            List of dicts: [{'name': str, 'type': str}]
        """
        print("=" * 80)
        print("[4] EXTRACT INSTANCES")
        print("=" * 80)

        instances = []

        for sm in self.loader.getComponentSubmodels('Instances'):
            for elem in sm.submodel_element:
                if isinstance(elem, model.SubmodelElementCollection):
                    instanceName = None
                    instanceType = None

                    for prop in elem.value:
                        if prop.id_short == 'instanceName' and isinstance(prop, model.Property):
                            instanceName = prop.value
                        elif prop.id_short == 'instanceTypeRef' and isinstance(prop, model.ReferenceElement):
                            instanceType = self.loader.resolveInstanceTypeRef(prop)

                    # Fallback: legacy format with string
                    if instanceName and not instanceType:
                        for prop in elem.value:
                            if prop.id_short == 'instanceType' and isinstance(prop, model.Property):
                                instanceType = prop.value

                    if instanceName and instanceType:
                        instances.append({'name': instanceName, 'type': instanceType})

        print(f"  [OK] {len(instances)} instances extracted")
        for inst in instances:
            print(f"    {inst['name']} : {inst['type']}")
        print()

        return instances

    def extractInitialStatesAndGoals(self):
        """Extract all states from AAS and sort by IEC 61360 expressionGoal.

        - expressionGoal == "ActualValue" -> initial state
        - expressionGoal == "Requirement" -> goal

        Returns:
            Tuple (initStates, goals)
        """
        print("=" * 80)
        print("[5] EXTRACT STATES (IEC 61360 ExpressionGoal)")
        print("=" * 80)

        initStates = []
        goals = []

        for sm in self.loader.getComponentSubmodels('Instances'):
            for instSmec in sm.submodel_element:
                if isinstance(instSmec, model.SubmodelElementCollection):
                    for elem in instSmec.value:
                        if isinstance(elem, model.SubmodelElementCollection) and elem.id_short in ('initialStates', 'InitialStates', 'goals', 'Goals'):
                            for stateSmec in elem.value:
                                state = self._extractState(stateSmec)
                                if state:
                                    if state['expressionGoal'] == 'ActualValue':
                                        initStates.append(state)
                                    elif state['expressionGoal'] == 'Requirement':
                                        goals.append(state)

        print(f"\n  Initial states (ActualValue): {len(initStates)}")
        for s in initStates:
            bindingsStr = ", ".join([f"{k}={v}" for k, v in s['bindings'].items()])
            print(f"    {s['predicate']}({bindingsStr})")

        print(f"\n  Goals (Requirement): {len(goals)}")
        for g in goals:
            bindingsStr = ", ".join([f"{k}={v}" for k, v in g['bindings'].items()])
            print(f"    {g['predicate']}({bindingsStr})")

        if not goals:
            print("  [WARNING] No goals found")

        print()
        return initStates, goals

    def _extractState(self, stateSmec: model.SubmodelElementCollection) -> Optional[Dict]:
        """Extract a state from an SMC.

        Predicate is read ONLY from dataElementTypeRef (no redundant strings).
        """
        predicateName = None
        expressionGoal = None
        paramBindings = {}

        for elem in stateSmec.value:
            if isinstance(elem, model.ReferenceElement) and elem.id_short == 'dataElementTypeRef':
                predicateName = self.loader.resolveDataElementTypeRef(elem)
            elif isinstance(elem, model.Property) and elem.id_short == 'expressionGoal':
                expressionGoal = elem.value
            elif isinstance(elem, model.SubmodelElementCollection) and elem.id_short == 'parameterBindings':
                for bindingSmec in elem.value:
                    param = None
                    value = None
                    for prop in bindingSmec.value:
                        if prop.id_short == 'parameter' and isinstance(prop, model.Property):
                            param = prop.value
                        elif prop.id_short == 'value' and isinstance(prop, model.Property):
                            value = prop.value
                    if param and value:
                        paramBindings[param] = value

        if not predicateName or not paramBindings:
            return None

        return {
            'predicate': predicateName,
            'expressionGoal': expressionGoal,
            'bindings': paramBindings
        }
