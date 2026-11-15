from django.db import models
from django.db.models import Q

class Region(models.Model):
    id = models.SlugField(primary_key=True, max_length=100)
    name = models.CharField(max_length=200)
    west = models.FloatField(null=True)
    south = models.FloatField(null=True)
    east = models.FloatField(null=True)
    north = models.FloatField(null=True)

class OverpassPair(models.Model):
    region = models.ForeignKey(Region, on_delete=models.PROTECT)
    date = models.DateField(db_index=True)
    modis_sobrevuelo = models.CharField(max_length=150)
    viirs_sobrevuelo = models.CharField(max_length=150)
    # Platforms are deliberately unknown unless supplied by a future source.
    modis_platform = models.CharField(max_length=100, null=True)
    viirs_platform = models.CharField(max_length=100, null=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['region','date','modis_sobrevuelo','viirs_sobrevuelo'], name='unique_region_overpass_pair')]

class DataImport(models.Model):
    source = models.CharField(max_length=255)
    checksum = models.CharField(max_length=64)
    version = models.CharField(max_length=100)
    imported_at = models.DateTimeField(auto_now_add=True)
    processed = models.PositiveIntegerField(default=0)
    inserted = models.PositiveIntegerField(default=0)
    unchanged = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, default='running')
    error = models.TextField(blank=True)

class H3Observation(models.Model):
    pair = models.ForeignKey(OverpassPair, on_delete=models.PROTECT, related_name='observations')
    data_import = models.ForeignKey(DataImport, on_delete=models.PROTECT)
    celda_h3 = models.CharField(max_length=15, db_index=True)
    resolucion_h3 = models.PositiveSmallIntegerField()
    version_armonizacion = models.CharField(max_length=100)
    metodo = models.CharField(max_length=150)
    estrato_temporal = models.CharField(max_length=40)
    coincidencia_original = models.CharField(max_length=20, db_index=True)
    coincidencia_qa = models.CharField(max_length=20)
    modis_utc = models.DateTimeField(null=True)
    viirs_utc = models.DateTimeField(null=True)
    modis_pixeles = models.PositiveIntegerField(null=True)
    modis_utiles = models.PositiveIntegerField(null=True)
    modis_nubes = models.PositiveIntegerField(null=True)
    modis_otros = models.PositiveIntegerField(null=True)
    modis_fuego = models.PositiveIntegerField(null=True)
    viirs_pixeles = models.PositiveIntegerField(null=True)
    viirs_utiles = models.PositiveIntegerField(null=True)
    viirs_nubes = models.PositiveIntegerField(null=True)
    viirs_reflejo_solar = models.PositiveIntegerField(null=True)
    viirs_otros = models.PositiveIntegerField(null=True)
    viirs_fuego = models.PositiveIntegerField(null=True)
    qa_originales = models.PositiveIntegerField(null=True)
    viirs_bowtie_residual = models.PositiveIntegerField(null=True)
    viirs_geo_no_nominal = models.PositiveIntegerField(null=True)
    viirs_fuego_sin_bowtie = models.PositiveIntegerField(null=True)
    viirs_fuego_qa_total = models.PositiveIntegerField(null=True)
    viirs_fuego_qa_nominal = models.PositiveIntegerField(null=True)
    modis_util_pct = models.FloatField(null=True)
    viirs_reflejo_solar_pct = models.FloatField(null=True)
    viirs_util_pct = models.FloatField(null=True)
    cobertura_compartida_pct = models.FloatField(null=True)
    diferencia_min = models.FloatField(null=True)
    area_modis_util_m2 = models.FloatField(null=True)
    area_viirs_util_m2 = models.FloatField(null=True)
    area_compartida_m2 = models.FloatField(null=True)
    cobertura_modis_pct = models.FloatField(null=True)
    cobertura_viirs_pct = models.FloatField(null=True)
    observacion_util_ambos = models.BooleanField(null=True)
    fuego_ambos = models.BooleanField(null=True)
    deteccion_solo_modis = models.BooleanField(null=True)
    deteccion_solo_viirs = models.BooleanField(null=True)
    fuego_solo_modis = models.BooleanField(null=True)
    fuego_solo_viirs = models.BooleanField(null=True)
    supera_umbral_exploratorio = models.BooleanField(null=True)
    comparacion_candidata = models.BooleanField(null=True)
    metodologia_validada = models.BooleanField(null=True)
    viirs_detecta = models.BooleanField(null=True)
    modis_detecta = models.BooleanField(null=True)
    viirs_detecta_sin_bowtie = models.BooleanField(null=True)
    alineacion_experimental = models.BooleanField(null=True)
    qa_viirs_disponible = models.BooleanField(null=True)
    calibracion_estadistica = models.BooleanField(null=True)
    geometria_validada = models.BooleanField(null=True)
    estado_comparacion = models.CharField(max_length=200, null=True)
    region = models.CharField(max_length=200, null=True)
    origen_datos = models.CharField(max_length=200, null=True)
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['pair','celda_h3','version_armonizacion'], name='unique_versioned_h3_observation'),
            models.CheckConstraint(condition=Q(resolucion_h3__lte=15), name='valid_h3_resolution'),
        ]
        ordering = ['pk']


