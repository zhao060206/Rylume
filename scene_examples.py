"""Eight original, explicitly specified scientific illustration fixtures.

These are editable teaching examples, not experimental observations. Each brief
states the relationships the fixture displays and is retained in the document.
"""
from __future__ import annotations

from scene_document import empty_scene, normalize_scene


EXAMPLES = [
    {"id": "egfr", "title": "EGFR · PI3K–AKT", "description": "膜受体、脂质转换和胞质级联", "category": "信号通路"},
    {"id": "jak_stat", "title": "JAK–STAT", "description": "磷酸化、二聚化与核内转录", "category": "信号通路"},
    {"id": "tgf_smad", "title": "TGF-β · SMAD", "description": "受体复合物、SMAD 结合与入核", "category": "信号通路"},
    {"id": "exosome", "title": "外泌体形成与释放", "description": "形成、运输、膜融合、胞外释放", "category": "过程"},
    {"id": "wound", "title": "伤口愈合", "description": "止血、炎症、增殖、重塑的组织变化", "category": "过程"},
    {"id": "tme", "title": "肿瘤微环境", "description": "细胞间促进、抑制与互作网络", "category": "细胞互作"},
    {"id": "nlrp3", "title": "NLRP3 组装", "description": "结构域、ASC 与 pro-caspase-1", "category": "结构组装"},
    {"id": "workflow", "title": "转录组实验流程", "description": "样本到分析的五步方框流程", "category": "实验流程"},
]

from scene_storyboards import STORYBOARDS, DESCRIPTIONS
from scene_flows import flow_catalog
EXAMPLES += [dict(id=t["example"],title=t["title"],description=t["description"],category=t["category"]) for t in flow_catalog()]
EXAMPLES += [dict(id=sid,title=title,description=DESCRIPTIONS[sid],category=category)
             for sid,title,category,_,_ in STORYBOARDS]


def _object(oid, kind, label, compartment="", state="", entity_id=None, **kwargs):
    return {"id": oid, "entity_id": entity_id or oid, "type": kind, "label": label,
            "compartment": compartment, "state": state, "font_size_pt": 8, **kwargs}


def _edge(eid, source, target, kind="activates", label="", **kwargs):
    return {"id": eid, "source": source, "target": target, "type": kind, "label": label, **kwargs}


