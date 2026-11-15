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
const active=async(sensor,count)=>page.waitForFunction(({sensor,count})=>{const v=window.__tfViewers.at(-1);return v?.scene.primitives._primitives.filter(p=>p instanceof window.Cesium.PointPrimitiveCollection && p.show && p.length && p.get(0)?.id?.attributes?.sensor===sensor).reduce((n,p)=>n+p.length,0)===count},{sensor,count},{timeout:90000})
const tab=async(name)=>page.getByRole('tab',{name:new RegExp(name)}).click()
try{
 await page.goto('http://localhost:5173',{waitUntil:'domcontentloaded'});await active('modis',7411)
 let attempts=0
 await page.route('**/api/v1/detections/**',async route=>{const u=new URL(route.request().url());if(u.searchParams.get('start_date')==='2024-04-17'&&attempts++<2)await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'CONSULTA_EN_CURSO',count:0,results:[]})});else await route.continue()})
 await dates('2024-04-17');await active('modis',8562);expect(attempts).toBeGreaterThanOrEqual(3)
 console.log(JSON.stringify({passed:true,attempts,automatic_recovery_without_tab_change:true}))
}finally{await browser.close()}
