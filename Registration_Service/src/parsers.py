"""
AASX File Parser

Extracts AAS and submodel information from AASX packages.
"""

import xml.etree.ElementTree as ET
import zipfile
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class AASXParser:
    """Parser for AASX files"""

    def __init__(self, aasx_path: str):
        self.aasx_path = Path(aasx_path)
        self.namespaces = {
            'aas': 'https://admin-shell.io/aas/3/0',
            'IEC61360': 'https://admin-shell.io/IEC61360/3/0'
        }

    def parse(self) -> Dict[str, Any]:
        """Parse AASX file and extract AAS and submodel information"""
        try:
            with zipfile.ZipFile(self.aasx_path, 'r') as zip_file:
                # Find the main AAS XML file
                xml_files = [f for f in zip_file.namelist()
                             if f.endswith('.xml')]
                if not xml_files:
                    raise ValueError("No XML file found in AASX")

                main_xml = xml_files[0]  # Usually the first one
                logger.info(f"Parsing XML file: {main_xml}")

                with zip_file.open(main_xml) as xml_file:
                    tree = ET.parse(xml_file)
                    root = tree.getroot()

                    return self._extract_aas_data(root)

        except Exception as e:
            logger.error(f"Error parsing AASX file: {e}")
            raise

    def _extract_aas_data(self, root: ET.Element) -> Dict[str, Any]:
        """Extract AAS and submodel data from XML"""
        result = {
            'aas_shells': [],
            'submodels': [],
            'concept_descriptions': []
        }

        # Extract AAS shells
        for aas in root.findall('.//aas:assetAdministrationShell', self.namespaces):
            shell_data = self._extract_shell(aas)
            if shell_data:
                result['aas_shells'].append(shell_data)

        # Extract submodels
        for submodel in root.findall('.//aas:submodel', self.namespaces):
            submodel_data = self._extract_submodel(submodel)
            if submodel_data:
                result['submodels'].append(submodel_data)

        return result

    def _extract_shell(self, shell_elem: ET.Element) -> Dict[str, Any]:
        """Extract AAS shell information"""
        shell_id = self._get_text(shell_elem, './/aas:id', self.namespaces)
        id_short = self._get_text(
            shell_elem, './/aas:idShort', self.namespaces)

        # Extract submodel references
        submodel_refs = []
        for ref in shell_elem.findall('.//aas:submodel/aas:keys/aas:key', self.namespaces):
            ref_value = ref.get('value')
            if ref_value:
                submodel_refs.append(ref_value)

        return {
            'id': shell_id,
            'idShort': id_short or 'UnknownShell',
            'submodelReferences': submodel_refs,
            'assetInformation': {
                'assetKind': 'Instance'
            }
        }

    def _extract_submodel(self, submodel_elem: ET.Element) -> Optional[Dict[str, Any]]:
        """Extract submodel information"""
        submodel_id = self._get_text(
            submodel_elem, './/aas:id', self.namespaces)
        id_short = self._get_text(
            submodel_elem, './/aas:idShort', self.namespaces)

        # Skip if no ID found
        if not submodel_id:
            return None

        # Extract submodel elements (properties)
        elements = []
        for prop in submodel_elem.findall('.//aas:property', self.namespaces):
            prop_data = self._extract_property(prop)
            if prop_data:
                elements.append(prop_data)

        return {
            'id': submodel_id,
            'idShort': id_short or 'UnknownSubmodel',
            'submodelElements': elements
        }

    def _extract_property(self, prop_elem: ET.Element) -> Dict[str, Any]:
        """Extract property information"""
        id_short = self._get_text(prop_elem, './/aas:idShort', self.namespaces)
        value_type = self._get_text(
            prop_elem, './/aas:valueType', self.namespaces)
        value = self._get_text(prop_elem, './/aas:value', self.namespaces)

        return {
            'idShort': id_short,
            'modelType': 'Property',
            'valueType': value_type or 'xs:string',
            'value': value or ''
        }

    def _get_text(self, parent: ET.Element, xpath: str, namespaces: Dict[str, str]) -> Optional[str]:
        """Helper to safely extract text from XML element"""
        elem = parent.find(xpath, namespaces)
        return elem.text if elem is not None else None
