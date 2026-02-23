"""
AAS Loader - Load AASX files and resolve cross-AAS references.

Supports:
- Single AASX files
- Directories with multiple AASX files
- Reference resolution (dataElementTypeRef, typeDefinitionRef, parameterBindingRef)
"""

from pathlib import Path
from typing import Dict, List, Optional, Union

from basyx.aas import model
from basyx.aas.adapter.aasx import AASXReader, DictSupplementaryFileContainer

try:
    from .utils import sanitizePddlName, derivePredicateNameFromIdShort
except ImportError:
    from utils import sanitizePddlName, derivePredicateNameFromIdShort


class AASLoader:
    """Load AASX files and provide BaSyx access methods."""

    def __init__(self, inputPath: Union[Path, str], domainName: str = None):
        """
        Args:
            inputPath: Path to an AASX file or directory
            domainName: Optional domain name (overrides automatic derivation)
        """
        self.inputPath = Path(inputPath)
        self.objStore = model.DictObjectStore()
        self.allAas: List[model.AssetAdministrationShell] = []
        self.componentAasList: List[model.AssetAdministrationShell] = []
        self._explicitDomainName = domainName

        # Planning Configuration
        self.domainName: str = None
        self.problemName: str = None

    def load(self):
        """Load AASX file(s) - auto-detect file or directory."""
        if self.inputPath.is_dir():
            self._loadFromDirectory()
        else:
            self._loadSingleAasx(self.inputPath)

        self._filterComponentAas()
        self._extractPlanningConfiguration()

    def _loadSingleAasx(self, aasxPath: Path):
        """Load a single AASX file into the object store."""
        with AASXReader(str(aasxPath)) as reader:
            fileStore = DictSupplementaryFileContainer()
            reader.read_into(object_store=self.objStore, file_store=fileStore)

    def _loadFromDirectory(self):
        """Load all AASX files from a directory."""
        print("=" * 80)
        print("AASLoader - Loading AASX files from directory")
        print("=" * 80)
        print(f"Directory: {self.inputPath}")

        aasxFiles = list(self.inputPath.glob("*.aasx"))
        if not aasxFiles:
            raise FileNotFoundError(f"No AASX files found in: {self.inputPath}")

        print(f"Found: {len(aasxFiles)} AASX files")
        for aasxFile in aasxFiles:
            print(f"  Loading: {aasxFile.name}")
            self._loadSingleAasx(aasxFile)
        print()

    def _filterComponentAas(self):
        """Filter component AAS from all loaded AAS."""
        self.allAas = [obj for obj in self.objStore if isinstance(obj, model.AssetAdministrationShell)]

        for aas in self.allAas:
            if self._getAasRole(aas) == "component":
                self.componentAasList.append(aas)

        print(f"[OK] Loaded: {len(self.componentAasList)} component AAS (of {len(self.allAas)} total)")
        for aas in self.componentAasList:
            print(f"  - {aas.id_short}")
        print()

    def _getAasRole(self, aas: model.AssetAdministrationShell) -> str:
        """Determine the role of an AAS (system or component)."""
        for smRef in aas.submodel:
            sm = self.objStore.get(smRef.get_identifier())
            if sm and sm.id_short == 'TechnicalData':
                for elem in sm.submodel_element:
                    if elem.id_short == 'AASRole' and isinstance(elem, model.Property):
                        return elem.value

        if "System" in aas.id_short:
            return "system"
        return "component"

    def _extractPlanningConfiguration(self):
        """Extract planning configuration.

        Priority:
        1. Explicit domainName (CLI parameter)
        2. Directory/file name
        """
        print("=" * 80)
        print("[0] PLANNING CONFIGURATION")
        print("=" * 80)

        # Priority 1: Explicit domain name via CLI
        if self._explicitDomainName:
            self.domainName = sanitizePddlName(self._explicitDomainName)
            self.problemName = self.domainName
            print(f"  [OK] Domain name via CLI parameter: {self.domainName}")
            print()
            return

        # Priority 2: Derive domain name from directory or file name
        if self.inputPath.is_dir():
            derivedName = self.inputPath.name
        else:
            derivedName = self.inputPath.stem
        self.domainName = sanitizePddlName(derivedName)
        self.problemName = self.domainName
        print(f"  [INFO] Domain name derived: {self.domainName}")
        print()

    def getComponentSubmodels(self, submodelName: str) -> List[model.Submodel]:
        """Return all submodels with the given name from component AAS."""
        submodels = []
        for aas in self.componentAasList:
            for smRef in aas.submodel:
                sm = self.objStore.get(smRef.get_identifier())
                if sm and sm.id_short == submodelName:
                    submodels.append(sm)
        return submodels

    # =========================================================================
    # Reference resolution (references only, no redundant strings)
    # =========================================================================

    def resolveDataElementTypeRef(self, refElement: model.ReferenceElement) -> str:
        """Follow a dataElementTypeRef to the DataElementType definition.

        Derives the PDDL name from idShort (e.g. "DataElementType_On" -> "on").

        Args:
            refElement: The ReferenceElement containing the reference

        Returns:
            The PDDL predicate name
        """
        if not refElement.value or not refElement.value.key:
            raise ValueError("ReferenceElement has no keys!")

        keys = refElement.value.key
        if len(keys) < 2:
            raise ValueError(f"dataElementTypeRef has invalid structure: {len(keys)} keys (expected: >=2)")

        submodelId = keys[0].value
        elementIdShort = keys[1].value

        dataElementSubmodel = self.objStore.get(submodelId)
        if not dataElementSubmodel:
            raise KeyError(f"DataElementTypes submodel not found: {submodelId}")

        # Find the DataElementType element
        dataElement = None
        for elem in dataElementSubmodel.submodel_element:
            if elem.id_short == elementIdShort:
                dataElement = elem
                break

        if not dataElement:
            raise KeyError(f"DataElementType '{elementIdShort}' not found in {dataElementSubmodel.id_short}")

        # Derive PDDL name from idShort (NOT from redundant string property)
        return derivePredicateNameFromIdShort(elementIdShort)

    def _findSubmodelById(self, submodelId: str) -> Optional[model.Submodel]:
        """Find a submodel in the object store.

        Tries multiple strategies:
        1. Exact ID match
        2. URL path match (ignores domain differences like example.com vs festo.com)
        """
        # Exact match
        sm = self.objStore.get(submodelId)
        if sm:
            return sm

        # Extract URL path (everything after the domain)
        # e.g. "https://mps500.example.com/aas/processingstation/submodels/TypeDescription"
        #   -> "/aas/processingstation/submodels/TypeDescription"
        def extractUrlPath(url: str) -> str:
            if '://' in url:
                parts = url.split('/', 3)
                if len(parts) > 3:
                    return '/' + parts[3]
            return url

        searchPath = extractUrlPath(submodelId)

        for obj in self.objStore:
            if isinstance(obj, model.Submodel):
                objPath = extractUrlPath(obj.id)
                if objPath == searchPath:
                    return obj

        return None

    def resolveTypeDefinitionRef(self, refElement: model.ReferenceElement) -> str:
        """Follow a typeDefinitionRef to the TypeDescription or TypeHierarchy.

        Args:
            refElement: The ReferenceElement containing the reference

        Returns:
            The type name
        """
        if not refElement.value or not refElement.value.key:
            raise ValueError("ReferenceElement has no keys!")

        keys = refElement.value.key
        submodelId = keys[0].value

        # Check if it points directly to TypeHierarchy (legacy format)
        if 'TypeHierarchy' in submodelId or (len(keys) > 1 and 'TypeHierarchy' in str(keys)):
            return sanitizePddlName(keys[-1].value)

        typeDescSubmodel = self._findSubmodelById(submodelId)
        if not typeDescSubmodel:
            # Fallback: extract type name directly from reference URL
            idParts = submodelId.split('/')
            for part in reversed(idParts):
                if part and part.lower() not in ('typedescription', 'submodels', 'aas', 'sm'):
                    return sanitizePddlName(part)
            raise KeyError(f"TypeDescription submodel not found: {submodelId}")

        # Method 1: Follow typeHierarchyRef
        for elem in typeDescSubmodel.submodel_element:
            if elem.id_short == 'typeHierarchyRef' and isinstance(elem, model.ReferenceElement):
                return self.resolveTypeHierarchyRef(elem)

        # Method 2: typeName property (legacy)
        for elem in typeDescSubmodel.submodel_element:
            if elem.id_short in ('typeName', 'TypeName') and isinstance(elem, model.Property):
                return sanitizePddlName(elem.value)

        # Method 3: Derive from submodel idShort (e.g. "CarrierTypeDescription" -> "carrier")
        idShort = typeDescSubmodel.id_short
        if idShort.endswith('TypeDescription'):
            derivedName = idShort[:-len('TypeDescription')]
            return sanitizePddlName(derivedName)
        if idShort == 'TypeDescription':
            smIdParts = submodelId.split('/')
            for part in reversed(smIdParts):
                if part and part not in ('TypeDescription', 'aas', 'sm', 'submodels'):
                    return sanitizePddlName(part)

        # Last resort: idShort directly
        return sanitizePddlName(idShort)

    def resolveTypeHierarchyRef(self, refElement: model.ReferenceElement) -> str:
        """Follow a typeHierarchyRef and extract the type name.

        The type name is the last key in the reference (Entity in TypeHierarchy).

        Args:
            refElement: The ReferenceElement containing the reference

        Returns:
            The type name
        """
        if not refElement.value or not refElement.value.key:
            raise ValueError("ReferenceElement has no keys!")

        keys = refElement.value.key
        return keys[-1].value

    def resolveParameterBindingRef(self, refElement: model.ReferenceElement) -> str:
        """Follow a parameterBindingRef to the ProcessParameter definition.

        Args:
            refElement: The ReferenceElement containing the reference

        Returns:
            The variable (e.g. "c" for ?c)
        """
        if not refElement.value or not refElement.value.key:
            raise ValueError("ReferenceElement has no keys!")

        keys = refElement.value.key

        # Short references (e.g. only 2-3 keys): derive variable from last key
        if len(keys) < 4:
            paramId = keys[-1].value
            return self._extractVarFromParamId(paramId)

        submodelId = keys[0].value
        processOpId = keys[1].value
        paramId = keys[3].value if len(keys) > 3 else keys[-1].value

        capabilitiesSm = self._findSubmodelById(submodelId)
        if not capabilitiesSm:
            return self._extractVarFromParamId(paramId)

        processOperator = None
        for elem in capabilitiesSm.submodel_element:
            if elem.id_short == processOpId:
                processOperator = elem
                break

        if not processOperator:
            return self._extractVarFromParamId(paramId)

        processParams = None
        for elem in processOperator.value:
            if elem.id_short in ('processParameters', 'ProcessParameters'):
                processParams = elem
                break

        if not processParams:
            return self._extractVarFromParamId(paramId)

        # Find the parameter and read the variable
        for paramSmec in processParams.value:
            if paramSmec.id_short == paramId:
                for prop in paramSmec.value:
                    if prop.id_short == 'variable' and isinstance(prop, model.Property):
                        return prop.value.lstrip('?')
                return self._extractVarFromParamId(paramId)

        return self._extractVarFromParamId(paramId)

    def _extractVarFromParamId(self, paramId: str) -> str:
        """Extract the variable from a parameter idShort.

        Examples:
        - "Parameter_c" -> "c"
        - "parameter_cb1" -> "cb1"
        - "c" -> "c"
        """
        prefixes = ['Parameter_', 'parameter_', 'param_', 'Param_']
        for prefix in prefixes:
            if paramId.startswith(prefix):
                return paramId[len(prefix):]
        return paramId

    def resolveInstanceTypeRef(self, refElement: model.ReferenceElement) -> str:
        """Follow an instanceTypeRef to the TypeDescription.

        Args:
            refElement: The ReferenceElement containing the reference

        Returns:
            The type name
        """
        return self.resolveTypeDefinitionRef(refElement)
