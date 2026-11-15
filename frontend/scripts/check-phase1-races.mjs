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
try{
 await page.goto('http://localhost:5173',{waitUntil:'domcontentloaded'});await active('modis',7411)
 let delayed=0
 await page.route('**/api/v1/detections/**',async route=>{
  const u=new URL(route.request().url())
  if(u.searchParams.get('start_date')==='2024-04-17' && !u.searchParams.has('offset')){
   delayed++;const response=await route.fetch();await new Promise(resolve=>setTimeout(resolve,2200));await route.fulfill({response}).catch(()=>{})
  }else await route.continue()
 })
 await dates('2024-04-17');await page.waitForTimeout(300);await dates('2024-04-16');await active('modis',7411)
 await page.waitForTimeout(2500);await active('modis',7411)
 await dates('2024-04-17');await tab('VIIRS');await dates('2024-04-16');await active('viirs',45487)
 await page.waitForTimeout(2500);await active('viirs',45487)
 await tab('MODIS');await active('modis',8562)
 await page.unroute('**/api/v1/detections/**')
 await dates('2024-04-16');await active('modis',7411)
 // Inject a network failure against a real date; no simulated detections are used.
 const initial=await page.evaluate(()=>window.__tfViewers[0].scene.primitives._primitives.filter(p=>p instanceof window.Cesium.PointPrimitiveCollection).map(p=>p.length))
 await page.route('**/api/v1/detections/**',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Prueba controlada de red'})}))
 await dates('2024-04-15');await expect(page.getByRole('status').filter({hasText:/No fue posible actualizar|Error consultando FIRMS/})).toBeVisible()
 const retained=await page.evaluate(()=>window.__tfViewers[0].scene.primitives._primitives.filter(p=>p instanceof window.Cesium.PointPrimitiveCollection).map(p=>p.length))
 expect(retained).toEqual(initial)
 await page.unroute('**/api/v1/detections/**');await dates('2024-04-16');await active('modis',7411)
 expect(delayed).toBeGreaterThan(0)
 await page.route('**/api/v1/harmonized-detections/**',async route=>{const u=new URL(route.request().url());if(u.searchParams.get('start')==='2024-04-17'){const response=await route.fetch();await new Promise(resolve=>setTimeout(resolve,2200));await route.fulfill({response}).catch(()=>{})}else await route.continue()})
 await tab('Armonizaci');await page.waitForTimeout(300);await dates('2024-04-16')
 const harmony=()=>page.waitForFunction(()=>{const d=window.__tfViewers[0].dataSources.getByName('harmonized-Level2-points')[0];return d.show&&d.entities.values.length===3101})
 await harmony();await page.waitForTimeout(2400);await harmony()
 await page.unroute('**/api/v1/harmonized-detections/**')
 console.log(JSON.stringify({passed:true,delayed,stale_responses_rejected:true,retained_on_error:true,recovery:true,errors,warnings}))
}catch(error){await page.screenshot({path:folder+'/race-failure.png',fullPage:true});throw error}finally{await browser.close()}
