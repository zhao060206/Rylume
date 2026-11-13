"""Attach scene relation vectors to scientific object frames in PowerPoint."""
import copy

from lxml.etree import SubElement
from pptx import Presentation
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.oxml.ns import qn


def bind_scene_connections(path,scene):
    from scene_render import connection_geometry
    presentation=Presentation(path);slide=presentation.slides[0]
    groups={s.name:s for s in slide.shapes if hasattr(s,'shapes')}
    objects={o['id']:o for o in scene['objects']}
    frames={};bound=0
    def frame(ident):
        if ident in frames:return frames[ident]
        group=groups[ident];o=objects[ident]
        shape=group.shapes.add_shape(MSO_SHAPE.RECTANGLE,*[round(o[k]*36000) for k in ('x','y','w','h')])
        shape.name='connection-frame-'+ident;shape.fill.background();shape.line.fill.background()
        # Keep arbitrary edge attachment positions instead of snapping exports
        # back to the four standard midpoints.
        geom=shape._element.spPr.find(qn('a:prstGeom'))
        custom=SubElement(shape._element.spPr,qn('a:custGeom'))
        for tag in ('avLst','gdLst','ahLst','cxnLst'):SubElement(custom,qn('a:'+tag))
        SubElement(custom,qn('a:rect'),l='0',t='0',r='r',b='b');SubElement(custom,qn('a:pathLst'))
        shape._element.spPr.remove(geom)
        shape._element.spPr.remove(custom);shape._element.spPr.insert(1,custom)
        style=shape._element.find(qn('p:style'))
        if style is not None:shape._element.remove(style)
        frames[ident]=shape
        return shape
    def attach(connector,ident,which,x,y):
        anchor=frame(ident);o=objects[ident]
        sites=anchor._element.spPr.find(qn('a:custGeom')).find(qn('a:cxnLst'))
        site=SubElement(sites,qn('a:cxn'),ang='0')
        SubElement(site,qn('a:pos'),x=str(round((x-o['x'])/o['w']*anchor.width)),y=str(round((y-o['y'])/o['h']*anchor.height)))
        props=connector._element.find(qn('p:nvCxnSpPr')).find(qn('p:cNvCxnSpPr'))
        SubElement(props,qn('a:'+which),id=str(anchor.shape_id),idx=str(len(sites)-1))
    for relation in scene['relations']:
        group=groups.get(relation['id'])
        if not group or relation['source'] not in groups or relation['target'] not in groups:continue
        shapes=list(group.shapes)
        vectors=[s for s in shapes if s._element.find(qn('p:spPr')) is not None
                 and s._element.spPr.find(qn('a:custGeom')) is not None]
        if not vectors:continue
        g=connection_geometry(scene,relation)
        curved=abs((g['control']['x']-(g['x1']+g['x2'])/2)*(g['y2']-g['y1'])-(g['control']['y']-(g['y1']+g['y2'])/2)*(g['x2']-g['x1']))>1
        connector=slide.shapes.add_connector(MSO_CONNECTOR.CURVE if curved else MSO_CONNECTOR.STRAIGHT,round(g['x1']*36000),round(g['y1']*36000),round(g['x2']*36000),round(g['y2']*36000))
        connector.name=relation['id']
        line=connector._element.spPr.find(qn('a:ln'))
        original=vectors[0]._element.spPr.find(qn('a:ln'))
        if line is not None:connector._element.spPr.remove(line)
        line=copy.deepcopy(original);connector._element.spPr.append(line)
        if relation.get('indirect'):
            dash=line.find(qn('a:prstDash'))
            if dash is None:SubElement(line,qn('a:prstDash'),val='dash')
        end_type={'sequence':'triangle','converts':'triangle','activates':'arrow'}.get(relation['type'])
        if end_type:SubElement(line,qn('a:tailEnd'),type=end_type,w='sm',len='sm')
        style=connector._element.find(qn('p:style'))
        if style is not None:connector._element.remove(style)
        attach(connector,relation['source'],'stCxn',g['x1'],g['y1'])
        attach(connector,relation['target'],'endCxn',g['x2'],g['y2'])
        element=connector._element;tree=element.getparent();tree.remove(element)
        tree.insert(tree.index(group._element),element)
        symbol_index=0
        for shape in shapes:
            if shape is vectors[0]:continue
            preset=shape._element.spPr.find(qn('a:prstGeom'))
            is_symbol=shape in vectors[1:] or (preset is not None and preset.get('prst')=='ellipse' and relation['type']=='binds')
            if is_symbol:
                if end_type:continue  # Native arrowheads follow their endpoint.
                owner=relation['source'] if relation['type']=='binds' and symbol_index==0 else relation['target']
                symbol_index+=1
                el=shape._element;el.getparent().remove(el)
                groups[owner].shapes._spTree.insert_element_before(el,'p:extLst')
                groups[owner].shapes._recalculate_extents()
            else:
                # Live relation labels remain independently editable.
                el=shape._element;el.getparent().remove(el);tree.insert(tree.index(group._element),el)
        tree.remove(group._element);bound+=1
    presentation.save(path)
    return bound
