"""
simple script to transform an Excel file to a yaml library for CISO assistant
Usage: python convert_library [--compat] your_excel_file

The compat flag is recommended only to maintain libraries that have been generated prior or up to release 1.9.20.
Without the compat flag, URNs generated for nodes without ref_id are constructed using the parent_urn.
This generated urns that are much simpler to understand and maintain if required.

Conventions:
    | means a cell separation, <> means empty cell
    The first tab shall be named "library_content" and contain the description of the library in the other tabs
        library_urn                     | <urn>
        library_version                 | <version>
        library_publication_date        | <date>   (default value: now)
        library_locale                  | <en/fr/...>
        library_ref_id                  | <ref_id>
        library_name                    | <name>
        library_description             | <description>
        library_copyright               | <copyright>
        library_provider                | <provider>
        library_packager                | <packager>
        library_dependencies            | <urn1, urn2...
        framework_urn                   | <urn>
        framework_ref_id                | <ref_id>
        framework_name                  | <name>
        framework_description           | <description>
        framework_min_score             | <min_score>
        framework_max_score             | <max_score>
        reference_control_base_urn      | <base_urn> | id
        threat_base_urn                 | <base_urn> | id
        risk_matrix_urn                 | <urn>
        risk_matrix_ref_id              | <ref_id>
        risk_matrix_name                | <name>
        risk_matrix_description         | <description>
        mapping_urn                     | <urn>
        mapping_ref_id                  | <ref_id>
        mapping_name                    | <name>
        mapping_description             | <description>
        mapping_source_framework_urn    | <urn>
        mapping_target_framework_urn    | <urn>
        mapping_source_node_base_urn    | <urn>
        mapping_target_node_base_urn    | <urn>
        tab                             | <tab_name> | requirements
        tab                             | <tab_name> | threats            | <base_urn>
        tab                             | <tab_name> | reference_controls | <base_urn>
        tab                             | <tab_name> | scores
        tab                             | <tab_name> | implementation_groups
        tab                             | <tab_name> | risk_matrix
        tab                             | <tab_name> | mappings
        tab                             | <tab_name> | answers

        variables can also have a translation in the form "variable[locale]"

    For requirements:
        If no section_name is given, no upper group is defined, else an upper group (depth 0) with the section name is used.
        The first line is a header, with the following possible fields (* for required):
            - assessable(*): non-empty (e.g x) if this is a requirement
            - depth(*): 1/2/3/... to describe the tree
            - ref_id
            - name
            - description
            - implementation_groups
            - threats
            - reference_controls
            - annotation
            - typical_evidence
            - questions
            - answer
            - skip_count: trick for fixing a referential without changing the urns (advanced users)
        The normal tree order shall be respected
        If multiple threats or reference_control are given for a requirements, they shall be separated by blank or comma.
        They shall be prefixed by the id of the corresponding base_urn and a semicolumn.
        Scores tab shall contain score, name and description column. Optionally, description_doc can be given.
    For reference controls:
        The first line is a header, with the following possible fields (* for required):
            - ref_id(*)
            - name
            - description
            - category (policy/process/technical/physical).
            - csf_function (govern/identify/protect/detect/respond/recover).
            - annotation
    For risk matrices:
        The first line is a header, with the following mandatory fields:
            - type: probability/impact/risk.
            - id: a number from 0 to n-1 (depending of the number of objects for a given type)
            - color: empty cells with the desired color. Can be left with no fill.
            - abbreviation: the abbreviation for the object
            - name: name of the object
            - description: description of the object
            - grid: several columns describing the matrix with colors. The colors shall be consistent with the color column.
        The grid shall be aligned with the probability objects, the columns being the impact in order of id, and the content of each cell being the id of the risk.
        This is a topological representation. The display on the screen (transposition, direction of axes) will be managed in the frontend, not in the data model.
    For mappings:
        The first line is a header, with the following possible fields (* for required):
            - source_node_id(*)
            - target_node_id(*)
            - relationship(*)
            - rationale
            - strength_of_relationship
    For Answers:
        The first line is a header, with the following possible fields (* for required):
            - id(*)
            - type(*)
            - choices(*)
    A library has a single locale, which is the reference language. Translations are given in columns with header like "name[fr]"
    Dependencies are given as a comma or blank separated list of urns.
"""

