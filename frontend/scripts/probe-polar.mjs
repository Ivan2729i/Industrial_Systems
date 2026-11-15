import { chromium, expect } from '@playwright/test'
import fs from 'node:fs/promises'
const folder='test-results/operational'
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

await page.goto('http://localhost:5173',{waitUntil:'domcontentloaded'})
await page.waitForTimeout(2500)
await page.evaluate(()=>{const C=window.Cesium,v=window.__tfViewers[0];v.camera.setView({destination:C.Cartesian3.fromDegrees(0,89.9,20000000)});v.scene.requestRender()})
await page.waitForTimeout(2000)
await page.screenshot({path:folder+'/pole-with-terrain.png',fullPage:true})
await page.evaluate(()=>{const C=window.Cesium,v=window.__tfViewers[0];v.terrainProvider=new C.EllipsoidTerrainProvider();v.scene.requestRender()})
await page.waitForTimeout(2500)
await page.screenshot({path:folder+'/pole-ellipsoid.png',fullPage:true})
console.log(JSON.stringify({errors,warnings,httpErrors}))
await browser.close()
