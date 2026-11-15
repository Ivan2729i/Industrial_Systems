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
    p.add_argument('--download-only',action='store_true')
    a=p.parse_args()
    w,s,e,n=map(float,a.bbox.split(','));day=date.fromisoformat(a.date)
    if not (-180<=w<e<=180 and -90<s<n<90):p.error('bbox invalido; dividir antimeridiano')
    if day.year!=2024:p.error('Conversion temporal V1 validada solo para 2024; no aplicar a otros periodos sin validar TAI93')
    if not 0<=a.resolution<=15 or a.version=='v1_experimental':p.error('Usa resolucion valida y nueva version explicita')
    for granule in [a.modis,a.viirs]:
        if datetime.strptime(granule,'A%Y%j.%H%M').date()!=day:p.error('Granulo no corresponde a fecha')
    work=a.workdir.resolve();work.mkdir(parents=True,exist_ok=True)
    config={k:str(v) for k,v in vars(a).items() if k!='download_only'}
    manifest=work/'run.json'
    if manifest.exists() and json.loads(manifest.read_text())['config']!=config:p.error('Directorio pertenece a otra ejecucion')
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'backend'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
    import django;django.setup()
    from analysis.models import Region, HarmonizationRun
    region_record,_=Region.objects.get_or_create(id=a.region,defaults={'name':a.region,'west':w,'south':s,'east':e,'north':n})
    key=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    def state(status,**extra):
        manifest.write_text(json.dumps({'config':config,'status':status,**extra},indent=2),encoding='utf-8')
        public={k:v for k,v in config.items() if k!='workdir'}
        run,_=HarmonizationRun.objects.get_or_create(key=key,defaults={'region':region_record,'date':day,'version':a.version,'resolution':a.resolution,'status':status})
        run.status=status;run.parameters=public
        if 'products' in extra:run.products=extra['products']
        if 'records' in extra:run.records=extra['records']
        run.error_type=extra.get('error_type','');run.save()
    state('PROCESAMIENTO_PENDIENTE')
    try:
        import earthaccess
        load_dotenv(Path(__file__).resolve().parent.parent/'.env')
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            auth=earthaccess.login(strategy='environment',persist=False)
        if not auth.authenticated:raise RuntimeError('Earthdata authentication failed')
        products=[('MYD14',a.modis,'061'),('MYD03',a.modis,'061'),('VNP14IMG',a.viirs,'002'),('VNP03IMG',a.viirs,'002')]
        provenance=[]
        for product,granule,version in products:
            prefix=f'{product}.{granule}.{version}.'
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                matches=earthaccess.search_data(short_name=product,granule_name=prefix+'*',count=10)
            if not matches:raise RuntimeError('CMR product unavailable: '+prefix)
            print('Downloading/validating '+prefix,flush=True)
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                files=earthaccess.download(matches[:1],local_path=str(work/'granules'),threads=1)
            if not files or not Path(files[0]).is_file() or Path(files[0]).stat().st_size==0:raise RuntimeError('Download incomplete: '+prefix)
            provenance.append({'product':product,'granule':granule,'collection_version':version,'file':Path(files[0]).name,'bytes':Path(files[0]).stat().st_size})
        state('DESCARGADO',products=provenance)
        if a.download_only:return
        import regiones, analizar_celdas as cells, omparar_tiempos as temporal, cobertura_espacial as spatial, generar_armonizacion_v1 as harmonize
        region={'nombre':a.region,'oeste':w,'sur':s,'este':e,'norte':n}
        regiones.REGIONES[a.region]=region
        cells.CONFIGURACIONES[a.date]={'carpeta':work/'granules','modis':a.modis,'viirs':a.viirs}
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
        state('COMPLETADO',products=provenance,records=len(frame),output=str(target))
    except Exception as exc:
        # Do not expose authenticated download URLs or credentials.
        state('ERROR_PROCESAMIENTO',error_type=type(exc).__name__)
        print('Scientific run failed: '+type(exc).__name__+'. See isolated run state; credentials withheld.',flush=True)
        raise SystemExit(1)
if __name__=='__main__':main()