import openpyxl
import argparse
import re
import yaml
from pprint import pprint
from collections import defaultdict
import datetime

LIBRARY_VARS = (
    "library_urn",
    "library_version",
    "library_publication_date",
    "library_locale",
    "library_ref_id",
    "library_name",
    "library_description",
    "framework_urn",
    "framework_ref_id",
    "framework_name",
    "framework_description",
    "framework_min_score",
    "framework_max_score",
    "library_copyright",
    "library_provider",
    "library_packager",
    "reference_control_base_urn",
    "threat_base_urn",
    "library_dependencies",
    "risk_matrix_urn",
    "risk_matrix_ref_id",
    "risk_matrix_name",
    "risk_matrix_description",
    "mapping_urn",
    "mapping_ref_id",
    "mapping_name",
    "mapping_description",
    "mapping_source_framework_urn",
    "mapping_target_framework_urn",
    "mapping_source_node_base_urn",
    "mapping_target_node_base_urn",
    "tab",
)
library_vars = {}
library_vars_dict = defaultdict(dict)
library_vars_dict_reverse = defaultdict(dict)
library_vars_dict_arg = defaultdict(dict)
urn_unicity_checker = set()

parser = argparse.ArgumentParser(
    prog="convert-library.py",
    description="convert an Excel file in a library for CISO Assistant",
)
parser.add_argument("input_file_name")
parser.add_argument("--compat", action="store_true")
args = parser.parse_args()

ref_name = re.sub(r"\.\w+$", "", args.input_file_name).lower()
output_file_name = ref_name + ".yaml"

print("parsing", args.input_file_name)

# Define variable to load the dataframe
dataframe = openpyxl.load_workbook(args.input_file_name)

requirement_nodes = []
reference_controls = []
threat_definitions = []
scores_definition = []
implementation_groups_definition = []
questions = []
risk_matrix = {}
requirement_mappings = []

def error(message):
    print("Error:", message)
    exit(1)

def read_header(row):
    """
    read header
    use a trick for "grid" columns, to store all of them: rename second one as "grid1", third as "grid2", etc.
    """
    i = 0
    header = {}
    grid_count = 0
    for v in row:
        v = str(v.value).lower()
        if v == "grid":
            v = f"{v}{grid_count}"
            grid_count += 1
        header[v] = i
        i += 1
    return header

def get_translations(header, row):
    """read available translations"""
    result = {}
    for i, h in enumerate(header):
        if q := re.match(r"(\w+)\[(\w+)\]", h):
            v = q.group(1)
            lang = q.group(2)
            if lang not in result:
                result[lang] = {}
            result[lang][v] = row[i].value
    return result

def get_translations_content(library_vars, prefix):
    """read available translations in library_vars"""
    result = {}
    for k, v in library_vars.items():
        k2 = k
        if q := re.match(prefix + r"_(\w+)\[(\w+)\]", k):
            k2 = q.group(1)
            lang = q.group(2)
            if lang not in result:
                result[lang] = {}
            result[lang][k2] = v
    return result

# https://gist.github.com/Mike-Honey/b36e651e9a7f1d2e1d60ce1c63b9b633
from colorsys import rgb_to_hls, hls_to_rgb

RGBMAX = 0xFF  # Corresponds to 255
HLSMAX = 240  # MS excel's tint function expects that HLS is base 240. see:
# https://social.msdn.microsoft.com/Forums/en-US/e9d8c136-6d62-4098-9b1b-dac786149f43/excel-color-tint-algorithm-incorrect?forum=os_binaryfile#d3c2ac95-52e0-476b-86f1-e2a697f24969

def rgb_to_ms_hls(red, green=None, blue=None):
    """Converts rgb values in range (0,1) or a hex string of the form '[#aa]rrggbb' to HLSMAX based HLS, (alpha values are ignored)"""
    if green is None:
        if isinstance(red, str):
            if len(red) > 6:
                red = red[-6:]  # Ignore preceding '#' and alpha values
            blue = int(red[4:], 16) / RGBMAX
            green = int(red[2:4], 16) / RGBMAX
            red = int(red[0:2], 16) / RGBMAX
        else:
            red, green, blue = red
    h, l, s = rgb_to_hls(red, green, blue)
    return (int(round(h * HLSMAX)), int(round(l * HLSMAX)), int(round(s * HLSMAX)))