def make_example(example_id, *, width_mm=180, height_mm=120, layout=True):
    if example_id.startswith("flow_"):
        from scene_flows import make_flow
        return make_flow(example_id,width_mm=width_mm,height_mm=height_mm)
    if example_id in {x[0] for x in STORYBOARDS}:
        from scene_storyboards import make_storyboard
        return make_storyboard(example_id,width_mm=width_mm,height_mm=height_mm)
    if example_id not in {x["id"] for x in EXAMPLES}:
        raise ValueError("未知样板")
    scene = empty_scene(width_mm=width_mm, height_mm=height_mm)
    scene["provenance"] = {"method": "original-editable-example", "example": example_id}
    scene["compartments"] = [
        {"id": "extracellular", "label": "Extracellular space", "kind": "extracellular"},
        {"id": "membrane", "label": "Plasma membrane", "kind": "membrane"},
        {"id": "cytoplasm", "label": "Cytoplasm", "kind": "cytoplasm"},
        {"id": "nucleus", "label": "Nucleus", "kind": "nucleus"},
    ]
    if example_id == "egfr":
        scene["title"] = "EGFR–PI3K–AKT signaling"
        scene["source_text"] = (
            "EGF binds and activates an EGFR dimer at the plasma membrane. Activated EGFR recruits and activates PI3K in the cytoplasm. "
            "PI3K catalyses conversion of membrane PIP2 to PIP3. PIP3 recruits AKT to the inner membrane. "
            "AKT is shown in its phosphorylated active state; intermediate activating kinases are omitted. Activated AKT indirectly promotes mTOR activity; mTOR promotes protein synthesis. This is a simplified schematic, not a complete pathway."
        )
        scene["compartments"] = scene["compartments"][:3]
        scene["objects"] = [
            _object("egf", "ligand", "EGF", "extracellular"),
            _object("egfr", "receptor_dimer", "EGFR", "membrane", "active"),
            _object("pi3k", "kinase", "PI3K", "cytoplasm", "active"),
            _object("pip2", "lipid", "PIP2", "membrane", "bisphosphate"),
            _object("pip3", "lipid", "PIP3", "membrane", "trisphosphate"),
            _object("akt", "kinase", "AKT", "cytoplasm", "phosphorylated"),
            _object("mtor", "kinase", "mTOR", "cytoplasm", "active"),
            _object("synthesis", "process", "Protein synthesis", "cytoplasm"),
        ]
        scene["relations"] = [
            _edge("e1", "egf", "egfr", "binds"), _edge("e2", "egfr", "pi3k"),
            _edge("e3", "pip2", "pip3", "converts", "PI3K"),
            _edge("e4", "pi3k", "pip3", "associates", "catalysis"),
            _edge("e5", "pip3", "akt", "binds", "recruitment"),
            _edge("e6", "akt", "mtor", indirect=True), _edge("e7", "mtor", "synthesis"),
        ]
    elif example_id == "jak_stat":
        scene["title"] = "JAK–STAT signaling"
        scene["source_text"] = (
            "A cytokine binds a cytokine receptor dimer at the plasma membrane and activates receptor-associated JAK. "
            "JAK phosphorylates cytoplasmic STAT. Phosphorylated STAT forms a dimer. The STAT dimer translocates into the nucleus "
            "and binds a DNA regulatory site to promote target-gene transcription."
        )
        scene["objects"] = [
            _object("cytokine", "ligand", "Cytokine", "extracellular"),
            _object("receptor", "receptor_dimer", "Cytokine receptor", "membrane"),
            _object("jak", "kinase", "JAK", "cytoplasm", "active"),
            _object("stat", "protein", "STAT", "cytoplasm", "phosphorylated", entity_id="stat_entity"),
            _object("stat_dimer", "tf", "STAT dimer", "cytoplasm", "dimer", entity_id="stat_entity"),
            _object("nuclear_stat", "tf", "Nuclear STAT", "nucleus", "dimer", entity_id="stat_entity"),
            _object("dna", "dna", "Target genes", "nucleus"),
        ]
        scene["relations"] = [
            _edge("e1", "cytokine", "receptor", "binds"), _edge("e2", "receptor", "jak"),
            _edge("e3", "jak", "stat", label="phosphorylation"),
            _edge("e4", "stat", "stat_dimer", "converts", "dimerization"),
            _edge("e5", "stat_dimer", "nuclear_stat", "transports", "nuclear import"),
            _edge("e6", "nuclear_stat", "dna", "binds", "transcription"),
        ]
    elif example_id == "tgf_smad":
        scene["title"] = "TGF-β–SMAD signaling"
        scene["source_text"] = (
            "Extracellular TGF-β binds the type II/type I TGF-β receptor complex at the plasma membrane. "
            "The activated type I receptor phosphorylates SMAD2/3 in the cytoplasm. Phosphorylated SMAD2/3 binds SMAD4 to form a complex. "
            "The SMAD complex enters the nucleus and associates with DNA to regulate target-gene transcription."
        )
        scene["objects"] = [
            _object("tgf", "ligand", "TGF-β", "extracellular"),
            _object("tgfr", "receptor_dimer", "TGF-βR II / I", "membrane", "active"),
            _object("smad23", "protein", "SMAD2/3", "cytoplasm", "phosphorylated", entity_id="smad23_entity"),
            _object("smad4", "protein", "SMAD4", "cytoplasm"),
            _object("smad_complex", "complex", "SMAD complex", "cytoplasm", "assembled", entity_id="smad_complex_entity"),
            _object("nuclear_smad", "complex", "Nuclear SMAD", "nucleus", "assembled", entity_id="smad_complex_entity"),
            _object("dna", "dna", "Target genes", "nucleus"),
        ]
        scene["relations"] = [
            _edge("e1", "tgf", "tgfr", "binds"), _edge("e2", "tgfr", "smad23", label="phosphorylation"),
            _edge("e3", "smad23", "smad_complex", "binds"), _edge("e4", "smad4", "smad_complex", "binds"),
            _edge("e5", "smad_complex", "nuclear_smad", "transports", "nuclear import"),
            _edge("e6", "nuclear_smad", "dna", "associates", "transcription"),
        ]
    else:
        scene["compartments"] = []
        if example_id == "exosome":
            scene["layout"] = "process"
            scene["title"] = "Exosome biogenesis and release"
            scene["source_text"] = "Intraluminal vesicles form within a multivesicular body (MVB). The MVB is transported to the plasma membrane, fuses with it, and releases exosomes into the extracellular space."
            scene["objects"] = [
                _object("formation", "mvb", "MVB formation", state="biogenesis"),
                _object("transport", "mvb", "MVB transport", state="transport", entity_id="formation"),
                _object("fusion", "vesicle_fusion", "Membrane fusion", state="fusion", entity_id="formation"),
                _object("release", "vesicle", "Exosome release", state="released"),
            ]
            scene["relations"] = [_edge("e1", "formation", "transport", "transports"), _edge("e2", "transport", "fusion", "transports"), _edge("e3", "fusion", "release", "transports")]
        elif example_id == "wound":
            scene["layout"] = "process"
            scene["title"] = "Cutaneous wound healing"
            scene["source_text"] = "Four stages of wound healing are shown: hemostasis with a fibrin-rich clot; inflammation with recruited neutrophils; proliferation with fibroblasts and new matrix; remodeling with aligned collagen. The temporal sequence does not imply sharply separated phases."
            scene["objects"] = [_object(oid, "tissue", label, state=oid) for oid, label in (
                ("hemostasis", "Hemostasis"), ("inflammation", "Inflammation"),
                ("proliferation", "Proliferation"), ("remodeling", "Remodeling"))]
            scene["relations"] = [_edge(f"e{i}", a["id"], b["id"], "converts") for i, (a,b) in enumerate(zip(scene["objects"],scene["objects"][1:]),1)]
        elif example_id == "tme":
            scene["layout"] = "network"
            scene["title"] = "Tumor microenvironment interactions"
            scene["source_text"] = "A simplified tumor microenvironment network: tumor cells activate cancer-associated fibroblasts (CAF); CAF interact with M2 macrophages and promote endothelial angiogenesis through VEGF; regulatory T cells inhibit cytotoxic CD8 T cells; CD8 T cells kill tumor cells; endothelial cells interact with tumor cells."
            scene["objects"] = [_object(*args) for args in (
                ("tumor", "tumor_cell", "Tumor cells"), ("caf", "fibroblast", "CAF"),
                ("m2", "immune_cell", "M2 macrophages"), ("treg", "immune_cell", "Treg"),
                ("cd8", "immune_cell", "CD8 T cells"), ("endo", "endothelial", "Endothelial cells"))]
            scene["relations"] = [_edge("e1", "tumor", "caf"), _edge("e2", "caf", "m2", "associates"),
                _edge("e3", "caf", "endo", label="VEGF"), _edge("e4", "treg", "cd8", "inhibits"),
                _edge("e5", "cd8", "tumor", "inhibits", "cytotoxicity"), _edge("e6", "endo", "tumor", "associates")]
        elif example_id == "nlrp3":
            scene["layout"] = "assembly"
            scene["title"] = "NLRP3 inflammasome assembly"
            scene["source_text"] = "NLRP3 comprises PYD, NACHT and LRR domains. PYD binds the PYD of ASC. ASC also has a CARD domain, which recruits pro-caspase-1 through CARD–CARD interaction. Domains within each protein are grouped, not successive process stages. This is a domain schematic, not an atomic structure."
            scene["objects"] = [
                _object("pyd", "domain", "PYD", group_id="nlrp3"),
                _object("nacht", "domain", "NACHT", group_id="nlrp3"),
                _object("lrr", "domain", "LRR", group_id="nlrp3"),
                _object("asc_pyd", "domain", "ASC · PYD", group_id="asc"),
                _object("asc_card", "domain", "ASC · CARD", group_id="asc"),
                _object("caspase", "complex", "pro-caspase-1"),
            ]
            scene["relations"] = [_edge("e1", "pyd", "nacht", "associates"), _edge("e2", "nacht", "lrr", "associates"),
                _edge("e3", "pyd", "asc_pyd", "binds", "PYD–PYD"), _edge("e4", "asc_pyd", "asc_card", "associates"),
                _edge("e5", "asc_card", "caspase", "binds", "CARD–CARD")]
        else:
            scene["layout"] = "process"
            scene["title"] = "RNA sequencing workflow"
            scene["source_text"] = "A boxed experimental workflow: sample collection → RNA extraction → library preparation → sequencing → bioinformatic analysis."
            scene["objects"] = [_object(oid, "process", label) for oid,label in (
                ("sample", "Sample collection"), ("rna", "RNA extraction"), ("library", "Library preparation"),
                ("sequencing", "Sequencing"), ("analysis", "Data analysis"))]
            scene["relations"] = [_edge(f"e{i}", a["id"], b["id"], "transports") for i,(a,b) in enumerate(zip(scene["objects"],scene["objects"][1:]),1)]
    scene["requirements"] = {"objects": [o["id"] for o in scene["objects"]],
                             "relations": [r["id"] for r in scene["relations"]]}
    for item in scene["objects"] + scene["relations"]:
        item["evidence"] = scene["source_text"]
    scene = normalize_scene(scene)
    if layout:
        from scene_render import layout_scene
        scene = normalize_scene(layout_scene(scene))
    return scene
