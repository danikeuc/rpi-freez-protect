'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const crypto = require('node:crypto');
const {handle} = require('../../deployment/lighting/unifi-adapter.js');
const profile = {version:1,occurred_at_format:'utc',event_id_path:['id'],source_id_path:['camera'],occurred_at_path:['at'],event_type_path:['type'],allowed_event_types:['motion']};
const config = {enabled:'commissioned',ingressToken:'i'.repeat(32),cameraToken:'c'.repeat(32),allowedSources:'cam1',profile:JSON.stringify(profile)};
const at='2026-10-13T12:00:00Z', now=Date.parse(at);
function message(body={id:'event1',camera:'cam1',at,type:'motion'}) {
 return {req:{method:'POST',headers:{authorization:'Bearer '+config.ingressToken,'content-type':'application/json'},url:'/lighting/unifi'},res:{},_msgid:'trace',payload:body};
}
function fakeHttp(reply={accepted:true,duplicate:false}, status=200, behavior='reply') {
 const calls=[];
 return {calls,request(options,cb) {
  const req=new EventEmitter(); req.destroy=()=>{req.destroyed=true;req.emit('error',new Error('private upstream secret'));};
  req.end=body=>{calls.push({options,body}); if(behavior==='hang')return;
   queueMicrotask(()=>{const res=new EventEmitter();res.statusCode=status;res.destroy=()=>{};
    cb(res);res.emit('data',Buffer.from(typeof reply==='string'?reply:JSON.stringify(reply)));res.emit('end');});};
  return req;
 }};
}
async function run(msg=message(), cfg=config, http=fakeHttp(), extra={}) {
 await handle(msg,cfg,{http,crypto,now:()=>now,timeoutMs:20,...extra});return {msg,http};
}
test('forwards original identity and retains HTTP context on repeated deliveries',async()=>{
 const http=fakeHttp();const msg=message();const req=msg.req,res=msg.res;
 await run(msg,config,http);await run(message(),config,http);
 assert.equal(msg.req,req);assert.equal(msg.res,res);assert.equal(msg._msgid,'trace');
 assert.equal(msg.statusCode,200);assert.deepEqual(msg.payload,{accepted:true,duplicate:false});
 assert.equal(http.calls.length,2);assert.equal(http.calls[0].body,http.calls[1].body);
 assert.deepEqual(JSON.parse(http.calls[0].body),{event_id:'event1',source_id:'cam1',occurred_at:at});
 assert.equal(http.calls[0].options.hostname,'127.0.0.1');assert.equal(http.calls[0].options.port,8002);
 assert.equal(http.calls[0].options.path,'/api/v1/lights/events/unifi');
 assert.equal(http.calls[0].options.headers.Authorization,'Bearer '+config.cameraToken);
});
test('rejects missing/wrong auth, methods and URL credentials without forwarding',async()=>{
 for(const change of [m=>delete m.req.headers.authorization,m=>m.req.headers.authorization='Bearer wrong',m=>m.req.url+='?token=secret',m=>m.req.method='GET']) {
  const msg=message();change(msg);const {http}=await run(msg);assert.notEqual(msg.statusCode,200);assert.equal(http.calls.length,0);
 }
});
test('requires explicit commissioned profile and distinct credentials',async()=>{
 for(const cfg of [{...config,enabled:''},{...config,profile:''},{...config,cameraToken:config.ingressToken},{...config,profile:'{}'}]){
  const {msg,http}=await run(message(),cfg);assert.equal(msg.statusCode,503);assert.equal(http.calls.length,0);
 }
});
test('rejects identity, source, type, malformed time, freshness and oversized body',async()=>{
 for(const body of [{camera:'cam1',at,type:'motion'},{id:'x',camera:'other',at,type:'motion'},{id:'x',camera:'cam1',at,type:'other'},{id:'x',camera:'cam1',at:at.replace('Z',''),type:'motion'},{id:'x',camera:'cam1',at:'2026-02-30T12:00:00Z',type:'motion'},{id:'x',camera:'cam1',at:'2026-10-13T11:58:59Z',type:'motion'},{id:'x',camera:'cam1',at:'2026-10-13T12:00:06Z',type:'motion'},{id:'x'.repeat(5000),camera:'cam1',at,type:'motion'},'not-json']){
  const {msg,http}=await run(message(body));assert.notEqual(msg.statusCode,200);assert.equal(http.calls.length,0);
 }
});
test('bounded timeout, oversized/malformed response and errors produce sanitized one reply',async()=>{
 for(const http of [fakeHttp({},200,'hang'),fakeHttp('secret',200),fakeHttp('x'.repeat(9000),200),fakeHttp('private secret',409)]){
  const msg=message();await run(msg,config,http);assert.ok([409,503].includes(msg.statusCode));assert.deepEqual(msg.payload,{error:msg.statusCode===409?'controller_rejected':'controller_unavailable'});
  assert.equal(JSON.stringify(msg.payload).includes('secret'),false);
 }
});
test('controller duplicate/manual-ignore outcomes are preserved without policy or retry',async()=>{
 for(const value of [{accepted:false,duplicate:true},{accepted:false,duplicate:false}]){
  const {msg,http}=await run(message(),config,fakeHttp(value));assert.deepEqual(msg.payload,value);assert.equal(http.calls.length,1);
 }
});
test('redeploy cancellation destroys pending requests without retries',async()=>{
 const pending=new Set();const http=fakeHttp({},200,'hang');const msg=message();
 const result=handle(msg,config,{http,crypto,now:()=>now,timeoutMs:100,pending});
 assert.equal(pending.size,1);for(const cancel of pending)cancel();await result;
 assert.equal(msg.statusCode,503);assert.equal(pending.size,0);assert.equal(http.calls.length,1);
});