def ms_hls_to_rgb(hue, lightness=None, saturation=None):
    """Converts HLSMAX based HLS values to rgb values in the range (0,1)"""
    if lightness is None:
        hue, lightness, saturation = hue
    return hls_to_rgb(hue / HLSMAX, lightness / HLSMAX, saturation / HLSMAX)

def rgb_to_hex(red, green=None, blue=None):
    """Converts (0,1) based RGB values to a hex string 'rrggbb'"""
    if green is None:
        red, green, blue = red
    return (
        "%02x%02x%02x"
        % (
            int(round(red * RGBMAX)),
            int(round(green * RGBMAX)),
            int(round(blue * RGBMAX)),
        )
    ).upper()

def get_theme_colors(wb):
    """Gets theme colors from the workbook"""
    # see: https://groups.google.com/forum/#!topic/openpyxl-users/I0k3TfqNLrc
    from openpyxl.xml.functions import QName, fromstring

    xlmns = "http://schemas.openxmlformats.org/drawingml/2006/main"
    root = fromstring(wb.loaded_theme)
    themeEl = root.find(QName(xlmns, "themeElements").text)
    colorSchemes = themeEl.findall(QName(xlmns, "clrScheme").text)
    firstColorScheme = colorSchemes[0]

    colors = []

    for c in [
        "lt1",
        "dk1",
        "lt2",
        "dk2",
        "accent1",
        "accent2",
        "accent3",
        "accent4",
        "accent5",
        "accent6",
    ]:
        accent = firstColorScheme.find(QName(xlmns, c).text)
        for i in list(accent):  # walk all child nodes, rather than assuming [0]
            if "window" in i.attrib["val"]:
                colors.append(i.attrib["lastClr"])
            else:
                colors.append(i.attrib["val"])

    return colors

def tint_luminance(tint, lum):
    """Tints a HLSMAX based luminance"""
    # See: http://ciintelligence.blogspot.co.uk/2012/02/converting-excel-theme-color-and-tint.html
    if tint < 0:
        return int(round(lum * (1.0 + tint)))
    else:
        return int(round(lum * (1.0 - tint) + (HLSMAX - HLSMAX * (1.0 - tint))))

def theme_and_tint_to_rgb(wb, theme, tint):
    """Given a workbook, a theme number and a tint return a hex based rgb"""
    rgb = get_theme_colors(wb)[theme]
    h, l, s = rgb_to_ms_hls(rgb)
    return rgb_to_hex(ms_hls_to_rgb(h, tint_luminance(tint, l), s))

def get_color(wb, cell):
    """get cell color; None for no fill"""
    if not cell.fill.patternType:
        return None
    if isinstance(cell.fill.fgColor.rgb, str):
        return "#" + cell.fill.fgColor.rgb[2:]
    theme = cell.fill.start_color.theme
    tint = cell.fill.start_color.tint
    color = theme_and_tint_to_rgb(wb, theme, tint)
    return "#" + color

def build_reference_control_ids_set():
    """
    Builds a set of all reference control IDs from the reference_controls tab.
    This will be used to validate references to controls in the requirements tab.
    """
    control_ids = set()

    # Find the reference_controls tab name
    ref_control_tab = None
    for tab_name, tab_type in library_vars_dict["tab"].items():
        if tab_type == "reference_controls":
            ref_control_tab = tab_name
            break

    if not ref_control_tab:
        print(
            "WARNING: No reference_controls tab found. Cannot validate control references."
        )
        return control_ids

    # Process the reference_controls tab to extract all IDs
    is_header = True
    for row in dataframe[ref_control_tab]:
        if is_header:
            header = read_header(row)
            is_header = False
            if "ref_id" not in header:
                print("WARNING: No ref_id column found in reference_controls tab.")
                return control_ids
        elif any(c.value for c in row):
            ref_id = (
                str(row[header["ref_id"]].value).strip()
                if row[header["ref_id"]].value
                else None
            )
            if ref_id:
                control_ids.add(ref_id.lower())

    return control_ids


