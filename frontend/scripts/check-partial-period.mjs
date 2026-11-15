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
try{
 await page.goto('http://localhost:5173',{waitUntil:'domcontentloaded'});await active('modis',7411)
 // Draw a real geographic rectangle strictly inside the persisted pilot bbox.
 await dates('2024-04-16');await active('modis',7411)
 await page.evaluate(()=>{const C=window.Cesium,v=window.__tfViewers[0];v.camera.setView({destination:C.Cartesian3.fromDegrees(-99.75,17.25,160000),orientation:{heading:0,pitch:-Math.PI/2,roll:0}})})
 await page.getByRole('button',{name:'Seleccionar área',exact:true}).click()
 const corners=await page.evaluate(()=>{const C=window.Cesium,v=window.__tfViewers[0];return [[-100,17],[-99.5,17.5]].map(([lon,lat])=>{const p=C.SceneTransforms.worldToWindowCoordinates(v.scene,C.Cartesian3.fromDegrees(lon,lat));return{x:p.x,y:p.y}})})
 const box=await page.locator('.globe canvas').first().boundingBox();await page.mouse.move(box.x+corners[0].x,box.y+corners[0].y);await page.mouse.down();await page.mouse.move(box.x+corners[1].x,box.y+corners[1].y,{steps:8});await page.mouse.up()
 const bbox=await page.getByRole('status').last().textContent();const match=bbox.match(/Área: ([^·]+)/);expect(match).toBeTruthy();const area=match[1].trim()

 await page.route('**/api/v1/detections/**',route=>(new URL(route.request().url()).searchParams.get('start_date')<='2024-04-05'&&new URL(route.request().url()).searchParams.get('end_date')>='2024-04-05')?route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Fallo controlado de un día'})}):route.continue())
 await dates('2024-04-02','2024-04-08')
 await expect(page.getByRole('status').last()).toContainText('6/7 días completos',{timeout:60000})
 await expect(page.getByRole('status').last()).toContainText('2024-04-05')
 const visibleDates=await page.evaluate(()=>{const C=window.Cesium,v=window.__tfViewers[0],dates=[];for(const p of v.scene.primitives._primitives)if(p instanceof C.PointPrimitiveCollection&&p.show)for(let i=0;i<p.length;i++)dates.push(p.get(i).id.attributes.observed_at.slice(0,10));return dates})
 expect(visibleDates.length).toBeGreaterThan(0);expect(visibleDates.every(d=>d>='2024-04-02'&&d<='2024-04-08'&&d!=='2024-04-05')).toBe(true)
 console.log(JSON.stringify({passed:true,retained_valid_records:visibleDates.length,completed_days:6,requested_days:7,failed_day:'2024-04-05'}))
}finally{await browser.close()}