test('explicit nested profile converts original unix milliseconds without invention',async()=>{
 const cfg={...config,profile:JSON.stringify({...profile,event_id_path:['alarm','id'],source_id_path:['alarm','triggers','0','device'],occurred_at_path:['timestamp'],event_type_path:['alarm','triggers','0','key'],occurred_at_format:'unix_ms'})};
 const body={alarm:{id:'stable1',triggers:[{device:'cam1',key:'motion'}]},timestamp:now};
 const {msg,http}=await run(message(body),cfg);assert.equal(msg.statusCode,200);
 assert.deepEqual(JSON.parse(http.calls[0].body),{event_id:'stable1',source_id:'cam1',occurred_at:new Date(now).toISOString()});
 for(const invalid of [{...body,timestamp:String(now)},{...body,alarm:{...body.alarm,id:undefined}}]){
  const result=await run(message(invalid),cfg);assert.equal(result.msg.statusCode,422);assert.equal(result.http.calls.length,0);
 }
});
test('exported Function completes once and preserves context without logging',async()=>{
 const fs=require('node:fs');
 const flow=JSON.parse(fs.readFileSync(require('node:path').join(__dirname,'../../deployment/lighting/lighting-flow.json')));
 const fn=flow.find(n=>n.type==='function');const storage=new Map();
 const context={get:(key)=>storage.get(key),set:(key,value)=>storage.set(key,value)};
 new Function('context',fn.initialize)(context);
 const env={get:key=>({LIGHT_UNIFI_ENABLED:config.enabled,LIGHT_UNIFI_INGRESS_TOKEN:config.ingressToken,LIGHT_CAMERA_TOKEN:config.cameraToken,LIGHT_ALLOWED_SOURCES:config.allowedSources,LIGHT_UNIFI_PROFILE:config.profile})[key]};
 const msg=message({...message().payload,at:new Date().toISOString()});
 let sends=0,done=0;
 const complete=new Promise(resolve=>{
  const node={send:value=>{sends++;assert.equal(value,msg);},done:()=>{done++;resolve();}};
  new Function('msg','env','context','node','http','crypto',fn.func)(msg,env,context,node,fakeHttp(),crypto);
 });
 await complete;assert.equal(sends,1);assert.equal(done,1);assert.equal(msg.statusCode,200);
 new Function('context',fn.finalize)(context);assert.equal(storage.get('lightRequests').size,0);
});