def validate_control_references(requirement_nodes, control_ids_set):
    """
    Validate that all referenced controls in requirements exist in the control set.

    Args:
        requirement_nodes: List of processed requirement nodes
        control_ids_set: Set of valid reference control IDs
    """
    missing_controls = set()
    for node in requirement_nodes:
        if "reference_controls" in node:
            for control_urn in node["reference_controls"]:
                # Extract the ID part from the URN
                # Format is typically like "urn:base_urn:control_id"
                control_id = control_urn.split(":")[-1]

                if control_id not in control_ids_set:
                    missing_controls.add(control_id)
                    print(
                        f"WARNING: Reference control '{control_id}' referenced in requirement '{node.get('ref_id', node['urn'])}' does not exist."
                    )

    if missing_controls:
        print(
            f"\nFound {len(missing_controls)} missing controls: {', '.join(missing_controls)}"
        )
        print("Please fix these references before uploading your file.")
    else:
        print("All reference control references are valid.")


def get_answers(tab):
    print("processing answers")
    found_answers = {}
    is_header = True
    for row in tab:
        if is_header:
            header = read_header(row)
            is_header = False
            assert "id" in header
        if any(c.value for c in row):
            row_id = (
                str(row[header["id"]].value).strip()
                if row[header["id"]].value
                else None
            )
            type = (
                row[header.get("question_type")].value
                if "question_type" in header
                else None
            )
            choices_lines = (
                (
                    row[header["question_choices"]].value.split("\n")
                    if row[header["question_choices"]].value
                    else []
                )
                if "question_choices" in header
                    else None
                )
            choices = []
            for line in choices_lines:
                if line.startswith("|"):
                    choices[-1]["value"] += "\n" + line[1:]
                else:
                    choices.append({"urn": "", "value": line.strip()})
            found_answers[row_id] = {
                "type": type,
                "choices": choices,
            }

    return found_answers

################################################################
def build_ids_set(tab_name):
    output = set()
    raw = dataframe[tab_name]["A"]
    output = {cell.value for cell in raw if cell.value is not None}
    return output

