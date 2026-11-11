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
assert(paicc.includes('回复示例')&&paicc.includes('来自 Sample Sender')&&paicc.includes('Draft reply')&&!paicc.includes('none ·'),'PAICC task fields');
assert(paicc.includes('Daily briefing · 2026-11-10'),'briefing title from period');
assert(paicc.includes('Cancelled 已取消')&&paicc.includes('Join online')&&!paicc.includes('Needs review'),'meeting status and online link');
assert(sec('finance').includes('FIC sample daily')&&!sec('briefing').includes('FIC sample daily'),'FIC briefings shown under finance');
assert(paicc.includes('exported'),'generated_at accepted for display');
// Batch 1: display_title, merged tasks, recurring meetings, bilingual briefing, Today overview.
const todayISO=ctx.today(),at=h=>{let d=new Date();d.setHours(h,0,0,0);return d.toISOString()};
ctx.externalData={export_root:'/tmp/x',sources:[{source:'paicc',label:'PAICC',exists:true,warnings:[],records:[
 rec({source_id:'mt',kind:'task',display_title:'Sample Sender：3 件事',title:'Sample Sender: 3 items',title_zh:'Sample Sender：3 件事',priority:'P2',task_count:3,open_count:2,summary_zh:'示例邮件摘要',link:'message://%3Cm@example.invalid%3E',subtasks:[{source_id:'s1',display_title:'回复示例一',status:'INBOX',priority:'P2'},{source_id:'s2',display_title:'完成示例二',status:'done'},{source_id:'s3',display_title:'示例三',status:'INBOX',deadline_at:at(18)}]}),
 rec({source_id:'t2',kind:'task',display_title:'登录示例银行',title:'Log in to sample bank',task_count:1,open_count:1,priority:'P1'}),
 rec({source_id:'t3',kind:'task',display_title:'已完成任务',task_count:1,open_count:0,status:'done'}),
 rec({source_id:'gm',kind:'meeting',display_title:'Group Meeting',title:'Group Meeting',start_at:at(13),end_at:at(14),location:'Room 1',recurring:true,recurrence_zh:'每周二 13:00',upcoming_count:9,upcoming_starts:[at(13),'2099-01-01T13:00:00Z']}),
 rec({source_id:'cm',kind:'meeting',display_title:'Seminar',title:'Canceled: Seminar',status:'CANCELLED',start_at:at(15),online_meeting_url:'https://teams.example.invalid/j'}),
 rec({source_id:'br',kind:'briefing',briefing_kind:'daily',period_start:todayISO,period_end:todayISO,body:'# 今日简报\n\n- 中文要点\n\n———— English ————\n\n- English point'})]},
 {source:'fic',label:'FIC',exists:true,warnings:[],records:[{source:'fic',source_label:'FIC',read_only:true,demo:true,source_id:'fd',kind:'finance_daily',title:'演示 Demo · 金融日报 sample',date:todayISO,updated_at:iso}]}]};
