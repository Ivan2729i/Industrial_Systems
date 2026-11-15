import os,sys,time
sys.path.insert(0,'backend');os.environ['DJANGO_SETTINGS_MODULE']='config.settings'
import django;django.setup()
from rest_framework.test import APIRequestFactory
from analysis.detections_api import detections,availability
from analysis.models import FireDetection
factory=APIRequestFactory()
for sensor in ['modis','viirs']:
 t=time.monotonic();r=detections(factory.get('/',{'sensor':sensor,'start_date':'2024-04-16','end_date':'2024-04-16','bbox':'world','retrieve':'true','aggregate':'true'}));print('WORLD',sensor,r.status_code,'count',r.data.get('count'),'groups',len(r.data.get('results',[])),'seconds',round(time.monotonic()-t,2),flush=True)
 for name,bbox in [('Africa','10,-15,35,10'),('Asia','95,5,120,30'),('Australia','110,-45,155,-10'),('Europe','-10,35,40,65'),('Empty','-150,-50,-149,-49')]:
  r=detections(factory.get('/',{'sensor':sensor,'start_date':'2024-04-16','end_date':'2024-04-16','bbox':bbox,'retrieve':'true','aggregate':'true'}));print(name,sensor,r.status_code,r.data.get('count'),r.data.get('status'),flush=True)
 a=availability(factory.get('/',{'sensor':sensor}));print('availability',sensor,a.status_code,a.data,flush=True)
print('total',FireDetection.objects.count())