for tab in dataframe:
    print("parsing tab", tab.title)
    title = tab.title
    try:
        answers = get_answers(dataframe["answers"])
    except KeyError:
        answers = {}
    if title.lower() == "library_content":
        print("processing library content")
        for row in tab:
            if any([r.value for r in row]):
                (v1, v2, v3) = (r.value for r in row[0:3])
                v4 = row[3].value if len(row) > 3 else None
                v1b = v1
                if q := re.match(r"(\w+)\[(\w+)\]", v1):
                    v1b = q.group(1)
                    lang = q.group(2)
                if v1b in LIBRARY_VARS:
                    library_vars[v1] = v2
                    library_vars_dict[v1][str(v2)] = v3
                    library_vars_dict_reverse[v1][str(v3)] = v2
                    library_vars_dict_arg[v1][v2] = v4
    elif title not in library_vars_dict["tab"]:
        print(f"Ignored tab: {title}")
    elif library_vars_dict["tab"][title] == "requirements":
        print("processing requirements")
        root_nodes_urn = re.sub("framework", "req_node", library_vars["framework_urn"])
        current_node_urn = None
        current_depth = 0
        parent_urn = None
        parent_for_depth = {}
        count_for_depth = {}
        section = library_vars_dict_arg["tab"][title]
        if section:
            section_id = section.lower().replace(" ", "-")
            current_node_urn = f"{root_nodes_urn}:{section_id}"
            parent_for_depth[1] = current_node_urn
            count_for_depth[1] = 1
            requirement_nodes.append(
                {"urn": current_node_urn, "name": section, "assessable": False}
            )
        is_header = True
        counter = 0
        counter_fix = 0
        for row in tab:
            counter += 1
            if is_header:
                header = read_header(row)
                is_header = False
                assert "assessable" in header
                assert "depth" in header
                assert "ref_id" in header
            elif any([c.value for c in row]):
                assessable = bool(row[header["assessable"]].value)
                depth = row[header["depth"]].value
                ref_id = (
                    str(row[header["ref_id"]].value).strip()
                    if row[header["ref_id"]].value
                    else None
                )
                name = row[header["name"]].value if "name" in header else None
                if name and len(name) >= 200:
                    print("Name too long:", ref_id, name)
                    exit(1)
                description = (
                    row[header["description"]].value
                    if "description" in header
                    else None
                )
                annotation = (
                    row[header["annotation"]].value if "annotation" in header else None
                )
                typical_evidence = (
                    row[header["typical_evidence"]].value
                    if "typical_evidence" in header
                    else None
                )
                implementation_groups = (
                    row[header["implementation_groups"]].value
                    if "implementation_groups" in header
                    else None
                )
                translations = get_translations(header, row)
                if depth == current_depth + 1:
                    parent_for_depth[depth] = current_node_urn
                    count_for_depth[depth] = 1
                    parent_urn = parent_for_depth[depth]
                elif depth <= current_depth:
                    pass
                else:
                    error(f"wrong depth in requirement (tab {title}) {urn}")
                if args.compat:
                    skip_count = "skip_count" in header and bool(
                        row[header["skip_count"]].value
                    )
                    if skip_count:
                        counter_fix += 1
                        ref_id_urn = f"node{counter - counter_fix}-{counter_fix}"
                    else:
                        ref_id_urn = (
                            ref_id.lower().replace(" ", "-")
                            if ref_id
                            else f"node{counter - counter_fix}"
                        )
                    urn = f"{root_nodes_urn}:{ref_id_urn}"
                else:
                    if ref_id:
                        urn = f"{root_nodes_urn}:{ref_id.lower().replace(' ', '-')}"
                    else:
                        p = parent_for_depth[depth]
                        c = count_for_depth[depth]
                        urn = f"{p}:{c}" if p else f"{root_nodes_urn}:node{c}"
                        count_for_depth[depth] += 1
                if urn in urn_unicity_checker:
                    print("URN duplicate:", urn)
                    exit(1)
                urn_unicity_checker.add(urn)
                assert isinstance(depth, int), f"incorrect depth for {row}"
                current_node_urn = urn
                parent_urn = parent_for_depth[depth]
                current_depth = depth
                req_node = {"urn": urn, "assessable": assessable, "depth": depth}
                if parent_urn:
                    req_node["parent_urn"] = parent_urn
                if ref_id:
                    req_node["ref_id"] = ref_id
                if name:
                    req_node["name"] = name
                if description:
                    req_node["description"] = description
                if annotation:
                    req_node["annotation"] = annotation
                if typical_evidence:
                    req_node["typical_evidence"] = typical_evidence
                if implementation_groups:
                    req_node["implementation_groups"] = implementation_groups.split(",")
                threats = row[header["threats"]].value if "threats" in header else None
                req_reference_controls = (
                    row[header["reference_controls"]].value
                    if "reference_controls" in header
                    else None
                )
                questions_lines = (
                    (
                        row[header["questions"]].value.split("\n")
                        if row[header["questions"]].value
                        else []
                    )
                    if "questions" in header
                    else []
                )
                questions = []
                for line in questions_lines:
                    if line.startswith("|"):
                        questions[-1] += "\n" + line[1:]
                    else:
                        questions.append(line)
                answer = (
                    (
                        row[header["answer"]].value.split("\n")
                        if row[header["answer"]].value
                        else []
                    )
                    if "answer" in header
                    else []
                )
                if len(answer) != 1 and len(answer) != len(questions):
                    print("error: answer and questions mismatch on requirement", urn)
                    print("hint: please check at least one answer is defined for all questions or each question has an answer")
                    exit(1)
                threat_urns = []
                function_urns = []
                if threats:
                    for element in re.split(r"[\s,]+", threats):
                        parts = re.split(r":", element)
                        prefix = parts.pop(0)
                        part_name = ":".join(parts)
                        part_name = part_name.lower().replace(" ", "-")
                        urn_prefix = library_vars_dict_reverse["threat_base_urn"][
                            prefix
                        ]
                        threat_urns.append(f"{urn_prefix}:{part_name}")
                if req_reference_controls:
                    for element in re.split(r"[\s,]+", req_reference_controls):
                        parts = re.split(r":", element)
                        prefix = parts.pop(0)
                        part_name = ":".join(parts).lower()
                        urn_prefix = library_vars_dict_reverse[
                            "reference_control_base_urn"
                        ][prefix]
                        function_urns.append(f"{urn_prefix}:{part_name}")
                if answer and questions:
                    req_node["questions"] = {
                        f"{req_node['urn']}:question:{i + 1}": {
                            "type": answers[answer[i]]["type"] if len(answer) > 1 else answers[answer[0]]["type"],
                            "choices": [
                                {
                                    "urn": f"{req_node['urn']}:question:{i + 1}:choice:{j + 1}",
                                    "value": choice["value"]
                                }
                                for j, choice in enumerate(answers[answer[i] or answer[0]]["choices"] if len(answer) > 1 else answers[answer[0]]["choices"])
                            ],
                            "text": question,
                        }
                        for i, question in enumerate(questions)
                    }
                if threat_urns:
                    req_node["threats"] = threat_urns
                if function_urns:
                    req_node["reference_controls"] = function_urns
                if translations:
                    req_node["translations"] = translations
                requirement_nodes.append(req_node)
            else:
                pass
                # print("empty row")
    elif library_vars_dict["tab"][title] == "reference_controls":
        print("processing reference controls")
        current_function = {}
        is_header = True
        reference_control_base_urn = library_vars["reference_control_base_urn"]
        for row in tab:
            if is_header:
                header = read_header(row)
                is_header = False
                assert "ref_id" in header
            elif any([c.value for c in row]):
                ref_id = (
                    str(row[header["ref_id"]].value).strip()
                    if row[header["ref_id"]].value
                    else None
                )
                name = row[header["name"]].value if "name" in header else None
                description = (
                    row[header["description"]].value
                    if "description" in header
                    else None
                )
                category = (
                    row[header["category"]].value if "category" in header else None
                )
                csf_function = (
                    row[header["csf_function"]].value
                    if "csf_function" in header
                    else None
                )
                annotation = (
                    row[header["annotation"]].value if "annotation" in header else None
                )
                translations = get_translations(header, row)
                ref_id_urn = ref_id.lower().replace(" ", "-")
                current_function = {}
                current_function["urn"] = f"{reference_control_base_urn}:{ref_id_urn}"
                current_function["ref_id"] = ref_id
                if name:
                    current_function["name"] = name
                if category:
                    current_function["category"] = category
                if csf_function:
                    current_function["csf_function"] = csf_function
                if description:
                    current_function["description"] = description
                if annotation:
                    current_function["annotation"] = annotation
                if translations:
                    current_function["translations"] = translations
                reference_controls.append(current_function)
    elif library_vars_dict["tab"][title] == "threats":
        print("processing threats")
        current_threat = {}
        is_header = True
        threat_base_urn = library_vars["threat_base_urn"]
        for row in tab:
            if is_header:
                header = read_header(row)
                print(header)
                is_header = False
                assert "ref_id" in header
            elif any([c.value for c in row]):
                ref_id = (
                    str(row[header["ref_id"]].value).strip()
                    if row[header["ref_id"]].value
                    else None
                )
                name = row[header["name"]].value if "name" in header else None
                description = (
                    row[header["description"]].value
                    if "description" in header
                    else None
                )
                annotation = (
                    row[header["annotation"]].value if "annotation" in header else None
                )
                translations = get_translations(header, row)
                ref_id_urn = ref_id.lower().replace(" ", "-")
                current_threat = {}
                current_threat["urn"] = f"{threat_base_urn}:{ref_id_urn}"
                current_threat["ref_id"] = ref_id
                if name:
                    current_threat["name"] = name
                if description:
                    current_threat["description"] = description
                if annotation:
                    current_threat["annotation"] = annotation
                if translations:
                    current_threat["translations"] = translations
                threat_definitions.append(current_threat)
    elif library_vars_dict["tab"][title] == "scores":
        print("processing scores")
        is_header = True
        for row in tab:
            if is_header:
                header = read_header(row)
                is_header = False
                assert "score" in header
                assert "name" in header
                assert "description" in header
            elif any([c.value for c in row]):
                score = row[header["score"]].value
                name = row[header["name"]].value
                description = row[header["description"]].value
                description_doc = (
                    row[header["description_doc"]].value
                    if "description_doc" in header
                    else None
                )
                translations = get_translations(header, row)
                current_score = {
                    "score": score,
                    "name": name,
                    "description": description,
                }
                if description_doc:
                    current_score["description_doc"] = description_doc
                if translations:
                    current_score["translations"] = translations
                scores_definition.append(current_score)
    elif library_vars_dict["tab"][title] == "implementation_groups":
        print("processing implementation groups")
        is_header = True
        for row in tab:
            if is_header:
                header = read_header(row)
                is_header = False
                assert "ref_id" in header
                assert "name" in header
                assert "description" in header
            elif any([c.value for c in row]):
                ref_id = str(row[header["ref_id"]].value).strip()
                name = row[header["name"]].value
                description = row[header["description"]].value
                translations = get_translations(header, row)
                current_def = {
                    "ref_id": ref_id,
                    "name": name,
                    "description": description,
                }
                if translations:
                    current_def["translations"] = translations
                implementation_groups_definition.append(current_def)
    elif library_vars_dict["tab"][title] == "risk_matrix":
        print("processing risk matrix")
        risk_matrix["urn"] = library_vars["risk_matrix_urn"]
        risk_matrix["ref_id"] = library_vars["risk_matrix_ref_id"]
        risk_matrix["name"] = library_vars["risk_matrix_name"]
        risk_matrix["description"] = library_vars["risk_matrix_description"]
        risk_matrix["probability"] = []
        risk_matrix["impact"] = []
        risk_matrix["risk"] = []
        risk_matrix["grid"] = []
        grid = {}
        grid_color = {}
        is_header = True
        for row in tab:
            if is_header:
                header = read_header(row)
                is_header = False
                assert "type" in header
                assert "id" in header
                assert "color" in header
                assert "abbreviation" in header
                assert "name" in header
                assert "description" in header
                assert "grid0" in header
                size_grid = len([h for h in header if len(h) > 4 and h[0:4] == "grid"])
            elif any([c.value for c in row]):
                ctype = row[header["type"]].value
                assert ctype in ("probability", "impact", "risk")
                id = row[header["id"]].value
                color = get_color(dataframe, row[header["color"]])
                abbreviation = row[header["abbreviation"]].value
                name = row[header["name"]].value
                description = row[header["description"]].value
                translations = get_translations(header, row)
                object = {
                    "id": id,
                    "abbreviation": abbreviation,
                    "name": name,
                    "description": description,
                }
                if translations:
                    object["translations"] = translations
                if color:
                    object["hexcolor"] = color
                risk_matrix[ctype].append(object)
                if ctype == "probability":
                    grid[id] = [c.value for c in row[6 : 6 + size_grid]]
                    grid_color[id] = [get_color(dataframe, c) for c in row[6:]]
        risk_matrix["grid"] = [grid[id] for id in sorted(grid)]
        for id in grid:
            for i, risk_id in enumerate(grid[id]):
                risk_color = (
                    risk_matrix["risk"][risk_id]["hexcolor"]
                    if "hexcolor" in risk_matrix["risk"][risk_id]
                    else None
                )
                if not risk_color == grid_color[id][i]:
                    print(f"color mismatch for risk id {risk_id}")
                    exit(1)
        for t in ("probability", "impact", "risk"):
            risk_matrix[t].sort(key=lambda c: c["id"])
    elif library_vars_dict["tab"][title] == "mappings":
        print("processing mappings")
        is_header = True
        source_prefix = library_vars["mapping_source_node_base_urn"]
        target_prefix = library_vars["mapping_target_node_base_urn"]
        for row in tab:
            if is_header:
                header = read_header(row)
                is_header = False
                assert "source_node_id" in header
                assert "target_node_id" in header
                assert "relationship" in header
            elif any([c.value for c in row]):
                # check if source_node_id and target_node_id exist in the supported values
                src_ids_set = build_ids_set("source")
                tgt_ids_set = build_ids_set("target")
                src_node_id = row[header["source_node_id"]].value
                tgt_node_id = row[header["target_node_id"]].value
                if src_node_id not in src_ids_set:
                    print(
                        f"WARNING: this source node id: {src_node_id} is not recognized. Fix it and try again before uploading your file."
                    )

                if tgt_node_id not in tgt_ids_set:
                    print(
                        f"WARNING: this target node id: {tgt_node_id} is not recognized. Fix it and try again before uploading your file."
                    )
                source_requirement_urn = source_prefix + ":" + src_node_id.lower().replace(" ", "-")
                target_requirement_urn = target_prefix + ":" + tgt_node_id.lower().replace(" ", "-")
                relationship = row[header["relationship"]].value
                rationale = (
                    row[header["rationale"]].value if "rationale" in header else None
                )
                strength_of_relationship = (
                    row[header["strength_of_relationship"]].value
                    if "strength_of_relationship" in header
                    else None
                )
                requirement_mappings.append(
                    {
                        "source_requirement_urn": source_requirement_urn,
                        "target_requirement_urn": target_requirement_urn,
                        "relationship": relationship,
                        "rationale": rationale,
                        "strength_of_relationship": strength_of_relationship,
                    }
                )

