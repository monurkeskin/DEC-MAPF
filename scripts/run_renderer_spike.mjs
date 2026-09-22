import { chromium } from '../frontend/node_modules/playwright/index.mjs'
import { spawn } from 'node:child_process'
import { writeFile } from 'node:fs/promises'
const server=spawn(process.execPath,['node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5176'],{cwd:new URL('../frontend',import.meta.url),stdio:'pipe'})
let browser
try{
 for(let i=0;i<80;i++){try{if((await fetch('http://127.0.0.1:5176/spike.html')).ok)break}catch{}await new Promise(r=>setTimeout(r,100))}
 browser=await chromium.launch({channel:'chrome',headless:true});const page=await browser.newPage({viewport:{width:1000,height:850}})
 await page.goto('http://127.0.0.1:5176/spike.html');await page.waitForFunction(()=>document.querySelector('#receipt')?.textContent?.startsWith('{'),{timeout:30000})
 const receipt=JSON.parse(await page.locator('#receipt').textContent());await writeFile(process.argv[2],JSON.stringify(receipt,null,2));await page.screenshot({path:process.argv[2].replace('.json','.png'),fullPage:true});console.log(JSON.stringify(receipt))
}finally{if(browser)await browser.close();server.kill('SIGTERM')}
