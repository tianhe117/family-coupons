const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH});const page=await browser.newPage({viewport:{width:390,height:844}});const base=process.env.TEST_BASE_URL||'http://127.0.0.1:8081';
try{
 await page.goto(base);
 await page.route('**/api/unlock',route=>route.abort());for(const digit of '123456')await page.locator('[data-digit="'+digit+'"]').click();await page.getByText('网络连接中断，请检查网络后重试。',{exact:true}).waitFor();assert.equal(await page.locator('.secret').count(),0);await page.unroute('**/api/unlock');
 await page.route('**/api/unlock',async route=>{const response=await route.fetch();await new Promise(r=>setTimeout(r,600));await route.fulfill({response});});for(const digit of '123456')await page.locator('[data-digit="'+digit+'"]').click();await page.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));await page.waitForTimeout(4000);assert.equal(await page.locator('.secret').count(),0);await page.unroute('**/api/unlock');
 for(const digit of '123456')await page.locator('[data-digit="'+digit+'"]').click();await page.locator('#hold').waitFor();let writes=0;
 await page.route('**/api/use',async route=>{writes++;await route.fetch();await route.abort();});const b=await page.locator('#hold').boundingBox();await page.mouse.move(b.x+20,b.y+20);await page.mouse.down();await page.waitForTimeout(3200);await page.mouse.up();await page.getByRole('heading',{name:'确认使用结果'}).waitFor();assert.equal(await page.locator('.secret').count(),0);await page.reload();await page.getByRole('heading',{name:'确认使用结果'}).waitFor();for(const digit of '123456')await page.locator('[data-digit="'+digit+'"]').click();await page.getByRole('heading',{name:'券已用完',exact:true}).waitFor();assert.equal(writes,1);
 console.log('Network acceptance passed: offline unlock, background stale response, lost write response, refresh reconciliation, one write.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});

