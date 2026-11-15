from rest_framework import serializers
from .models import H3Observation, Region

class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ['id','name','west','south','east','north']

class ObservationSerializer(serializers.ModelSerializer):
    fecha = serializers.DateField(source='pair.date', read_only=True)
    region_id = serializers.CharField(source='pair.region_id', read_only=True)
    region_nombre = serializers.CharField(source='pair.region.name', read_only=True)
    modis_sobrevuelo = serializers.CharField(source='pair.modis_sobrevuelo', read_only=True)
    viirs_sobrevuelo = serializers.CharField(source='pair.viirs_sobrevuelo', read_only=True)
    class Meta:
        model = H3Observation
        exclude = ['data_import']
        read_only_fields = ['id','pair']