has_framework = "requirements" in [
    library_vars_dict["tab"][x] for x in library_vars_dict["tab"]
]
has_reference_controls = "reference_controls" in [
    library_vars_dict["tab"][x] for x in library_vars_dict["tab"]
]
has_threats = "threats" in [
    library_vars_dict["tab"][x] for x in library_vars_dict["tab"]
]

has_mappings = "mappings" in [
    library_vars_dict["tab"][x] for x in library_vars_dict["tab"]
]

lib_date = library_vars.get("library_publication_date", datetime.datetime.now())
if type(lib_date) == datetime.datetime:
    lib_date = lib_date.date()

convert_library_version = f"v1 ; Compat Mode: [{args.compat}]"    

library = {
    "convert_library_version": convert_library_version,
    "urn": library_vars["library_urn"],
    "locale": library_vars["library_locale"],
    "ref_id": library_vars["library_ref_id"],
    "name": library_vars["library_name"],
    "description": library_vars["library_description"],
    "copyright": library_vars["library_copyright"],
    "version": library_vars["library_version"],
    "publication_date": lib_date,
    "provider": library_vars["library_provider"],
    "packager": library_vars["library_packager"],
}
translations = get_translations_content(library_vars, "library")
if translations:
    library["translations"] = translations
if "library_dependencies" in library_vars:
    dependencies = [
        x for x in re.split(r"[\s,]+", library_vars["library_dependencies"])
    ]
    library["dependencies"] = dependencies

