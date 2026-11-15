import { chromium, expect } from '@playwright/test'
import fs from 'node:fs/promises'
const folder='test-results/phase1'
await fs.mkdir(folder,{recursive:true})
const browser=await chromium.launch({channel:'chrome',headless:true})
const page=await browser.newPage({viewport:{width:1440,height:1080}})
const errors=[],warnings=[],httpErrors=[]
page.on('pageerror',e=>errors.push(e.message))
page.on('console',m=>{if(m.type()==='error')errors.push(m.text());if(m.type()==='warning')warnings.push(m.text())})
page.on('response',r=>{if(r.status()>=400)httpErrors.push({status:r.status(),url:r.url()})})
await page.addInitScript(()=>{
  let cesium;window.__tfViewers=[]
  Object.defineProperty(window,'Cesium',{configurable:true,get(){return cesium},set(value){
    const Viewer=new Proxy(value.Viewer,{construct(target,args){const viewer=Reflect.construct(target,args);window.__tfViewers.push(viewer);return viewer}})
    cesium=new Proxy(value,{get(target,key){return key==='Viewer'?Viewer:Reflect.get(target,key)}})
  }})
})

const dates=async(start,end=start)=>{await page.getByLabel('Desde (UTC)',{exact:true}).fill(start);await page.getByLabel('Hasta (UTC)',{exact:true}).fill(end)}
const active=async(sensor,count)=>page.waitForFunction(({sensor,count})=>{const v=window.__tfViewers.at(-1);return v?.scene.primitives._primitives.some(p=>p instanceof window.Cesium.PointPrimitiveCollection && p.show && p.length===count && p.get(0)?.id?.attributes?.sensor===sensor)},{sensor,count},{timeout:90000})
const tab=async(name)=>page.getByRole('tab',{name:new RegExp(name)}).click()

