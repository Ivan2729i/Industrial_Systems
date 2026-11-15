"""Pixel product extending the existing H3 analysis. All associations are exploratory.

Spatial rule: >=50% of the reconstructed VIIRS footprint intersects a MODIS
footprint, <=15 minutes, valid VIIRS QA and evaluable H3 context for both.
Each VIIRS selects one MODIS by overlap, distance, stable ID (deterministic).
Coordinates are never averaged; MODIS anchor or unmatched source center is used.
"""
import hashlib,json,math
from pathlib import Path
import h3,h5py,numpy as np
from pyhdf.SD import SD,SDC
from shapely.geometry import Polygon,Point
from shapely.strtree import STRtree
from cobertura_espacial import bloques_modis,bloques_viirs,proyeccion_local,LIMITES,encontrar,reconstruir_huella
from omparar_tiempos import convertir_utc

METHOD='L2_FOOTPRINT_ONE_TO_MANY_EXPLORATORY_V1'

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def footprint(lat,lon,r,c,global_row,sensor,projector):
    """Same within-scan neighbor derivatives and rejection limits as coverage V1."""
    scan=LIMITES[sensor]['filas_escaneo']; first=global_row//scan*scan
    up=r-int(global_row>first);down=r+int(global_row<first+scan-1)
    left=max(c-1,0);right=min(c+1,lat.shape[1]-1)
    if up<0 or down>=lat.shape[0] or down==up or left==right:return None
    coords=[(float(lon[y,x]),float(lat[y,x])) for y,x in [(r,c),(r,left),(r,right),(up,c),(down,c)]]
    if any(not(math.isfinite(x) and math.isfinite(y) and -180<=x<=180 and -90<=y<=90) for x,y in coords):return None
    projected=[projector.transform(x,y) for x,y in coords]; (x,y),(xi,yi),(xd,yd),(xs,ys),(xb,yb)=projected
    dx,dy=(xd-xi)/(right-left),(yd-yi)/(right-left);ex,ey=(xb-xs)/(down-up),(yb-ys)/(down-up)
    return reconstruir_huella(x,y,dx,dy,ex,ey,sensor)

