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

try {
 await page.goto('http://localhost:5173',{waitUntil:'domcontentloaded'})
 await page.getByRole('combobox',{name:'País',exact:true}).fill('Mexico')
 await page.getByRole('option',{name:/México/}).click()
 const state=page.getByRole('combobox',{name:'Estado / provincia',exact:true})
 await expect(state).toBeEnabled({timeout:30000})
 await state.fill('Guerrero');await page.getByRole('option',{name:/Guerrero/}).click()
 const city=page.getByRole('combobox',{name:'Ciudad / municipio',exact:true})
 await expect(city).toBeEnabled({timeout:30000});await city.fill('Acapulco')
 await page.getByRole('option',{name:/Acapulco/}).first().click()
 await expect(city).toHaveValue(/Acapulco/)
 await page.waitForTimeout(2500)
 const location=await page.evaluate(()=>{const c=window.__tfViewers[0].camera.positionCartographic;return {lat:c.latitude*180/Math.PI,lon:c.longitude*180/Math.PI,height:c.height}})
 expect(location.lat).toBeGreaterThan(16);expect(location.lat).toBeLessThan(18);expect(location.lon).toBeGreaterThan(-101);expect(location.lon).toBeLessThan(-99)
 await page.screenshot({path:folder+'/mexico-guerrero-acapulco.png',fullPage:true})
 await page.getByRole('button',{name:'Vista mundial',exact:true}).click()
 await expect(state).toBeDisabled();await expect(city).toBeDisabled()
 const result={passed:true,path:'Mexico / Guerrero / Acapulco',location,errors,warnings,httpErrors}
 await fs.writeFile(folder+'/geography-results.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2))
} catch(error){await page.screenshot({path:folder+'/geography-failure.png',fullPage:true});throw error} finally {await browser.close()}
