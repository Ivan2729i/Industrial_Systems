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
 for(const [sensor,count16,count17] of [['modis',7411,8562],['viirs',45487,44705]]){
  await tab(sensor.toUpperCase());await dates('2024-04-16');await active(sensor,count16)
  const camera=await page.evaluate(()=>{const p=window.__tfViewers[0].camera.position;return [p.x,p.y,p.z]})
  await dates('2024-04-17');await active(sensor,count17)
  await dates('2024-04-16','2024-04-17');await active(sensor,count16+count17)
  await dates('2024-04-16');await active(sensor,count16)
  for(let i=0;i<3;i++){await dates('2024-04-17');await dates('2024-04-16')}
  await active(sensor,count16)
  expect(await page.evaluate(()=>{const p=window.__tfViewers[0].camera.position;return [p.x,p.y,p.z]})).toEqual(camera)
 }
 await tab('Armonizaci');await dates('2024-04-16')
 const harmony=async(count)=>page.waitForFunction(count=>{const d=window.__tfViewers[0].dataSources.getByName('harmonized-Level2-points')[0];return d.show && d.entities.values.length===count},count,{timeout:45000})
 await harmony(3101)
 const expected17=await (await page.request.get('http://localhost:8000/api/v1/harmonized-detections/?start=2024-04-17&end=2024-04-17&aggregate=true')).json()
 await dates('2024-04-17');await harmony(expected17.results.length)
 const expectedRange=await (await page.request.get('http://localhost:8000/api/v1/harmonized-detections/?start=2024-04-16&end=2024-04-17&aggregate=true')).json()
 await dates('2024-04-16','2024-04-17');await harmony(expectedRange.results.length)
 expect(expectedRange.count).toBe(100361)
 await dates('2024-04-16');await harmony(3101)
 for(let i=0;i<3;i++){await dates('2024-04-17');await dates('2024-04-16')}
 await harmony(3101)
 expect(await page.evaluate(()=>window.__tfViewers.length)).toBe(1)
 await page.screenshot({path:folder+'/dates-stable.png',fullPage:true})
 expect(errors).toEqual([]);expect(httpErrors).toEqual([])
 console.log(JSON.stringify({passed:true,full_modis:7411,full_viirs:45487,range_modis:15973,range_viirs:90192,one_viewer:true,errors,warnings,httpErrors}))
}catch(error){await page.screenshot({path:folder+'/failure.png',fullPage:true});console.log(JSON.stringify({error:error.message,errors,warnings,httpErrors}));throw error}finally{await browser.close()}