const shot=async name=>page.screenshot({path:folder+'/'+name+'.png',fullPage:true})
const point=async sensor=>page.evaluate(sensor=>{const C=window.Cesium,v=window.__tfViewers[0],c=v.scene.primitives._primitives.find(p=>p instanceof C.PointPrimitiveCollection&&p.show&&p.length&&p.get(0).id?.attributes.sensor===sensor),p=c.get(0),a=p.id.attributes;v.camera.setView({destination:C.Cartesian3.fromDegrees(a.longitude,a.latitude,80000),orientation:{heading:0,pitch:-Math.PI/2,roll:0}});v.scene.requestRender();return a},sensor)
const clickPoint=async sensor=>{
 const attributes=await point(sensor);await page.waitForTimeout(1800);await page.waitForFunction(()=>window.__tfViewers[0].scene.globe.tilesLoaded,null,{timeout:45000});await page.waitForTimeout(500)
 const xy=await page.evaluate(sensor=>{const C=window.Cesium,v=window.__tfViewers[0],c=v.scene.primitives._primitives.find(p=>p instanceof C.PointPrimitiveCollection&&p.show&&p.length&&p.get(0).id?.attributes.sensor===sensor),p=C.SceneTransforms.worldToWindowCoordinates(v.scene,c.get(0).position);return{x:p.x,y:p.y}},sensor)
 const box=await page.locator('.globe canvas').first().boundingBox();await page.mouse.click(box.x+xy.x,box.y+xy.y);return attributes
}
try{
 await page.goto('http://localhost:5173',{waitUntil:'domcontentloaded'});await active('modis',7411)
 await page.waitForTimeout(3500);await shot('world-labels')
 for(const [sensor,count] of [['modis',7411],['viirs',45487]]){
  await tab(sensor.toUpperCase());await dates('2024-04-16');await active(sensor,count)
  await clickPoint(sensor)
  const card=page.getByRole('complementary',{name:'Detalle de detección térmica'})
  await expect(card).toContainText(sensor.toUpperCase());await expect(card).toContainText('UTC');await expect(card).toContainText('Fuente de datos')
  await expect(card.locator('details')).not.toHaveAttribute('open','')
  await card.getByText('Ver detalles técnicos',{exact:true}).click();await expect(card.locator('pre')).toContainText('source')
  await card.getByText('Ver detalles técnicos',{exact:true}).click();await shot(sensor+'-card')
  await page.keyboard.press('Escape');await expect(card).toHaveCount(0)
 }
 await tab('MODIS');await active('modis',7411)
 await page.getByRole('button',{name:'Vista mundial',exact:true}).click();await page.waitForTimeout(1800)
 await page.getByRole('combobox',{name:'Representación FIRMS',exact:true}).selectOption('density')
 const heat=async()=>page.waitForFunction(()=>{const C=window.Cesium,v=window.__tfViewers[0];return Array.from({length:v.imageryLayers.length},(_,i)=>v.imageryLayers.get(i)).some(l=>l.show && l.imageryProvider instanceof C.SingleTileImageryProvider)})
 await heat();await page.waitForTimeout(1200);await shot('world-density')
 const raster=await page.evaluate(async()=>{const C=window.Cesium,v=window.__tfViewers[0],l=Array.from({length:v.imageryLayers.length},(_,i)=>v.imageryLayers.get(i)).find(l=>l.show&&l.imageryProvider instanceof C.SingleTileImageryProvider),image=await l.imageryProvider.requestImage(0,0,0),canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;const c=canvas.getContext('2d');c.drawImage(image,0,0);const values=c.getImageData(0,0,canvas.width,canvas.height).data;let strong=0;for(let i=3;i<values.length;i+=4)if(values[i]>100)strong++;return{strong,width:image.width,height:image.height}})
 expect(raster.strong).toBeGreaterThan(1000)
 await dates('2024-04-17');await heat();await page.waitForTimeout(1000)
 await tab('VIIRS');await dates('2024-04-17');await heat();await page.waitForTimeout(1200);await shot('viirs-density')
 await page.getByRole('combobox',{name:'Representación FIRMS',exact:true}).selectOption('points');await active('viirs',44705)
 await tab('Armonizaci');await dates('2024-04-16')
 await page.waitForFunction(()=>window.__tfViewers[0].dataSources.getByName('harmonized-Level2-points')[0].entities.values.length===3101)
 const id=await page.evaluate(()=>{const C=window.Cesium,v=window.__tfViewers[0],e=v.dataSources.getByName('harmonized-Level2-points')[0].entities.values[0],p=C.Cartographic.fromCartesian(e.position.getValue(v.clock.currentTime));v.camera.setView({destination:C.Cartesian3.fromRadians(p.longitude,p.latitude,80000),orientation:{heading:0,pitch:-Math.PI/2,roll:0}});return e.id})
 await page.waitForTimeout(2200)
 const xy=await page.evaluate(id=>{const C=window.Cesium,v=window.__tfViewers[0],e=v.dataSources.getByName('harmonized-Level2-points')[0].entities.getById(id),p=C.SceneTransforms.worldToWindowCoordinates(v.scene,e.position.getValue(v.clock.currentTime));return{x:p.x,y:p.y}},id)
 const box=await page.locator('.globe canvas').first().boundingBox();await page.mouse.click(box.x+xy.x,box.y+xy.y)
 await expect(page.locator('.detection-card')).toContainText('Armonizado');await shot('harmonized-card')
 await page.keyboard.press('Escape')
 expect(await page.locator('.map-legend').count()).toBe(0)
 await page.getByRole('button',{name:'Abrir menú de navegación',exact:true}).click()
 expect(await page.locator('.side-menu nav button').count()).toBe(3)
 await expect(page.getByRole('button',{name:/Analítica/})).toBeDisabled();await expect(page.getByRole('button',{name:/Blockchain/})).toBeDisabled()
 await page.keyboard.press('Escape');await page.setViewportSize({width:390,height:844});await shot('mobile')
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(391)
 expect(errors).toEqual([]);expect(warnings).toEqual([]);expect(httpErrors).toEqual([])
 console.log(JSON.stringify({passed:true,raster,one_viewer:await page.evaluate(()=>window.__tfViewers.length===1),errors,warnings,httpErrors}))
}catch(error){await shot('ui-failure');console.log(JSON.stringify({error:error.message,errors,warnings,httpErrors}));throw error}finally{await browser.close()}
