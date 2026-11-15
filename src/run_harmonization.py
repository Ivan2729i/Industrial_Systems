"""Isolated batch adapter for the existing V1 scientific algorithms (Aqua/SNPP)."""
import argparse, contextlib, csv, io, json, os, sys, hashlib
from datetime import date, datetime
from pathlib import Path
from dotenv import load_dotenv

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--bbox',required=True)
    p.add_argument('--date',required=True)
    p.add_argument('--region',required=True)
    p.add_argument('--modis',required=True)
    p.add_argument('--viirs',required=True)
    p.add_argument('--resolution',type=int,default=7)
    p.add_argument('--version',required=True)
    p.add_argument('--workdir',type=Path,required=True)
    p.add_argument('--cache-dir',type=Path,default=Path(__file__).resolve().parent/'datos'/'cache_level2')
    p.add_argument('--local-granules',type=Path,help='Directorio existente con los cuatro productos verificados')
    p.add_argument('--download-only',action='store_true')
    a=p.parse_args()
    w,s,e,n=map(float,a.bbox.split(','));day=date.fromisoformat(a.date)
    if not (-180<=w<e<=180 and -90<s<n<90):p.error('bbox invalido; dividir antimeridiano')
    if not 0<=a.resolution<=15 or a.version=='v1_experimental':p.error('Usa resolucion valida y nueva version explicita')
    if datetime.strptime(a.modis,'A%Y%j.%H%M').date()!=day:p.error('La fecha UTC se ancla en el granulo MODIS')
    if abs((datetime.strptime(a.viirs,'A%Y%j.%H%M').date()-day).days)>1:p.error('VIIRS fuera de la ventana temporal')
    work=a.workdir.resolve();work.mkdir(parents=True,exist_ok=True)
    config={k:str(v) for k,v in vars(a).items() if k!='download_only'}
    manifest=work/'run.json'
    if manifest.exists() and json.loads(manifest.read_text())['config']!=config:p.error('Directorio pertenece a otra ejecucion')
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'backend'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
    import django;django.setup()
    from analysis.models import Region, HarmonizationRun
    region_record,_=Region.objects.get_or_create(id=a.region,defaults={'name':a.region,'west':w,'south':s,'east':e,'north':n})
    if [region_record.west,region_record.south,region_record.east,region_record.north] != [w,s,e,n]:p.error('Identificador de region ya corresponde a otra extension')
    key=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    def state(status,**extra):
        manifest.write_text(json.dumps({'config':config,'status':status,**extra},indent=2),encoding='utf-8')
        public={k:v for k,v in config.items() if k not in ('workdir','cache_dir','local_granules')}
        run,_=HarmonizationRun.objects.get_or_create(key=key,defaults={'region':region_record,'date':day,'version':a.version,'resolution':a.resolution,'status':status})
        run.status=status;run.parameters=public
        if 'products' in extra:run.products=extra['products']
        if 'records' in extra:run.records=extra['records']
        run.error_type=extra.get('error_type','');run.save()
    if manifest.exists() and json.loads(manifest.read_text()).get('status')=='COMPLETADO':
        print('Trabajo completado previamente; no se repite.',flush=True);return
    state('PROCESAMIENTO_PENDIENTE')
    try:
        import earthaccess
        load_dotenv(Path(__file__).resolve().parent.parent/'.env')
        if not a.local_granules:
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                auth=earthaccess.login(strategy='environment',persist=False)
            if not auth.authenticated:raise RuntimeError('Earthdata authentication failed')
        products=[('MYD14',a.modis,'061'),('MYD03',a.modis,'061'),('VNP14IMG',a.viirs,'002'),('VNP03IMG',a.viirs,'002')]
        provenance=[]
        for product,granule,version in products:
            prefix=f'{product}.{granule}.{version}.'
            if a.local_granules:
                files=list(a.local_granules.glob(prefix+'*'))
                if len(files)!=1:raise RuntimeError('Se requieren cuatro productos locales univocos')
                provenance.append({'product':product,'granule':granule,'collection_version':version,'file':files[0].name,'bytes':files[0].stat().st_size});continue
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                matches=earthaccess.search_data(short_name=product,granule_name=prefix+'*',count=10,**({'bounding_box':(w,s,e,n)} if product in ('MYD14','VNP14IMG') else {}))
            if len(matches)!=1:raise RuntimeError('CMR product unavailable: '+prefix)
            links=matches[0].data_links(access='external')
            if not links:raise RuntimeError('Sin enlaces de descarga verificables')
            print('Downloading/validating '+prefix,flush=True)
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                files=earthaccess.download(matches[:1],local_path=str(a.cache_dir),threads=1)
            if not files or not Path(files[0]).is_file() or Path(files[0]).stat().st_size==0:raise RuntimeError('Download incomplete: '+prefix)
            with Path(files[0]).open('rb') as source_file: checksum=hashlib.file_digest(source_file,'sha256').hexdigest()
            provenance.append({'product':product,'granule':granule,'collection_version':version,'file':Path(files[0]).name,'bytes':Path(files[0]).stat().st_size,'sha256':checksum,'cmr_concept_id':matches[0].get('meta',{}).get('concept-id'),'granule_ur':matches[0].get('umm',{}).get('GranuleUR')})
        state('DESCARGADO',products=provenance)
        if a.download_only:return
        import regiones, analizar_celdas as cells, omparar_tiempos as temporal, cobertura_espacial as spatial, generar_armonizacion_v1 as harmonize
        region={'nombre':a.region,'oeste':w,'sur':s,'este':e,'norte':n}
        regiones.REGIONES[a.region]=region
        cells.CONFIGURACIONES[a.date]={'carpeta':a.local_granules or a.cache_dir,'modis':a.modis,'viirs':a.viirs}
        out=work/'results';out.mkdir(exist_ok=True)
        for module in [cells,temporal,spatial,harmonize]:
            module.RESOLUCION_H3=a.resolution
            if hasattr(module,'DIRECTORIO_RESULTADOS'):module.DIRECTORIO_RESULTADOS=out
            if hasattr(module,'RESULTADOS'):module.RESULTADOS=out
        sys.argv=['scientific','--fecha',a.date,'--region',a.region]
        for module in [cells,temporal,spatial]:
            state('PROCESANDO',stage=module.__name__,products=provenance)
            module.main()
        frame=harmonize.procesar_region(a.region,a.date)
        frame['version_armonizacion']=a.version
        frame['metodo']=f'H3_{a.resolution}_PRESENCIA_DETECCION'
        frame['calibracion_estadistica']=False;frame['geometria_validada']=False
        frame['region_nombre']=a.region
        frame['origen_datos']='NASA_LEVEL2_AQUA_SNPP'
        if frame.empty:raise RuntimeError('Sin observaciones en esta pareja y extension')
        sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'backend'))
        os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
        import django;django.setup()
        from analysis.management.commands.import_observations import REQUIRED
        for column in REQUIRED:
            if column not in frame:frame[column]=None
        target=out/'observations.csv';frame.to_csv(target,index=False)
        from django.core.management import call_command
        from analysis.models import Region
        Region.objects.get_or_create(id=a.region,defaults={'name':a.region,'west':w,'south':s,'east':e,'north':n})
        call_command('import_observations',file=str(target))
        from analysis.models import OverpassPair
        OverpassPair.objects.filter(region=region_record,date=day,modis_sobrevuelo=a.modis,viirs_sobrevuelo=a.viirs).update(modis_platform='Aqua',viirs_platform='Suomi NPP')
        state('COMPLETADO',products=provenance,records=len(frame),output=str(target))
    except Exception as exc:
        # Do not expose authenticated download URLs or credentials.
        state('ERROR_PROCESAMIENTO',error_type=type(exc).__name__)
        print('Scientific run failed: '+type(exc).__name__+'. See isolated run state; credentials withheld.',flush=True)
        raise SystemExit(1)
if __name__=='__main__':main()
