/** Detached JSON values, sharing immutable strings such as vector artwork. */
export const copySceneData=value=>Array.isArray(value)?value.map(copySceneData):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).map(([key,item])=>[key,copySceneData(item)])):value;

/** Apply a canonical server delta without replaying edits made during a save. */
export function applySceneDelta(scene,delta){
  const next=copySceneData(scene);
  Object.assign(next,copySceneData(delta.fields));
  for(const field of ['objects','relations']){
    const changes=delta[field];if(!changes)continue;
    const items=new Map(next[field].map(item=>[item.id,item]));
    for(const id of changes.removed)items.delete(id);
    for(const item of changes.added)items.set(item.id,copySceneData(item));
    for(const update of changes.updated){
      const item=items.get(update.id);if(!item)throw Error('保存结果缺少对象，请重新载入图版');
      Object.assign(item,copySceneData(update.changes));
      for(const key of update.unset)delete item[key];
    }
    next[field]=(changes.order||[...items.keys()]).map(id=>items.get(id));
  }
  return next;
}

/** Retain a structural SVG refresh across subsequent saves while typing. */
export class SceneSaveCache{
  reset(scene){this.scene=scene;this.canonicalBase=null;}
  accept(data,baseline=this.scene){
    if(data.scene_delta){data.scene=applySceneDelta(baseline,data.scene_delta);data.svg=undefined;}
    this.scene=data.scene;
    if(data.svg!==undefined)this.canonicalBase={scene:data.scene,svg:data.svg};
  }
  consumePreview(data){
    const base=this.canonicalBase;this.canonicalBase=null;
    return [data.scene,base?.svg??data.svg,base?.scene??data.scene];
  }
}