class SatelliteSource(models.Model):
    id = models.CharField(primary_key=True, max_length=40)
    sensor = models.CharField(max_length=10)
    platform = models.CharField(max_length=30, null=True)

class DetectionImport(models.Model):
    source = models.ForeignKey(SatelliteSource, on_delete=models.PROTECT)
    date = models.DateField()
    area = models.CharField(max_length=150)
    status = models.CharField(max_length=40, default='PROCESAMIENTO_PENDIENTE')
    records = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)
    error = models.TextField(blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['source','date','area'],name='unique_firms_daily_import')]

class FireDetection(models.Model):
    fingerprint = models.CharField(max_length=64, unique=True)
    source = models.ForeignKey(SatelliteSource, on_delete=models.PROTECT)
    data_import = models.ForeignKey(DetectionImport, on_delete=models.PROTECT)
    observed_at = models.DateTimeField(db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    satellite = models.CharField(max_length=30)
    original = models.JSONField()
    ingested_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        indexes = [models.Index(fields=['source','observed_at'],name='firesight_source_time'),models.Index(fields=['latitude','longitude'],name='firesight_coordinates')]


class HarmonizationRun(models.Model):
    key = models.CharField(max_length=64, unique=True)
    region = models.ForeignKey(Region, on_delete=models.PROTECT)
    date = models.DateField(db_index=True)
    version = models.CharField(max_length=100)
    resolution = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=30)
    parameters = models.JSONField(default=dict)
    products = models.JSONField(default=list)
    records = models.PositiveIntegerField(default=0)
    error_type = models.CharField(max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

class FIRMSHarmonizationJob(models.Model):
    date = models.DateField()
    version = models.CharField(max_length=60, default='firms_operational_v1')
    status = models.CharField(max_length=30, default='PENDIENTE')
    modis_count = models.PositiveIntegerField(default=0)
    viirs_count = models.PositiveIntegerField(default=0)
    records = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict)
    error = models.CharField(max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['date','version'], name='unique_firms_harmonization_day')]


class FIRMSUnifiedDetection(models.Model):
    id = models.CharField(primary_key=True, max_length=64)
    job = models.ForeignKey(FIRMSHarmonizationJob, on_delete=models.PROTECT, related_name='detections')
    representative = models.ForeignKey(FireDetection, on_delete=models.PROTECT, related_name='operational_anchors')
    members = models.ManyToManyField(FireDetection, related_name='operational_products')
    latitude = models.FloatField()
    longitude = models.FloatField()
    observed_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20)
    modis_count = models.PositiveIntegerField()
    viirs_count = models.PositiveIntegerField()
    metadata = models.JSONField(default=dict)
    class Meta:
        indexes = [models.Index(fields=['latitude','longitude'], name='firms_unified_location')]


class Level2FirePixel(models.Model):
    h3_r7 = models.CharField(max_length=16,db_index=True,default='')
    id = models.CharField(primary_key=True,max_length=64)
    sensor = models.CharField(max_length=10)
    platform = models.CharField(max_length=30)
    granule = models.CharField(max_length=100)
    source_file = models.CharField(max_length=200)
    row = models.PositiveIntegerField()
    column = models.PositiveIntegerField()
    observed_at = models.DateTimeField(db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    fire_class = models.PositiveSmallIntegerField()
    qa = models.JSONField(default=dict)
    provenance = models.JSONField(default=dict)

class HarmonizedDetection(models.Model):
    canonical_key = models.CharField(max_length=64,db_index=True,default='')
    id = models.CharField(primary_key=True,max_length=64)
    pair = models.ForeignKey(OverpassPair,on_delete=models.PROTECT)
    version = models.CharField(max_length=150)
    method = models.CharField(max_length=100)
    status = models.CharField(max_length=30)
    representative = models.ForeignKey(Level2FirePixel,on_delete=models.PROTECT)
    observed_at = models.DateTimeField(db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    h3 = models.CharField(max_length=16)
    modis_count = models.PositiveIntegerField()
    viirs_count = models.PositiveIntegerField()
    assessment = models.JSONField(default=dict)
    class Meta:
        indexes = [models.Index(fields=['version','observed_at'],name='harm_pixel_version_time'),models.Index(fields=['latitude','longitude'],name='harm_pixel_coordinates')]

class HarmonizedDetectionMember(models.Model):
    detection = models.ForeignKey(HarmonizedDetection,on_delete=models.CASCADE,related_name='members')
    pixel = models.ForeignKey(Level2FirePixel,on_delete=models.PROTECT)
    pair = models.ForeignKey(OverpassPair,on_delete=models.PROTECT)
    version = models.CharField(max_length=150)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['pixel','pair','version'],name='one_pixel_per_pair_version')]
