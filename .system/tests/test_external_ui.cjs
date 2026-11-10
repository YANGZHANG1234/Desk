// Briefing view renders fabricated export records read-only, escaped and with safe links only.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('.system/app/desk.js','utf8');
const ctx={E:s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),I:()=>'',localDate:d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`,dateText:d=>d,route:'briefing'};
ctx.today=()=>ctx.localDate(new Date());ctx.pageHeading=t=>`<h1>${t}</h1>`;vm.createContext(ctx);
vm.runInContext(src.slice(src.indexOf('let externalData='),src.indexOf('async function loadExternal(')).replace('let externalData=null,externalState=\'idle\';','var externalData=null,externalState=\'idle\';'),ctx);
const now=new Date(),iso=new Date(now.getTime()+3600e3).toISOString(),later=new Date(now.getTime()+3*864e5).toISOString();
const rec=(o)=>({source:'paicc',source_label:'PAICC',read_only:true,demo:false,updated_at:iso,...o});
ctx.externalData={export_root:'/tmp/x',sources:[
 {label:'PAICC',exists:true,manifest:{exported_at:iso,schema_version:1},warnings:[],records:[
  rec({source_id:'m',kind:'meeting',title:'Sync <b>today</b>',start_at:iso}),
  rec({source_id:'m2',kind:'meeting',title:'Future meeting',start_at:later}),
  rec({source_id:'t',kind:'task',title:'Reply',deadline_at:later,summary_zh:'示例',summary_en:'Sample',link:'message://%3Cfake@example.invalid%3E'}),
  rec({source_id:'d',kind:'task',title:'Finished thing',status:'done'}),
  rec({source_id:'x',kind:'task',title:'Evil',link:'javascript:alert(1)'}),
  rec({source_id:'b',kind:'briefing',title:'Briefing',body:'Line one\n<script>x</script>'}),
  rec({source_id:'ms',kind:'milestone',title:'Chapter draft'})]},
 {label:'FIC',exists:false,manifest:null,warnings:['Unsupported schema_version 2'],records:[
  {source:'fic',source_label:'FIC',read_only:true,demo:true,source_id:'f',kind:'finance_daily',title:'Daily'},
  {source:'fic',source_label:'FIC',read_only:true,demo:false,source_id:'l',kind:'learning',title:'Duration'}]}]};
ctx.externalState='ready';
const html=ctx.externalView();
for(const id of ['schedule','tasks','briefing','milestones','finance','learning'])assert(html.includes(`id="external-${id}"`),'missing section '+id);
assert(!html.includes('external-other'),'empty other section hidden');
assert(html.includes('Sync &lt;b&gt;today&lt;/b&gt;')&&!html.includes('<script>x'),'content is escaped');
assert(html.includes('href="message://%3Cfake@example.invalid%3E"')&&html.includes('Open in Mail'),'mail link rendered');
assert(!html.includes('javascript:'),'unsafe link dropped');
assert(!html.includes('Finished thing'),'done tasks hidden');
assert.equal((html.match(/>Read-only</g)||[]).length,8,'every record marked read-only');
assert(html.includes('演示 Demo'),'demo badge kept');
assert(html.includes('Unsupported schema_version 2'),'schema warning shown');
assert(html.indexOf('Sync &lt;b&gt;')<html.indexOf('Upcoming')&&html.indexOf('Upcoming')<html.indexOf('Future meeting'),'today before upcoming');
assert(!/contenteditable|<input|<textarea|data-action="(save|delete)/.test(html),'no editing controls');
ctx.externalData={export_root:'/tmp/x',sources:[{label:'PAICC',exists:true,manifest:{generated_at:iso},warnings:[],records:[
 rec({source_id:'pt',kind:'task',title:'Reply to sample',title_zh:'回复示例',status:'INBOX',priority:'P1',deadline_kind:'none',next_action:'Draft reply',email_sender:'Sample Sender',email_subject:'Sample subject',link:'message://%3Cs@example.invalid%3E'}),
 rec({source_id:'pm',kind:'meeting',title:'Online sync',status:'CANCELLED',start_at:iso,needs_review:false,online_meeting_url:'https://teams.example.invalid/x'}),
 rec({source_id:'pb',kind:'briefing',briefing_kind:'daily',period_start:'2026-11-10',period_end:'2026-11-10',body:'中文 / English'})]},
 {label:'FIC',exists:true,manifest:null,warnings:[],records:[{source:'fic',source_label:'FIC',read_only:true,demo:true,source_id:'fb',kind:'briefing',title:'FIC sample daily'}]}]};
let paicc=ctx.externalView(),sec=id=>paicc.slice(paicc.indexOf(`id="external-${id}"`),paicc.indexOf('</section>',paicc.indexOf(`id="external-${id}"`)));
assert(paicc.includes('回复示例')&&paicc.includes('From Sample Sender')&&paicc.includes('Draft reply')&&!paicc.includes('none ·'),'PAICC task fields');
assert(paicc.includes('Daily briefing · 2026-11-10'),'briefing title from period');
assert(paicc.includes('>Cancelled<')&&paicc.includes('Join online')&&!paicc.includes('Needs review'),'meeting status and online link');
assert(sec('finance').includes('FIC sample daily')&&!sec('briefing').includes('FIC sample daily'),'FIC briefings shown under finance');
assert(paicc.includes('exported'),'generated_at accepted for display');
ctx.externalData={export_root:'/tmp/x',sources:[{label:'PAICC',exists:false,manifest:null,warnings:[],records:[]},{label:'FIC',exists:false,manifest:null,warnings:[],records:[]}]};
assert(ctx.externalView().includes('No exported records yet'),'empty state');
console.log('Briefing view: sections, read-only badges, demo marks, escaping, safe links and empty state passed');
