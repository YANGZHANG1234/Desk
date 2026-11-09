const fs=require('fs'),vm=require('vm'),assert=require('assert');
const code=fs.readFileSync('.system/app/literature_map.js','utf8');let queue=new Map(),seq=0,time=0;
const nodes=[{id:'a',label:'Rivera2026JCP',collected:true},{id:'b',label:'Taylor2007JIE',collected:false},{id:'c',label:'Other2020JCP',collected:true}],edges=[{id:'relation-1',source:'a',target:'b'}],positions={a:[100,100],b:[102,100],c:[450,420]};
const elements=nodes.map(n=>({dataset:{node:n.id},attrs:{},classList:{contains:()=>false},text:{style:{}},setAttribute(k,v){this.attrs[k]=v;},querySelector(){return this.text;}}));const edgeElement={attrs:{},setAttribute(k,v){this.attrs[k]=v;}};
const svg={isConnected:true,classList:{contains:()=>false},style:{getPropertyValue:()=>''},querySelectorAll:q=>q==='[data-node]'?elements:[edgeElement]};
const ctx={Math,Map,Object,requestAnimationFrame:f=>{const id=++seq;queue.set(id,f);return id;},cancelAnimationFrame:id=>queue.delete(id)};vm.createContext(ctx);vm.runInContext(code.slice(code.indexOf('function academicForce(')),ctx);
const sim=ctx.academicForce(nodes,edges,positions,svg,600,550,()=>{});
function frames(n){for(let i=0;i<n;i++){const batch=[...queue.values()];queue.clear();time+=34;batch.forEach(f=>f(time));}}
frames(90);const distance=(a,b)=>Math.hypot(positions[a][0]-positions[b][0],positions[a][1]-positions[b][1]);assert(distance('a','b')>20);assert(distance('a','b')<distance('a','c'));assert(edgeElement.attrs.d.startsWith('M'));
sim.pin='a';positions.a=[320,240];sim.restart();frames(20);assert.deepEqual(positions.a,[320,240]);sim.pin=null;sim.paused=true;const paused=JSON.stringify(positions);frames(5);assert.equal(JSON.stringify(positions),paused);sim.paused=false;sim.restart();frames(20);assert.notEqual(JSON.stringify(positions),paused);sim.stop();assert.equal(queue.size,0);assert(Object.values(positions).flat().every(Number.isFinite));console.log('Live forces, linked-node proximity, drag pinning, pause/resume and cleanup passed');
