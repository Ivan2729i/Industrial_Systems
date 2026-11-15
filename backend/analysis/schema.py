COUNT_FIELDS = ['modis_pixeles', 'modis_utiles', 'modis_nubes', 'modis_otros', 'modis_fuego', 'viirs_pixeles', 'viirs_utiles', 'viirs_nubes', 'viirs_reflejo_solar', 'viirs_otros', 'viirs_fuego', 'qa_originales', 'viirs_bowtie_residual', 'viirs_geo_no_nominal', 'viirs_fuego_sin_bowtie', 'viirs_fuego_qa_total', 'viirs_fuego_qa_nominal']
FLOAT_FIELDS = ['modis_util_pct', 'viirs_reflejo_solar_pct', 'viirs_util_pct', 'cobertura_compartida_pct', 'diferencia_min', 'area_modis_util_m2', 'area_viirs_util_m2', 'area_compartida_m2', 'cobertura_modis_pct', 'cobertura_viirs_pct']
BOOL_FIELDS = ['observacion_util_ambos', 'fuego_ambos', 'deteccion_solo_modis', 'deteccion_solo_viirs', 'fuego_solo_modis', 'fuego_solo_viirs', 'supera_umbral_exploratorio', 'comparacion_candidata', 'metodologia_validada', 'viirs_detecta', 'modis_detecta', 'viirs_detecta_sin_bowtie', 'alineacion_experimental', 'qa_viirs_disponible', 'calibracion_estadistica', 'geometria_validada']
TEXT_FIELDS = ['estado_comparacion', 'region', 'origen_datos']
CLASSES = ("AMBOS", "SOLO_MODIS", "SOLO_VIIRS", "NINGUNO", "NO_EVALUABLE")
STRATA = ("A_0_A_5_MIN", "B_MAS_5_A_15_MIN", "NO_EVALUABLE")
