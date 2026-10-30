import json, time
from pathlib import Path
import compose, review, qa
OUT = Path("real-run")
scene = json.loads((OUT/"scene.json").read_text(encoding="utf-8"))
assets, engines = {}, {}
for i, ent in enumerate(scene["entities"], 1):
    cut = (OUT/f"{i:02d}-{ent['id']}-cut.png").read_bytes()
    t=time.time(); svg, aw, ah, engine = compose.asset_svg(cut, {"quality":"hd","vectorize":{"engine":"hifi"}})
    (OUT/f"{i:02d}-{ent['id']}.svg").write_bytes(svg)
    assets[ent["id"]]=(svg,aw,ah); engines[ent["id"]]=engine
    print(i, ent["id"], engine, len(svg)//1024, "KB", "box", round(aw), round(ah), round(time.time()-t,1), "s", flush=True)
svg = compose.compose_svg(scene, assets, "Times New Roman")
(OUT/"figure2.svg").write_bytes(svg)
w,h=scene["canvas"]
png=qa.rasterize(svg,int(w),int(h),{})
if png: (OUT/"figure2.png").write_bytes(png)
rep=review.findings(svg,scene)
(OUT/"review2.json").write_text(json.dumps(rep,ensure_ascii=False,indent=1),encoding="utf-8")
print("figure", len(svg)//1024,"KB","findings",len(rep))
for f in rep[:12]: print(" -", f.get("type"), f.get("detail") or f)
