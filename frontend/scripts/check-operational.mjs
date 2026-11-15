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
const api=async query=>{const response=await page.request.get('http://localhost:8000/api/v1/harmonized-detections/?'+new URLSearchParams(query));expect(response.ok()).toBe(true);return response.json()}
const active=async(name,count)=>page.waitForFunction(({name,count})=>{const v=window.__tfViewers.at(-1),d=v?.dataSources.getByName(name)[0];return d?.show && d.entities.values.length===count},{name,count},{timeout:45000})
const tab=async name=>page.getByRole('tab',{name:new RegExp(name)}).click()
const dates=async day=>{await page.getByLabel('Desde (UTC)',{exact:true}).fill(day);await page.getByLabel('Hasta (UTC)',{exact:true}).fill(day)}
const shot=async name=>page.screenshot({path:`${folder}/${name}.png`,fullPage:true})
try{
  const world=await api({start:'2024-04-16',end:'2024-04-16',aggregate:'true'})
  expect(world.count).toBe(47164)
  expect(world.results.reduce((n,p)=>n+p.represented_count,0)).toBe(world.count)
  const continents={}
  for(const [name,bbox] of Object.entries({Africa:'-20,-35,55,38',Asia:'65,0,145,55',Oceania:'110,-45,155,-10',America:'-125,-55,-35,50',Europe:'-15,35,45,70'})){
    const result=await api({start:'2024-04-16',end:'2024-04-16',bbox,aggregate:'true'});expect(result.count).toBeGreaterThan(0);continents[name]=result.count
  }
  await page.goto('http://localhost:5173',{waitUntil:'domcontentloaded'})
  await active('firms-modis',5000)
  await tab('Armonizaci');await expect(page.getByLabel('Desde (UTC)',{exact:true})).toHaveValue('2024-04-17');await dates('2024-04-16');await active('harmonized-Level2-points',world.results.length)
  await expect(page.getByText('No hay detecciones armonizadas procesadas para este período y área.')).toHaveCount(0)
  await page.waitForTimeout(2500);await shot('global-red-points')
  const position=()=>page.evaluate(()=>{const p=window.__tfViewers[0].camera.position;return [p.x,p.y,p.z]})
  const before=await position()
  for(let n=0;n<10;n++){
    await tab('MODIS');await active('firms-modis',5000)
    await tab('VIIRS');await active('firms-viirs',5000)
    await tab('Armonizaci');await active('harmonized-Level2-points',world.results.length)
  }
  expect(await position()).toEqual(before)
  expect(await page.evaluate(()=>window.__tfViewers.length)).toBe(1)
  const country=page.getByRole('combobox',{name:'País',exact:true})
  await country.click();expect(await page.locator('#geo-options-country [role=option]').count()).toBe(249);await country.press('Escape')
  const african=world.results.find(p=>p.latitude>-25 && p.latitude<0 && p.longitude>15 && p.longitude<40)
  expect(african).toBeTruthy()
  await page.evaluate(p=>{const C=window.Cesium,v=window.__tfViewers[0];v.camera.setView({destination:C.Cartesian3.fromDegrees(p.longitude,p.latitude,150000),orientation:{heading:0,pitch:-Math.PI/2,roll:0}});v.scene.requestRender()},african)
  await page.waitForTimeout(4500)
  const xy=await page.evaluate(id=>{const C=window.Cesium,v=window.__tfViewers[0],e=v.dataSources.getByName('harmonized-Level2-points')[0].entities.getById('harmonized-'+id);const p=C.SceneTransforms.worldToWindowCoordinates(v.scene,e.position.getValue(v.clock.currentTime));return{x:p.x,y:p.y}},african.id)
  const canvas=page.locator('.globe canvas').first(),box=await canvas.boundingBox()
  await page.mouse.click(box.x+xy.x,box.y+xy.y)
  await expect(page.locator('.cell-detail')).toContainText('Integración operativa FIRMS')
  await expect(page.locator('.cell-detail')).toContainText(african.members[0].pixel.granule)
  await shot('africa-source-selection')
  await page.locator('.cell-detail').getByRole('button',{name:'Cerrar',exact:true}).click()
  await page.getByRole('button',{name:'Buscar en esta área',exact:true}).click()
  await page.waitForFunction(()=>{const d=window.__tfViewers[0].dataSources.getByName('harmonized-Level2-points')[0];return d.show && d.entities.values.length>0 && d.entities.values.length<3101})
  await page.getByRole('button',{name:'Vista mundial',exact:true}).click();await active('harmonized-Level2-points',world.results.length)
  await dates('2024-04-17')
  const world17=await api({start:'2024-04-17',end:'2024-04-17',aggregate:'true'})
  await active('harmonized-Level2-points',world17.results.length)
  await dates('2024-04-16');await active('harmonized-Level2-points',world.results.length)
  await page.getByRole('combobox',{name:'Producto armonizado',exact:true}).selectOption('level2');await active('harmonized-Level2-points',24)
  await page.getByRole('combobox',{name:'Producto armonizado',exact:true}).selectOption('operational');await active('harmonized-Level2-points',world.results.length)
  await tab('MODIS');await active('firms-modis',5000)
  await page.getByRole('combobox',{name:'Representación FIRMS',exact:true}).selectOption('density');await active('firms-modis',0)
  await page.waitForTimeout(1800);await shot('density-imagery-overlay')
  await page.getByRole('combobox',{name:'Representación FIRMS',exact:true}).selectOption('points');await active('firms-modis',5000)
  await tab('Armonizaci');await active('harmonized-Level2-points',world.results.length)
  await page.evaluate(()=>{const C=window.Cesium,v=window.__tfViewers[0];v.camera.setView({destination:C.Cartesian3.fromDegrees(0,89.9,20000000)});v.scene.requestRender()})
  await page.waitForTimeout(3500);await shot('polar-earth')
  await page.setViewportSize({width:390,height:844});await shot('mobile')
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(391)
  expect(errors).toEqual([]);expect(warnings).toEqual([]);expect(httpErrors).toEqual([])
  const result={passed:true,cycles:10,one_viewer:true,world:{modis:world.jobs[0].modis_count,viirs:world.jobs[0].viirs_count,unified:world.count,map_groups:world.results.length,counts:world.counts},continents,second_date:world17.count,errors,warnings,httpErrors}
  await fs.writeFile(`${folder}/results.json`,JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2))
}catch(error){await shot('failure');console.log(JSON.stringify({error:error.message,errors,warnings,httpErrors}));throw error}
finally{await browser.close()}
