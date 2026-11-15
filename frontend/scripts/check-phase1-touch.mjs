import { chromium, expect } from '@playwright/test'
import fs from 'node:fs/promises'
const folder='test-results/phase1'
await fs.mkdir(folder,{recursive:true})
const browser=await chromium.launch({channel:'chrome',headless:true})
const page=await browser.newPage({viewport:{width:390,height:844},deviceScaleFactor:2,isMobile:true,hasTouch:true})
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
 await page.evaluate(()=>{const C=window.Cesium,v=window.__tfViewers[0],c=v.scene.primitives._primitives.find(p=>p instanceof C.PointPrimitiveCollection&&p.show&&p.length),a=c.get(0).id.attributes;v.camera.setView({destination:C.Cartesian3.fromDegrees(a.longitude,a.latitude,80000),orientation:{heading:0,pitch:-Math.PI/2,roll:0}});v.scene.requestRender()})
 const canvas=page.locator('.globe canvas').first();await canvas.scrollIntoViewIfNeeded();await page.waitForTimeout(1800)
 const xy=await page.evaluate(()=>{const C=window.Cesium,v=window.__tfViewers[0],c=v.scene.primitives._primitives.find(p=>p instanceof C.PointPrimitiveCollection&&p.show&&p.length),p=C.SceneTransforms.worldToWindowCoordinates(v.scene,c.get(0).position);return{x:p.x,y:p.y}})
 const box=await canvas.boundingBox();await page.touchscreen.tap(box.x+xy.x,box.y+xy.y)
 await expect(page.locator('.detection-card')).toContainText('MODIS');await page.screenshot({path:folder+'/touch-card.png',fullPage:true})
 const resolution=await page.evaluate(()=>{const v=window.__tfViewers[0];return {canvas:v.canvas.width,css:v.canvas.clientWidth,dpr:devicePixelRatio}})
 expect(resolution.canvas/resolution.css).toBeCloseTo(2,1)
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(391)
 expect(errors).toEqual([]);console.log(JSON.stringify({passed:true,touch_selection:true,resolution,errors,warnings,httpErrors}))
}finally{await browser.close()}
