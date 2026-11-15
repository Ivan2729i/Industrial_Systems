import { chromium } from '@playwright/test'
import fs from 'node:fs/promises'
await fs.mkdir('test-results/visual',{recursive:true})
const browser=await chromium.launch({channel:'chrome',headless:true})
const page=await browser.newPage({viewport:{width:1440,height:1080},deviceScaleFactor:1})
const errors=[];const warnings=[];const failed=[]
page.on('pageerror',e=>errors.push(e.message))
page.on('console',msg=>{if(msg.type()==='error')errors.push(msg.text());if(msg.type()==='warning')warnings.push(msg.text())})
page.on('response',response=>{if(response.status()>=400)failed.push({status:response.status(),url:response.url()})})
await page.addInitScript(()=>{
 window.__tfViewers=[]
 let cesium
 Object.defineProperty(window,'Cesium',{configurable:true,get(){return cesium},set(value){
   const Viewer=new Proxy(value.Viewer,{construct(target,args){const viewer=Reflect.construct(target,args);window.__tfViewers.push(viewer);return viewer}})
   cesium=new Proxy(value,{get(target,key){return key==='Viewer'?Viewer:Reflect.get(target,key)}})
 }})
})
await page.goto('http://localhost:5173',{waitUntil:'domcontentloaded'})
await page.waitForTimeout(5000)
await page.screenshot({path:'test-results/visual/initial.png',fullPage:true})
console.log(JSON.stringify({title:await page.title(),text:(await page.locator('body').innerText()).slice(0,4000),viewers:await page.evaluate(()=>window.__tfViewers.length),errors,warnings,failed},null,2))
await browser.close()
