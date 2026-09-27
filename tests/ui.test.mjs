import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import fs from 'node:fs';
// JSDOM is a test-only dependency; the deployed application has none.
const require=createRequire(import.meta.url);
const {JSDOM}=require(process.env.JSDOM_PATH||'jsdom');
test('page flow: login, create multi-session course, show detail, preview and restore',async()=>{
 const dom=new JSDOM(fs.readFileSync(new URL('../public/index.html',import.meta.url),'utf8'),{url:'http://localhost/'});
 Object.assign(globalThis,{document:dom.window.document,window:dom.window,localStorage:dom.window.localStorage,matchMedia:()=>({matches:false}),confirm:()=>true});
 dom.window.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','')};dom.window.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open')};
 const nativeSetInterval=globalThis.setInterval,nativeSetTimeout=globalThis.setTimeout,timers=[];
 globalThis.setInterval=(fn,ms)=>{const t=nativeSetInterval(fn,ms);timers.push(t);return t.unref()};
 globalThis.setTimeout=(fn,ms)=>{const t=nativeSetTimeout(fn,ms);timers.push(t);return t};
 let data={settings:{title:'测试学期',startDate:'2026-09-07',totalWeeks:20,timezone:'Asia/Shanghai',dayStart:'08:00',dayEnd:'20:00'},courses:[]},revision=1,authenticated=false;
 globalThis.fetch=async(url,options={})=>{if(url.endsWith('login'))authenticated=true;if(options.method==='PUT'){assert.equal(authenticated,true);const body=JSON.parse(options.body);assert.equal(body.revision,revision);data=body.data;revision++}return {ok:true,json:async()=>({data:structuredClone(data),revision,authenticated})}};
 await import('../public/app.mjs');await new Promise(r=>setImmediate(r));
 const $=s=>document.querySelector(s), submit=f=>f.dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));
 assert.match($('#schedule').textContent,/新的学期/);$('#add-course').click();assert.equal($('#login-dialog').open,true);
 $('#login-form').elements.password.value='test-password';submit($('#login-form'));await new Promise(r=>setImmediate(r));
 assert.equal($('#course-dialog').open,true);const f=$('#course-form');f.elements.name.value='<b>线性代数</b>';f.elements.location.value='A302';$('#add-session').click();assert.equal($('#sessions').children.length,2);
 const second=$('#sessions').children[1];second.querySelector('.session-day').value='3';second.querySelector('.session-weeks').value='1-16单';submit(f);await new Promise(r=>setImmediate(r));
 assert.equal(data.courses.length,1);assert.equal(data.courses[0].sessions.length,2);assert.equal($('#course-dialog').open,false);assert.equal($('#course-list b'),null);
 $('#course-list [data-course]').click();assert.equal($('#detail-title').textContent,'<b>线性代数</b>');$('#detail-dialog .close').click();
 $('#preview-button').click();assert.equal(document.querySelectorAll('.course-index-item').length,6);$('#preview-button').click();assert.equal(document.querySelectorAll('.course-index-item').length,1);assert.equal(data.courses.length,1);
 $('#settings-button').click();assert.equal($('#settings-dialog').open,true);assert.equal($('#settings-form').elements.title.value,'测试学期');$('#settings-dialog .close').click();$('#list-view').click();assert.equal($('#list-view').getAttribute('aria-pressed'),'true');
 timers.forEach(t=>{clearTimeout(t);clearInterval(t)});globalThis.setInterval=nativeSetInterval;globalThis.setTimeout=nativeSetTimeout;dom.window.close();
});
