import { chromium, expect } from '@playwright/test'
import fs from 'node:fs/promises'
const folder='test-results/perf'
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
    const Viewer=new Proxy(value.Viewer,{construct(target,args){const viewer=Reflect.construct(target,args);window.__tfViewers.push(viewer);window.__frames=[];viewer.scene.postRender.addEventListener(()=>{const counts={modis:0,viirs:0,harmonized:0};for(const p of viewer.scene.primitives._primitives)if(p instanceof value.PointPrimitiveCollection&&p.show&&p.length){const sensor=p.get(0).id?.attributes?.sensor;if(sensor in counts)counts[sensor]+=p.length}const h=viewer.dataSources.getByName('harmonized-Level2-points')[0];if(h?.show)counts.harmonized=h.entities.values.length;window.__frames.push({at:performance.now(),counts});if(window.__frames.length>500)window.__frames.shift()});return viewer}})
    cesium=new Proxy(value,{get(target,key){return key==='Viewer'?Viewer:Reflect.get(target,key)}})
  }})
})


const dates=async(s,e=s)=>{await page.getByLabel('Desde (UTC)',{exact:true}).fill(s);await page.getByLabel('Hasta (UTC)',{exact:true}).fill(e)}
const active=async(sensor,count,t=0)=>page.waitForFunction(({sensor,count,t})=>window.__frames?.some(f=>f.at>=t&&f.counts[sensor]===count),{sensor,count,t},{timeout:90000})
const results=[]
async function measure(name,sensor,s,e,count){const t=await page.evaluate(()=>{performance.clearResourceTimings();return performance.now()});await dates(s,e);await active(sensor,count,t);const result=await page.evaluate(({sensor,count,t})=>{const f=window.__frames.find(f=>f.at>=t&&f.counts[sensor]===count),r=performance.getEntriesByType('resource').filter(r=>r.name.includes('/api/')&&r.decodedBodySize>0);return {frame_ms:f.at-t,decoded_bytes:r.reduce((n,r)=>n+r.decodedBodySize,0),transfer_ms:r.reduce((n,r)=>n+r.responseEnd-r.responseStart,0),ttfb_ms:r.reduce((n,r)=>n+r.responseStart-r.requestStart,0),requests:r.length}},{sensor,count,t});results.push({name,...result})}
try{
 await page.goto('http://localhost:5173',{waitUntil:'domcontentloaded'});await active('modis',7411)
 await measure('modis_new_day','modis','2024-04-17','2024-04-17',8562)
 await measure('modis_cached_day','modis','2024-04-16','2024-04-16',7411)
 await measure('modis_two_days','modis','2024-04-16','2024-04-17',15973)
 await page.getByRole('tab',{name:'VIIRS',exact:true}).click();await active('viirs',90192)
 await measure('viirs_day','viirs','2024-04-16','2024-04-16',45487)
 await measure('viirs_cached_range','viirs','2024-04-16','2024-04-17',90192)
 const cameraBefore=await page.evaluate(()=>{const p=window.__tfViewers[0].camera.position;return [p.x,p.y,p.z]})
 for(let i=0;i<10;i++){await page.getByRole('tab',{name:'MODIS',exact:true}).click();await page.waitForTimeout(40);await page.getByRole('tab',{name:'VIIRS',exact:true}).click();await page.waitForTimeout(40);await page.getByRole('tab',{name:/Armonizaci/}).click();await dates('2024-04-16');await active('harmonized',3101);await page.getByRole('tab',{name:'MODIS',exact:true}).click()}
 expect(await page.evaluate(()=>window.__tfViewers.length)).toBe(1)
 expect(await page.evaluate(()=>{const p=window.__tfViewers[0].camera.position;return [p.x,p.y,p.z]})).toEqual(cameraBefore)
 // Draw a real geographic rectangle strictly inside the persisted pilot bbox.
 await dates('2024-04-16');await active('modis',7411)
 await page.evaluate(()=>{const C=window.Cesium,v=window.__tfViewers[0];v.camera.setView({destination:C.Cartesian3.fromDegrees(-99.75,17.25,160000),orientation:{heading:0,pitch:-Math.PI/2,roll:0}})})
 await page.getByRole('button',{name:'Seleccionar área',exact:true}).click()
 const corners=await page.evaluate(()=>{const C=window.Cesium,v=window.__tfViewers[0];return [[-100,17],[-99.5,17.5]].map(([lon,lat])=>{const p=C.SceneTransforms.worldToWindowCoordinates(v.scene,C.Cartesian3.fromDegrees(lon,lat));return{x:p.x,y:p.y}})})
 const box=await page.locator('.globe canvas').first().boundingBox();await page.mouse.move(box.x+corners[0].x,box.y+corners[0].y);await page.mouse.down();await page.mouse.move(box.x+corners[1].x,box.y+corners[1].y,{steps:8});await page.mouse.up()
 const bbox=await page.getByRole('status').last().textContent();const match=bbox.match(/Área: ([^·]+)/);expect(match).toBeTruthy();const area=match[1].trim()
 for(const sensor of ['modis','viirs']){await page.getByRole('tab',{name:sensor.toUpperCase(),exact:true}).click();for(const n of [1,3,7,15]){const end=new Date(Date.UTC(2024,3,2+n-1)).toISOString().slice(0,10);const response=await page.request.get('http://localhost:8000/api/v1/detections/?'+new URLSearchParams({sensor,start_date:'2024-04-02',end_date:end,bbox:area,detail:'true'}));const d=await response.json();expect(d.missing_dates).toEqual([]);await measure(sensor+'_'+n+'d',sensor,'2024-04-02',end,d.count)}}
 await fs.writeFile(folder+'/after-browser.json',JSON.stringify({results,stages:await page.evaluate(()=>performance.getEntriesByType('measure').filter(e=>e.name.startsWith('TerraFlare:')).map(e=>({name:e.name,ms:e.duration}))),errors,warnings,httpErrors},null,2));console.log(JSON.stringify({passed:true,cycles:10,area,results,errors,warnings,httpErrors}))
}finally{await browser.close()}
