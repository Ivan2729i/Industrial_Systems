// Real API + Cesium data source regression. This is NOT a WebGL visual test.
import assert from 'node:assert/strict'
import { cellToLatLng } from 'h3-js'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
const resolveFromCesium=createRequire(import.meta.resolve('cesium'))
const engineEntry=pathToFileURL(resolveFromCesium.resolve('@cesium/engine'))
const {default:CustomDataSource}=await import(new URL('./Source/DataSources/CustomDataSource.js',engineEntry))
const {default:Cartesian3}=await import(new URL('./Source/Core/Cartesian3.js',engineEntry))
import { setLayerVisibility } from '../src/layerVisibility.ts'

const base='http://localhost:8000/api/v1'
const query='start_date=2024-04-16&end_date=2024-04-16&bbox=-100.05,16.95,-99.45,17.55&limit=5000'
async function get(path){const response=await fetch(base+path);assert.equal(response.status,200);return response.json()}
const [modis,viirs,product,context]=await Promise.all([
  get('/detections/?sensor=modis&'+query),get('/detections/?sensor=viirs&'+query),
  get('/harmonization/detections/?start=2024-04-16&end=2024-04-16&limit=1000'),
  get('/harmonization/?date=2024-04-16&region=guerrero&limit=1000'),
])
const layers={modis:new CustomDataSource('modis'),viirs:new CustomDataSource('viirs'),harmonized:new CustomDataSource('harmonized'),h3:new CustomDataSource('h3')}
for(const [name,data] of [['modis',modis],['viirs',viirs],['harmonized',product]])
  for(const row of data.results)layers[name].entities.add({id:String(row.id),position:Cartesian3.fromDegrees(row.longitude,row.latitude)})
for(const row of context.results){const [lat,lon]=cellToLatLng(row.celda_h3);layers.h3.entities.add({id:String(row.id),position:Cartesian3.fromDegrees(lon,lat)})}
const counts=Object.fromEntries(Object.entries(layers).map(([name,layer])=>[name,layer.entities.values.length]))
assert.ok(counts.harmonized>0)
for(let cycle=0;cycle<10;cycle++) for(const active of ['modis','viirs','harmonized','h3','modis','harmonized','viirs']) {
  setLayerVisibility(layers,active)
  for(const [name,layer] of Object.entries(layers)) {assert.equal(layer.show,name===active);assert.equal(layer.entities.values.length,counts[name])}
}
console.log(JSON.stringify({cycles:10,transitions:70,counts,webgl_test:false}))
