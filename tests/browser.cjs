// Optional browser acceptance runner. No frontend build or npm project required.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH});
 const page=await browser.newPage({viewport:{width:390,height:844}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const base=process.env.TEST_BASE_URL||'http://127.0.0.1:8081';
 async function login(admin=false){if(admin){await page.locator('#password').fill('admin');await page.locator('#login button').click();}else{for(const digit of '123456')await page.locator('[data-digit="'+digit+'"]').click();}}
 async function waitFor(selector){await page.locator(selector).waitFor();}
 async function hold(ms){const b=await page.locator('#hold').boundingBox();await page.mouse.move(b.x+30,b.y+30);await page.mouse.down();await page.waitForTimeout(ms);await page.mouse.up();}
 try{
 await page.goto(base+'/?view=admin');await login(true);await waitFor('#single');
 await page.locator('#batch').fill('001234567890 000123\n009876543210 000456');await page.locator('#preview').click();await page.locator('#import').click();await page.getByText('已保存。',{exact:true}).waitFor();
 await page.locator('#batch').fill('001234567890 0001');await page.locator('#preview').click();assert.equal(await page.locator('#import').isVisible(),false);
 await page.goto(base);
 for(const width of [320,375,390,393,414,430,440]){await page.setViewportSize({width,height:width===320?568:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));const last=await page.locator('.delete').boundingBox();assert(last.y+last.height<=(width===320?568:844));}
 await page.setViewportSize({width:390,height:844});await page.locator('[data-digit="1"]').click();await page.locator('[data-digit="2"]').click();await page.locator('.delete').click();assert.equal(await page.locator('.pin-dot.filled').count(),1);await page.locator('.delete').click();assert.equal(await page.locator('input').count(),0);fs.mkdirSync('test-results',{recursive:true});await page.screenshot({path:'test-results/mobile-pin.png',fullPage:true});
for(const digit of '999999')await page.locator('[data-digit="'+digit+'"]').click();await page.getByText('密码不正确，请重试',{exact:true}).waitFor();assert.equal(await page.locator('.secret').count(),0);
 await login();await waitFor('#hold');assert.equal(await page.locator('.secret').nth(1).textContent(),'000123');
 for(const width of [320,375,390,393,414,430,440]){await page.setViewportSize({width,height:width===320?568:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`overflow at ${width}`);const b=await page.locator('#hold').boundingBox();assert(b.y+b.height<=(width===320?568:844),`button below fold ${width}`);}
 await page.setViewportSize({width:390,height:844});fs.mkdirSync('test-results',{recursive:true});await page.screenshot({path:'test-results/mobile-coupon.png',fullPage:true});
 await page.locator('#hold').click();await hold(200);assert.equal(await page.locator('.secret').count(),2);
 const b=await page.locator('#hold').boundingBox();await page.mouse.move(b.x+30,b.y+30);await page.mouse.down();await page.mouse.move(0,0);await page.waitForTimeout(3100);await page.mouse.up();assert.equal(await page.locator('.secret').count(),2);
 await page.reload();await waitFor('.pin-pad');await login();await waitFor('#hold');assert.equal(await page.locator('.secret').first().textContent(),'0012 3456 7890');
 await page.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));await waitFor('.pin-pad');assert.equal(await page.locator('.secret').count(),0);await login();await waitFor('#hold');
 await hold(3200);await waitFor('.pin-pad');assert.equal(await page.locator('.secret').count(),0);await login();await waitFor('#hold');assert.equal(await page.locator('.secret').nth(1).textContent(),'000456');
 await hold(3200);await page.getByRole('heading',{name:'券已用完',exact:true}).waitFor();
 await page.goto(base+'/?view=admin');await login(true);await waitFor('#single');await page.locator('[data-restore]').first().click();await page.locator('#confirm').click();await page.getByText('已保存。',{exact:true}).waitFor();assert.equal(await page.locator('[data-edit]').count(),1);
 await page.locator('[data-edit]').click();await page.locator('#edit-number').fill('000001');await page.getByRole('button',{name:'保存修改',exact:true}).click();await page.getByText('已保存。',{exact:true}).waitFor();assert.equal(await page.locator('.row strong').first().textContent(),'000001');
 await page.setViewportSize({width:1280,height:900});await page.screenshot({path:'test-results/admin.png',fullPage:true});
 assert.deepEqual(errors,[]);console.log('Browser acceptance passed: 7 widths, login, cancellation, use, reload, background, empty, batch, edit, restore.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