let ov=ctx.todayOverview(),bv=ctx.externalView();
assert(ov.indexOf('id="overview-brief"')<ov.indexOf('id="overview-meetings"')&&ov.indexOf('id="overview-meetings"')<ov.indexOf('id="overview-tasks"')&&ov.indexOf('id="overview-tasks"')<ov.indexOf('id="overview-finance"'),'overview order');
let ovBrief=ov.slice(ov.indexOf('id="overview-brief"'),ov.indexOf('id="overview-meetings"'));
assert(ovBrief.includes('中文要点')&&ovBrief.includes('<summary>English</summary>')&&ovBrief.indexOf('English point')>ovBrief.indexOf('<summary>English</summary>'),'briefing Chinese expanded, English folded');
assert(ov.includes('每周二 13:00 · 之后还有 8 次')&&ov.includes('Join online')&&ov.includes('已取消'),'today meetings with recurrence, join link, cancelled');
let ovTasks=ov.slice(ov.indexOf('id="overview-tasks"'),ov.indexOf('id="overview-finance"'));
assert(ovTasks.includes('Sample Sender：3 件事')&&ovTasks.includes('登录示例银行')&&!ovTasks.includes('已完成任务'),'open task cards only');
assert(ovTasks.indexOf('登录示例银行')<ovTasks.indexOf('Sample Sender'),'priority order when no deadline');
assert((ovTasks.match(/external-check/g)||[]).length===3&&(ovTasks.match(/external-check checked/g)||[]).length===1,'read-only subtask checks reflect status');
assert(ovTasks.includes('示例邮件摘要')&&ovTasks.includes('Open in Mail'),'summary and mail link');
assert(ov.includes('还没有论文里程碑'),'milestone empty state');
assert(ov.includes('演示 Demo')&&ov.includes('data-route="finance"'),'finance one-liner links to Finance');
assert(!/<input|<textarea|contenteditable/.test(ov),'overview has no editing controls');
assert(bv.includes('>Seminar</h3>')&&bv.includes('Canceled: Seminar'),'display_title main, differing title as subtitle');
assert(!bv.includes('<div class="external-zh-title">Group Meeting</div>'),'identical subtitle hidden');
let bvBrief=bv.slice(bv.indexOf('id="external-briefing"'),bv.indexOf('id="external-milestones"'));
assert(bvBrief.includes('中文要点')&&!/<summary>[^<]*Details<\/summary>/.test(bvBrief),'briefing expanded on Briefing page');
assert(bv.includes('之后还有 8 次')&&!bv.includes('2099'),'recurring meeting summarised, not listed');
assert(bv.indexOf('今日日程')<bv.indexOf('Today’s schedule'),'Chinese section titles first');
assert(bv.includes('class="external-updated"'),'updated time de-emphasised');
ctx.externalData={export_root:'/tmp/x',sources:[{source:'paicc',label:'PAICC',exists:true,warnings:[],records:[]},{source:'fic',label:'FIC',exists:true,manifest:{schema:1},warnings:['Unsupported schema_version None'],records:[
 {source:'fic',source_label:'FIC',read_only:true,demo:true,source_id:'d1',kind:'briefing',title:'Old report',date:'2026-11-09',updated_at:'2026-11-09T08:00:00+00:00',body:'# Old'},
 {source:'fic',source_label:'FIC',read_only:true,demo:true,source_id:'d2',kind:'finance_daily',title:'New report',date:'2026-11-10',updated_at:'2026-11-10T08:00:00+00:00',body:'# 金融日报\n\n> note\n\n- **Bold** item <img src=x onerror=alert(1)>\n- [ok](https://example.invalid/a) [bad](javascript:alert(1)) [local](file:///x)\n- [ ] not a checkbox'},
 {source:'fic',source_label:'FIC',read_only:true,demo:false,source_id:'a1',kind:'finance_alert',title:'Sample alert',level:'L3',rule:'sample_rule',priority:'P1',summary_zh:'示例提醒'},
 {source:'fic',source_label:'FIC',read_only:true,demo:true,source_id:'l1',kind:'learning',title:'TWR vs MWR',topic:'return_measurement'}]}]};
