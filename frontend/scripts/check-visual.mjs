import { chromium, expect } from '@playwright/test'
import fs from 'node:fs/promises'
await fs.mkdir('test-results/visual',{recursive:true})
const browser=await chromium.launch({channel:'chrome',headless:true})
const page=await browser.newPage({viewport:{width:1440,height:1080},deviceScaleFactor:1})
const errors=[],warnings=[],httpErrors=[]
page.on('pageerror',e=>errors.push(e.message))
page.on('console',msg=>{if(msg.type()==='error')errors.push(msg.text());if(msg.type()==='warning')warnings.push(msg.text())})
page.on('response',response=>{if(response.status()>=400)httpErrors.push({status:response.status(),url:response.url()})})
await page.addInitScript(()=>{
 window.__tfViewers=[];let cesium
 Object.defineProperty(window,'Cesium',{configurable:true,get(){return cesium},set(value){const Viewer=new Proxy(value.Viewer,{construct(target,args){const v=Reflect.construct(target,args);window.__tfViewers.push(v);return v}});cesium=new Proxy(value,{get(target,key){return key==='Viewer'?Viewer:Reflect.get(target,key)}})}})
})
const layerState=()=>page.evaluate(()=>{const v=window.__tfViewers.at(-1);return {viewers:window.__tfViewers.length,webgl2:v.scene.context.webgl2,terrain:v.terrainProvider instanceof window.Cesium.ArcGISTiledElevationTerrainProvider,layers:Array.from({length:v.dataSources.length},(_,i)=>{const d=v.dataSources.get(i);return {name:d.name,show:d.show,count:d.entities.values.length}})}})
async function active(name,count){await page.waitForFunction(({name,count})=>{const v=window.__tfViewers.at(-1);const d=v?.dataSources.getByName(name)[0];return d?.show && d.entities.values.length===count},{name,count},{timeout:30000})}
async function tab(name){await page.getByRole('tab',{name:new RegExp(name)}).click()}
async function dates(start,end){await page.getByLabel('Desde (UTC)',{exact:true}).fill(start);await page.getByLabel('Hasta (UTC)',{exact:true}).fill(end)}
async function screenshot(name){await page.screenshot({path:'test-results/visual/'+name+'.png',fullPage:true})}
try{
 await page.goto('http://localhost:5173',{waitUntil:'domcontentloaded'})
 await active('firms-modis',5000)
 await tab('Armonizaci')
 await active('harmonized-Level2-points',32)
 await screenshot('harmonized-latest-global')
 await dates('2024-04-16','2024-04-16');await active('harmonized-Level2-points',24)
 const before=await page.evaluate(()=>{const v=window.__tfViewers.at(-1);return [v.camera.position.x,v.camera.position.y,v.camera.position.z]})
 for(let i=0;i<10;i++){
  await tab('MODIS');await active('firms-modis',5000)
  await tab('VIIRS');await active('firms-viirs',5000)
  await tab('Armonizaci');await active('harmonized-Level2-points',24)
  const state=await layerState();expect(state.viewers).toBe(1)
  expect(state.layers.filter(l=>l.show).map(l=>l.name)).toEqual(['harmonized-Level2-points'])
 }
 const after=await page.evaluate(()=>{const v=window.__tfViewers.at(-1);return [v.camera.position.x,v.camera.position.y,v.camera.position.z]})
 expect(after).toEqual(before)
 const data=await (await page.request.get('http://localhost:8000/api/v1/harmonization/detections/?date=2024-04-16&bbox=31,-15,31.3,-14.7&limit=1000')).json()
 const associated=data.results.find(r=>r.status==='ASOCIADA')
 await page.evaluate(({lat,lon})=>{const C=window.Cesium,v=window.__tfViewers.at(-1);v.camera.setView({destination:C.Cartesian3.fromDegrees(lon,lat,18000),orientation:{heading:0,pitch:-Math.PI/2,roll:0}});v.scene.requestRender()},{lat:associated.latitude,lon:associated.longitude})
 await page.waitForTimeout(1800)
 await page.waitForFunction(()=>window.__tfViewers.at(-1).scene.globe.tilesLoaded,null,{timeout:45000})
 await page.waitForTimeout(2000)
 const xy=await page.evaluate(id=>{const C=window.Cesium,v=window.__tfViewers.at(-1),d=v.dataSources.getByName('harmonized-Level2-points')[0],e=d.entities.getById('harmonized-'+id),p=C.SceneTransforms.worldToWindowCoordinates(v.scene,e.position.getValue(v.clock.currentTime));return {x:p.x,y:p.y}},associated.id)
 const canvas=page.locator('.globe canvas').first(),box=await canvas.boundingBox()
 await page.mouse.click(box.x+xy.x,box.y+xy.y)
 await expect(page.locator('.cell-detail')).toContainText('ASOCIADA')
 await expect(page.locator('.cell-detail')).toContainText('A2024107.1210')
 await expect(page.locator('.cell-detail')).toContainText('A2024107.1206')
 await screenshot('zambia-associated-real-pixels')
 await page.locator('.cell-detail').getByRole('button',{name:'Cerrar',exact:true}).click()
 await dates('2024-04-19','2024-04-19');await active('harmonized-Level2-points',32)
 await dates('2024-04-16','2024-04-16');await active('harmonized-Level2-points',24)
 await page.getByRole('combobox',{name:'Visualizaci'}).selectOption('h3')
 await page.waitForFunction(()=>window.__tfViewers.at(-1).dataSources.getByName('harmonization-h3')[0].show)
 await page.getByRole('combobox',{name:'Visualizaci'}).selectOption('points');await active('harmonized-Level2-points',24)
 // Actual rectangle drag uses geographic picking; Escape restores camera input.
 await page.getByRole('button',{name:'Seleccionar área',exact:true}).click()
 const drawBox=await canvas.boundingBox()
 await page.mouse.move(drawBox.x+drawBox.width*.35,drawBox.y+drawBox.height*.35)
 await page.mouse.down();await page.mouse.move(drawBox.x+drawBox.width*.65,drawBox.y+drawBox.height*.65,{steps:8});await page.mouse.up()
 await expect(page.getByRole('button',{name:'Limpiar área',exact:true})).toBeVisible()
 expect(await page.evaluate(()=>window.__tfViewers.at(-1).scene.screenSpaceCameraController.enableInputs)).toBe(true)
 await page.getByRole('button',{name:'Limpiar área',exact:true}).click();await active('harmonized-Level2-points',24)
 await tab('MODIS');await active('firms-modis',5000)
 await page.getByRole('combobox',{name:'Representación FIRMS',exact:true}).selectOption('density');await active('firms-modis',1)
 await page.getByRole('button',{name:'Vista mundial',exact:true}).click();await page.waitForTimeout(2200)
 await screenshot('firms-density')
 await page.getByRole('combobox',{name:'Representación FIRMS',exact:true}).selectOption('points');await active('firms-modis',5000)
 await tab('Armonizaci');await active('harmonized-Level2-points',24)
 await page.mouse.move(drawBox.x+drawBox.width*.45,drawBox.y+drawBox.height*.45);await page.mouse.wheel(0,250);await page.waitForTimeout(600)
 await active('harmonized-Level2-points',24)
 await page.setViewportSize({width:390,height:844});await page.waitForTimeout(600);await screenshot('mobile-harmonized')
 const overflow=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:innerWidth}))
 expect(overflow.scroll).toBeLessThanOrEqual(overflow.width+1)
 expect(errors).toEqual([]);expect(warnings).toEqual([]);expect(httpErrors).toEqual([])
 console.log(JSON.stringify({passed:true,rectangle_drag:true,density_roundtrip:true,wheel_zoom:true,cycles:10,tab_transitions:30,layerState:await layerState(),errors,warnings,httpErrors,overflow},null,2))
 await fs.writeFile('test-results/visual/results.json',JSON.stringify({passed:true,rectangle_drag:true,density_roundtrip:true,wheel_zoom:true,cycles:10,layerState:await layerState(),errors,warnings,httpErrors,overflow},null,2))
} catch(error){await screenshot('failure');console.log(JSON.stringify({passed:false,error:error.message,layerState:await layerState(),errors,warnings,httpErrors},null,2));throw error}
finally{await browser.close()}
