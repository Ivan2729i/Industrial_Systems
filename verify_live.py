import os,sys
sys.path.insert(0,'backend');os.environ['DJANGO_SETTINGS_MODULE']='config.settings'
import django;django.setup()
from rest_framework.test import APIRequestFactory
from analysis.detections_api import detections
from analysis.models import FireDetection
cases=[('guerrero','2024-04-16','2024-04-16','-100.05,16.95,-99.45,17.55'),('tabasco','2024-04-19','2024-04-19','-93.55,17.45,-92.95,18.05'),('range','2024-04-02','2024-04-16','-100.05,16.95,-99.45,17.55'),('california','2024-04-16','2024-04-16','-122.5,38,-122,38.5')]
for label,start,end,bbox in cases:
 for sensor in ['modis','viirs']:
  params={'start_date':start,'end_date':end,'sensor':sensor,'bbox':bbox,'retrieve':'true'}
  r=detections(APIRequestFactory().get('/api/v1/detections/',params))
  print(label,sensor,r.status_code,'count',r.data.get('count'),'retrieval',r.data.get('retrieval'),flush=True)
  before=FireDetection.objects.count(); repeat=detections(APIRequestFactory().get('/api/v1/detections/',params));print('repeat_delta',FireDetection.objects.count()-before,flush=True)