ctx.externalData.sources[1].records.push({source:'fic',source_label:'FIC',read_only:true,demo:false,source_id:'r1',kind:'finance_review',status:'confirmed',tags:['review'],title:'Sample review',date:'2026-11-10',body:'## 复盘\n\n| 项目 | 结论 |\n|---|---|\n| A <b>x</b> | **ok** |\n'},{source:'fic',source_label:'FIC',read_only:true,demo:false,source_id:'r0',kind:'finance_review',status:'draft',title:'Older review',date:'2026-11-09'});
let fin=ctx.financeView();
let rev=fin.slice(fin.indexOf('id="finance-review"'),fin.indexOf('id="finance-latest"'));
assert(rev.includes('Sample review')&&rev.includes('Confirmed 已确认')&&!rev.includes('演示 Demo'),'review shown, confirmed, not demo');
assert(rev.includes('<table>')&&rev.includes('<th>项目</th>')&&rev.includes('A &lt;b&gt;x&lt;/b&gt;')&&rev.includes('<strong>ok</strong>'),'review table rendered and escaped');
assert(rev.includes('Earlier reviews')&&rev.includes('Draft 草稿'),'older draft review listed');
assert(fin.includes('Level L3')&&fin.includes('Rule sample_rule')&&fin.includes('示例提醒'),'alert fields');
assert(fin.indexOf('id="finance-alerts"')<fin.indexOf('id="finance-latest"'),'alerts first');
let latest=fin.slice(fin.indexOf('id="finance-latest"'),fin.indexOf('id="finance-earlier"'));
assert(latest.includes('New report')&&latest.includes('<strong>Bold</strong>')&&latest.includes('<blockquote>'),'latest report rendered as Markdown');
assert(fin.slice(fin.indexOf('id="finance-earlier"')).includes('Old report'),'older report listed');
assert(!fin.includes('<img')&&fin.includes('&lt;img')&&!/href="(javascript|file):/.test(fin)&&!fin.includes('data-checkline')&&!fin.includes('data-open'),'markdown is escaped and read-only');
assert(fin.includes('href="https://example.invalid/a"'),'https links kept');
assert(fin.includes('return measurement')&&fin.includes('TWR vs MWR'),'learning grouped by topic');
assert(fin.includes('finance-demo-note')&&fin.includes('Unsupported schema_version None'),'demo note and schema warning');
assert(!/<input|<textarea|contenteditable/.test(fin),'no editing controls');
ctx.externalData={export_root:'/tmp/x',sources:[{label:'PAICC',exists:false,manifest:null,warnings:[],records:[]},{label:'FIC',exists:false,manifest:null,warnings:[],records:[]}]};
assert(ctx.externalView().includes('No exported records yet'),'empty state');
// Codex review: recurring meetings show today's occurrence; daily reports sort by report date.
{const day=n=>{let d=new Date();d.setDate(d.getDate()+n);return d},stamp=(n,h)=>{let d=day(n);d.setHours(h,0,0,0);return d.toISOString()},hm=x=>new Date(x).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
ctx.externalData={export_root:'/tmp/x',sources:[{source:'paicc',label:'PAICC',exists:true,warnings:[],records:[
 rec({source_id:'rw',kind:'meeting',display_title:'Weekly sample',start_at:stamp(-7,9),end_at:stamp(-7,10),recurring:true,recurrence_zh:'每周示例',upcoming_count:3,upcoming_starts:[stamp(-7,9),stamp(0,14),stamp(7,14)]})]},
 {source:'fic',label:'FIC',exists:true,warnings:[],records:[
  {source:'fic',source_label:'FIC',read_only:true,demo:false,source_id:'old',kind:'finance_daily',title:'Report older',date:'2026-11-09',updated_at:'2026-11-11T12:00:00+00:00',body:'old'},
  {source:'fic',source_label:'FIC',read_only:true,demo:false,source_id:'new',kind:'finance_daily',title:'Report newer',date:'2026-11-10',updated_at:'2026-11-10T08:00:00+00:00',body:'new'}]}]};
let o=ctx.todayOverview(),m=o.slice(o.indexOf('id="overview-meetings"'),o.indexOf('id="overview-milestone"'));
assert(m.includes(hm(stamp(0,14))+'–'+hm(stamp(0,15)))&&!m.includes(hm(stamp(-7,9))),'today shows the matching occurrence time');
assert(m.includes('之后还有 1 次'),'remaining count from today’s occurrence');
let sched=ctx.externalView();sched=sched.slice(sched.indexOf('id="external-schedule"'),sched.indexOf('id="external-tasks"'));
assert(sched.includes('Weekly sample')&&sched.includes(hm(stamp(0,14))),'briefing schedule uses occurrence too');
assert(o.includes('Report newer')&&!o.includes('Report older'),'today finance link uses newest report date');
let f=ctx.financeView(),latest=f.slice(f.indexOf('id="finance-latest"'),f.indexOf('id="finance-earlier"'));
assert(latest.includes('Report newer')&&f.slice(f.indexOf('id="finance-earlier"')).includes('Report older'),'re-exported older report stays in earlier reports');}
console.log('Briefing view: sections, read-only badges, demo marks, escaping, safe links and empty state passed');