library["objects"] = {}

if has_reference_controls:
    library["objects"]["reference_controls"] = reference_controls

if has_threats:
    library["objects"]["threats"] = threat_definitions

if has_mappings:
    library["objects"]["requirement_mapping_set"] = {
        "urn": library_vars["mapping_urn"],
        "ref_id": library_vars["mapping_ref_id"],
        "name": library_vars["mapping_name"],
        "description": library_vars["mapping_description"],
        "source_framework_urn": library_vars["mapping_source_framework_urn"],
        "target_framework_urn": library_vars["mapping_target_framework_urn"],
    }
    translations = get_translations_content(library_vars, "mapping")
    if translations:
        library["objects"]["requirement_mapping_set"]["translations"] = translations
    library["objects"]["requirement_mapping_set"]["requirement_mappings"] = (
        requirement_mappings
    )


if has_framework:
    library["objects"]["framework"] = {
        "urn": library_vars["framework_urn"],
        "ref_id": library_vars["framework_ref_id"],
        "name": library_vars["framework_name"],
        "description": library_vars["framework_description"],
    }
    translations = get_translations_content(library_vars, "framework")
    if translations:
        library["objects"]["framework"]["translations"] = translations
    if "framework_min_score" in library_vars:
        library["objects"]["framework"]["min_score"] = library_vars[
            "framework_min_score"
        ]
    if "framework_max_score" in library_vars:
        library["objects"]["framework"]["max_score"] = library_vars[
            "framework_max_score"
        ]
    if scores_definition:
        library["objects"]["framework"]["scores_definition"] = scores_definition
    if implementation_groups_definition:
        library["objects"]["framework"]["implementation_groups_definition"] = (
            implementation_groups_definition
        )
    library["objects"]["framework"]["requirement_nodes"] = requirement_nodes

if risk_matrix:
    library["objects"]["risk_matrix"] = [risk_matrix]
    translations = get_translations_content(library_vars, "risk_matrix")
    if translations:
        library["objects"]["risk_matrix"][0]["translations"] = translations

if has_reference_controls and has_framework:
    print("\nValidating reference control references...")
    control_ids_set = build_reference_control_ids_set()
    validate_control_references(requirement_nodes, control_ids_set)

print("generating", output_file_name)
with open(output_file_name, "w", encoding="utf8") as file:
    yaml.dump(library, file, sort_keys=False)