def extract(folder,granule,sensor,region,resolution,projector,diagnostics=None):
    folder=Path(folder)
    if sensor=='MODIS':
        source=encontrar(folder,f'MYD14.{granule}.061.','.hdf');geo_path=encontrar(folder,f'MYD03.{granule}.061.','.hdf')
        fire=SD(str(source),SDC.READ);geo=SD(str(geo_path),SDC.READ)
        times=np.asarray(geo.select('EV center time').get()).ravel();qa_ds=fire.select('algorithm QA')
        scan=10;blocks=bloques_modis(folder,granule)
    else:
        source=encontrar(folder,f'VNP14IMG.{granule}.002.','.nc');geo_path=encontrar(folder,f'VNP03IMG.{granule}.002.','.nc')
        fire=h5py.File(source,'r');geo=h5py.File(geo_path,'r')
        times=np.asarray(geo['scan_line_attributes/ev_mid_time'][:]).ravel();qa_ds=fire['algorithm QA'];scan=32;blocks=bloques_viirs(folder,granule)
    pixels=[]
    audit={'positive_mask_pixels_in_granule':0,'invalid_geolocation':0,'outside_requested_bbox':0,'retained_in_scope':0}
    try:
        for lat,lon,mask,offset,n_core,start in blocks:
            core=mask[offset:offset+n_core];la=lat[offset:offset+n_core];lo=lon[offset:offset+n_core]
            mask_positive=np.isin(core,[7,8,9]);geo_valid=np.isfinite(la)&np.isfinite(lo)&(la>=-90)&(la<=90)&(lo>=-180)&(lo<=180)
            audit['positive_mask_pixels_in_granule']+=int(mask_positive.sum());audit['invalid_geolocation']+=int((mask_positive & ~geo_valid).sum())
            positive=np.isin(core,[7,8,9]) & np.isfinite(la) & np.isfinite(lo) & (la>=region['sur']) & (la<=region['norte']) & (lo>=region['oeste']) & (lo<=region['este'])
            for rr,cc in zip(*np.where(positive)):
                row,column=int(start+rr),int(cc);local=int(offset+rr)
                stamp=convertir_utc(times[row//scan]);bits=int(qa_ds.get(start=(row,column),count=(1,1))[0,0]) if sensor=='MODIS' else int(qa_ds[row,column])
                latitude,longitude=float(la[rr,cc]),float(lo[rr,cc]);cell=h3.latlng_to_cell(latitude,longitude,resolution)
                qa={'raw':bits,'bowtie_residual':bool(bits&(1<<22)) if sensor=='VIIRS' else None,'geo_non_nominal':bool(bits&(1<<5)) if sensor=='VIIRS' else None,'interpretation':'VIIRS_bits_22_5' if sensor=='VIIRS' else 'MODIS_raw_preserved_mask_class_used'}
                pixel={'id':digest([source.name,row,column]),'sensor':sensor,'platform':'Aqua' if sensor=='MODIS' else 'Suomi NPP','granule':granule,'source_file':source.name,'row':row,'column':column,'observed_at':stamp.isoformat(),'latitude':latitude,'longitude':longitude,'fire_class':int(core[rr,cc]),'qa':qa,'provenance':{'geolocation_file':geo_path.name,'product':'MYD14' if sensor=='MODIS' else 'VNP14IMG','collection_version':'061' if sensor=='MODIS' else '002','time_basis':'scan_center_TAI93_to_UTC'},'h3':cell,'h3_r7':h3.latlng_to_cell(latitude,longitude,7)}
                pixel['_shape']=footprint(lat,lon,local,column,row,sensor,projector)
                pixels.append(pixel)
    finally:
        blocks.close()
        if sensor=='MODIS':fire.end();geo.end()
        else:fire.close();geo.close()
    audit['retained_in_scope']=len(pixels);audit['outside_requested_bbox']=audit['positive_mask_pixels_in_granule']-audit['invalid_geolocation']-len(pixels)
    if diagnostics is not None:diagnostics[sensor]=audit
    return pixels

def associate(pixels,context,projector):
    def eligible(p):
        c=context.get(p['h3'],{})
        return p['_shape'] is not None and c.get('estrato_temporal') in ['A_0_A_5_MIN','B_MAS_5_A_15_MIN'] and (p['sensor']=='MODIS' or not (p['qa']['bowtie_residual'] or p['qa']['geo_non_nominal']))
    modis=sorted([p for p in pixels if p['sensor']=='MODIS'],key=lambda p:p['id'])
    candidates=[m for m in modis if eligible(m)];tree=STRtree([p['_shape'] for p in candidates]) if candidates else None
    assigned={m['id']:[] for m in modis};details={};unmatched=[]
    for v in sorted([p for p in pixels if p['sensor']=='VIIRS'],key=lambda p:p['id']):
        matches=[]
        if eligible(v) and tree is not None:
            for index in tree.query(v['_shape'],predicate='intersects'):
                m=candidates[int(index)];dt=abs((__import__('datetime').datetime.fromisoformat(v['observed_at'])-__import__('datetime').datetime.fromisoformat(m['observed_at'])).total_seconds())/60
                overlap=m['_shape'].intersection(v['_shape']).area/v['_shape'].area
                mx,my=projector.transform(m['longitude'],m['latitude']);vx,vy=projector.transform(v['longitude'],v['latitude']);distance=math.hypot(mx-vx,my-vy)
                if dt<=15 and overlap>=.5:matches.append((-overlap,distance,m['id'],m,dt))
        if matches:
            overlap,distance,_,m,dt=min(matches,key=lambda x:x[:3]);assigned[m['id']].append(v);details[v['id']]={'overlap_viirs_fraction':-overlap,'center_distance_m':distance,'difference_minutes':dt}
        else:unmatched.append(v)
    groups=[]
    for m in modis:
        members=[m]+assigned[m['id']];status='ASOCIADA' if len(members)>1 else ('SOLO_MODIS' if eligible(m) else 'SIN_COMPARABILIDAD')
        groups.append((m,members,status))
    for v in unmatched:groups.append((v,[v],'SOLO_VIIRS' if eligible(v) else 'SIN_COMPARABILIDAD'))
    result=[]
    for representative,members,status in groups:
        result.append({'representative':representative['id'],'members':[p['id'] for p in members],'status':status,'h3':representative['h3'],'assessment':{'exploratory':True,'calibrated_sensitivity':False,'representative_position':'original_MODIS_center' if representative['sensor']=='MODIS' else 'original_VIIRS_center','footprints':'approximate_neighbor_derivatives_not_instrument_footprints','minimum_viirs_overlap_fraction':.5,'maximum_difference_minutes':15,'h3_context':context.get(representative['h3'],{}),'associations':{p['id']:details[p['id']] for p in members if p['id'] in details},'reason':'spatiotemporal_footprint_association' if status=='ASOCIADA' else 'no_assigned_compatible_positive' if status.startswith('SOLO') else 'QA_geometry_or_H3_comparability_insufficient'}})
    assert sorted(p['id'] for p in pixels)==sorted(pid for g in result for pid in g['members'])
    return result

def generate(folder,modis_id,viirs_id,region,frame,resolution=7):
    projector,_,_=proyeccion_local(region)
    diagnostics={}
    pixels=extract(folder,modis_id,'MODIS',region,resolution,projector,diagnostics)+extract(folder,viirs_id,'VIIRS',region,resolution,projector,diagnostics)
    # Only scientifically relevant context, preserving original H3 analysis separately.
    context={str(r.celda_h3):{'estrato_temporal':r.estrato_temporal,'coverage_shared_pct':None if np.isnan(r.cobertura_compartida_pct) else float(r.cobertura_compartida_pct),'h3_class_qa':r.coincidencia_qa} for r in frame.itertuples()}
    groups=associate(pixels,context,projector)
    clean=[{k:v for k,v in p.items() if k not in ('_shape','h3')} for p in pixels]
    return {'method':METHOD,'pixels':clean,'detections':groups,'conservation':{'source_audit':diagnostics,'input_positive_pixels':len(pixels),'output_members':sum(len(g['members']) for g in groups),'output_detections':len(groups)}}
