"""Rebuild original editable benchmarks and keep their audit evidence."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scene_document import audit_scene
from scene_examples import EXAMPLES,make_example
from scene_export import export_scene


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",default="out/v2-benchmarks")
    parser.add_argument("--examples",nargs="*",default=[x["id"] for x in EXAMPLES])
    parser.add_argument("--formats",nargs="*",default=["svg","png"])
    parser.add_argument("--width",type=float,default=180)
    parser.add_argument("--height",type=float,default=120)
    args=parser.parse_args()
    output=Path(args.output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for example in args.examples:
        scene=make_example(example,width_mm=args.width,height_mm=args.height)
        (output/f"{example}.scene.json").write_text(json.dumps(scene,ensure_ascii=False,indent=2),encoding="utf-8")
        audit=audit_scene(scene)
        (output/f"{example}.audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
        exports=[export_scene(scene,fmt,output/f"{example}.{fmt}") for fmt in args.formats]
        manifest.append({"id":example,"audit":audit,"exports":exports})
        print(f"{example}: {audit['errors']} errors, {audit['warnings']} warnings")
    (output/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")


if __name__=="__main__":
    main()
