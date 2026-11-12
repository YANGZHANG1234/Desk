// Briefing view renders fabricated export records read-only, escaped and with safe links only.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('.system/app/desk.js','utf8');
const ctx={E:s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),I:()=>'',localDate:d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`,dateText:d=>d,route:'briefing'};
ctx.today=()=>ctx.localDate(new Date());ctx.pageHeading=t=>`<h1>${t}</h1>`;vm.createContext(ctx);
vm.runInContext(src.slice(src.indexOf('let externalData='),src.indexOf('async function loadExternal(')).replace(/^let externalData=/m,'var externalData=').replace(/,taskMarks=\{\},externalLoadedAt=0;/,';var taskMarks={},externalLoadedAt=0;'),ctx);
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
assert((ovTasks.match(/external-check/g)||[]).length===4&&(ovTasks.match(/external-check checked/g)||[]).length===1,'3 subtask checks + 1 single-task check; mail-assistant done stays checked');
// Ticking: open PAICC tasks get real buttons; a task PAICC already closed stays a read-only tick.
assert((ovTasks.match(/<button type="button" class="external-check" data-task-mark="(s1|s3|t2)"/g)||[]).length===3,'open tasks are clickable');
assert(!ovTasks.includes('data-task-mark="s2"')&&ovTasks.includes('aria-label="Done (read-only)"'),'source-done subtask not clickable');
assert(ovTasks.includes('data-task-mark="s1,s3" data-done="1"')&&ovTasks.includes('还剩 3 件待办'),'mark-all and remaining count');
ctx.taskMarks={s1:new Date().toISOString(),t2:new Date().toISOString()};
let ticked=ctx.todayOverview(),tickedTasks=ticked.slice(ticked.indexOf('id="overview-tasks"'),ticked.indexOf('id="overview-finance"'));
assert(tickedTasks.includes('还剩 1 件待办')&&tickedTasks.includes('今天完成 2 件')&&tickedTasks.includes('1/3 未完成'),'counts follow Desk marks');
assert(tickedTasks.includes('data-task-mark="s1" data-done="0"')&&tickedTasks.includes('overview-task is-done'),'ticked today stays visible and can be unticked');
ctx.taskMarks={t2:'2020-01-01T09:00:00Z'};
let old=ctx.todayOverview();assert(!old.slice(old.indexOf('id="overview-tasks"')).includes('登录示例银行'),'tasks ticked on an earlier day are hidden');
ctx.taskMarks={};
// PAICC re-export of a Desk tick (D-028): COMPLETED + done_in_desk stays clickable and follows Desk's marks.
{let save=ctx.externalData;ctx.externalData={export_root:'/tmp/x',sources:[{source:'paicc',label:'PAICC',exists:true,warnings:[],records:[
 rec({source_id:'g',kind:'task',display_title:'示例分组',task_count:2,open_count:1,subtasks:[{source_id:'g1',display_title:'已在 Desk 勾选',status:'COMPLETED',done_in_desk:true},{source_id:'g2',display_title:'未完成',status:'INBOX',done_in_desk:false}]})]}]};
 ctx.taskMarks={g1:new Date().toISOString()};let o=ctx.todayOverview();
 assert(o.includes('data-task-mark="g1" data-done="0"')&&o.includes('1/2 未完成'),'desk-ticked export item can be unticked');
 ctx.taskMarks={};o=ctx.todayOverview();
 assert(o.includes('data-task-mark="g1" data-done="1"')&&o.includes('还剩 2 件待办'),'unticked before the next export shows as open');
 ctx.taskMarks={};ctx.externalData=save;}

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
// Finance lock: locked views show only the lock, never FIC titles or counts.
{ctx.externalData={export_root:'/tmp/x',finance_locked:true,sources:[{source:'paicc',label:'PAICC',exists:true,warnings:[],records:[rec({source_id:'pt1',kind:'task',display_title:'普通任务'})]},{source:'fic',label:'FIC',locked:true,exists:null,manifest:null,warnings:[],records:[]}]};
vm.runInContext("financeStatus={locked:true,configured:true,retry_after:0,idle_minutes:15,reset_hint:'desk lock set'};financeMessage=''",ctx);
let fv=ctx.financeView();
assert(fv.includes('id="finance-unlock"')&&fv.includes('type="password"')&&fv.includes('金融内容已锁定'),'locked Finance shows password form');
assert(!/records?\b|条|Latest daily|持仓|Holdings/.test(fv.replace(/<form[\s\S]*<\/form>/,'')),'locked Finance reveals no titles or counts');
assert(!fv.includes('data-action="finance-lock"'),'no Lock button while locked');
assert(!fv.includes('忘记密码')&&!fv.includes('desk lock set'),'no reset instructions on the lock screen');
let bv=ctx.externalView();assert(bv.includes('金融内容已锁定')&&!bv.includes('id="external-learning"')&&!bv.includes('FIC 0'),'Briefing finance section locked');
let ov=ctx.todayOverview();assert(ov.includes('金融内容已锁定')&&ov.includes('普通任务'),'Today finance locked, PAICC still shown');
vm.runInContext("financeStatus={locked:true,configured:false,retry_after:0,reset_hint:'uv run python -m app.finance.cli desk lock set'}",ctx);
let nc=ctx.financeView();assert(nc.includes('还没有设置金融密码')&&!nc.includes('desk lock set')&&/<input[^>]*disabled/.test(nc),'unconfigured hint, input disabled');
vm.runInContext("financeStatus={locked:true,configured:true,retry_after:240}",ctx);
assert(ctx.financeView().includes('请 4 分钟后再试'),'lockout countdown');
ctx.externalData={export_root:'/tmp/x',finance_locked:false,sources:[{source:'fic',label:'FIC',exists:true,warnings:[],records:[{source:'fic',source_label:'FIC',read_only:true,demo:false,source_id:'h',kind:'finance_holdings',title:'持仓 2026-11-11',date:'2026-11-11',body:'| 账户 | 金额 CNY |\n|---|---|\n| A | 1 |'}]}]};
ctx.pageHeading=(t,a='')=>`<h1>${t}</h1>${a}`;let un=ctx.financeView();assert(un.includes('data-action="finance-lock"')&&un.includes('id="finance-holdings"')&&un.includes('<th>金额 CNY</th>'),'unlocked shows Lock button and holdings table');}
// FD-044 charts: values come from chart_data unchanged; views and follow-ups rendered read-only.
{const cats=Array.from({length:9},(_,i)=>({key:'c'+i,label_zh:'类别'+i,label_en:'Cat '+i,value:100*(9-i),weight:i===0?30:8.75,pnl:i%2?-50*i:40*i,count:i+1}));
const cd={base:'CNY',total:123456.78,by_category:cats,by_region:[{key:'cn',label_zh:'中国',value:500,weight:60},{key:'us',label_zh:'美国',value:300,weight:40}],by_currency:[{key:'CNY',value:700,weight:70}],by_account:[{account:'<b>Acct</b>',value:400,weight:50}],top_losses:Array.from({length:12},(_,i)=>({name:'Loss '+i,account:'A',pnl:-(i+1)*10,pnl_pct:-(i+1)}))};
ctx.externalData={export_root:'/tmp/x',finance_locked:false,sources:[{source:'fic',label:'FIC',exists:true,warnings:[],records:[
 {source:'fic',source_label:'FIC',read_only:true,demo:false,source_id:'h',kind:'finance_holdings',title:'持仓',date:'2026-11-11',chart_data:cd,body:'| a | b |\n|---|---|\n| 1 | 2 |'},
 {source:'fic',source_label:'FIC',read_only:true,demo:false,source_id:'r',kind:'finance_review',status:'confirmed',title:'复盘',date:'2026-11-11',body:'全文',views:[{view:'观点甲',why:'理由甲',risk:'风险甲',confidence:'high'},{view:'观点乙',confidence:'低'},{view:'<i>x</i>',confidence:'medium'}],followups:[{done:false,text:'无日期事项',due:null},{done:true,text:'较晚事项',due:'12-01'},{done:false,text:'较早事项',due:'11-15'}]}]}]};
let f=ctx.financeView(),hold=f.slice(f.indexOf('id="finance-holdings"'),f.indexOf('id="finance-latest"'));
assert(hold.includes('123,457')&&hold.includes('总值 CNY'),'center total comes from chart_data.total');
assert((hold.match(/class="fin-arc"/g)||[]).length===9&&hold.includes('stroke="#b9b8b1"'),'nine arcs, ninth folded to neutral gray');
assert(hold.includes('类别0')&&hold.includes('30.0%')&&hold.includes('8.8%'),'legend shows label_zh and weight');
assert(hold.includes('地区分布')&&hold.includes('账户分布')&&hold.includes('币种分布')&&hold.includes('各类浮盈亏')&&hold.includes('最大亏损 Top 10'),'all chart cards present');
let losses=hold.slice(hold.indexOf('最大亏损'));assert(losses.includes('Loss 9')&&!losses.includes('Loss 10'),'top losses capped at 10');
assert(hold.includes('−50')&&hold.includes('+80')&&hold.includes(`left:auto;right:50%`)&&hold.includes(`left:50%`),'signed diverging bars');
assert(!hold.includes('<b>Acct</b>')&&hold.includes('&lt;b&gt;Acct'),'labels escaped');
assert(hold.includes('持仓明细 Details')&&(hold.match(/表格 Table/g)||[]).length===6,'detail table collapsed, every chart has a table view');
assert(!/<script|https?:\/\/(?!example)/.test(hold.replace(/xmlns="[^"]*"/g,'')),'no external resources');
let rev=f.slice(f.indexOf('id="finance-review"'),f.indexOf('id="finance-holdings"'));
assert(rev.includes('Claude 观点')&&rev.includes('信心 高')&&rev.includes('信心 低')&&rev.includes('信心 中')&&rev.includes('理由甲')&&rev.includes('风险甲'),'views with confidence labels');
assert(rev.indexOf('较早事项')<rev.indexOf('较晚事项')&&rev.indexOf('较晚事项')<rev.indexOf('无日期事项'),'follow-ups sorted by due, null last');
assert((rev.match(/external-check checked/g)||[]).length===1&&rev.includes('复盘全文'),'done follow-up checked; full text folded');
assert(!rev.includes('<i>x</i>'),'views escaped');}
console.log('Briefing view: sections, read-only badges, demo marks, escaping, safe links and empty state passed');

// Codex PR#2: lockout expiry re-enables the form; UI idle timeout revokes the server session.
(async()=>{
 let timers=[],calls=0;ctx.setTimeout=(f,ms)=>{timers.push([f,ms]);return timers.length};ctx.clearTimeout=()=>{};ctx.render=()=>{};
 ctx.fetch=async()=>({json:async()=>(++calls===1?{locked:true,retry_after:120}:{locked:true,retry_after:0})});
 await ctx.financeRefreshStatus();
 assert(timers.length===1&&timers[0][1]===120500,'refresh scheduled when lockout ends');
 await timers[0][0]();assert.equal(vm.runInContext("financeStatus",ctx).retry_after,0,'status refreshed after lockout');assert.equal(timers.length,1,'no timer once unlocked');
 assert(/setInterval\(\(\)=>\{if\(externalData&&!externalData\.finance_locked&&Date\.now\(\)-externalActivity>15\*60\*1000\)financeLock\(\)\}/.test(src),'idle timeout calls financeLock, not loadExternal');
 console.log('Finance lock: lockout expiry and idle revoke passed');
})().catch(e=>{console.error(e);process.exit(1)});

// Codex PR#3: overlapping ticks are saved one at a time and none is lost.
(async()=>{
 const seg=src.slice(src.indexOf('let taskMarkQueue='),src.indexOf("document.addEventListener('click',e=>{let b=e.target.closest?.('[data-task-mark]')"));
 const c={render(){},alert(){},Date,taskMarks:{}},server={},inflight=[];let maxInflight=0,open=0;
 c.fetch=(url,opt)=>new Promise(res=>{open++;maxInflight=Math.max(maxInflight,open);inflight.push(()=>{open--;let op=JSON.parse(opt.body);op.ids.forEach(id=>{if(op.done)server[id]='t';else delete server[id]});res({ok:true,json:async()=>({done:{...server}})})})});
 vm.createContext(c);vm.runInContext(seg.replace(/^let taskMarkQueue=/,'var taskMarkQueue=')+';this.toggle=toggleTaskMark;this.marks=()=>taskMarks;',c);
 c.toggle(['a'],true);c.toggle(['b'],true);
 assert.deepEqual(Object.keys(c.marks()).sort(),['a','b'],'both ticks shown at once');
 while(inflight.length){inflight.shift()();await new Promise(r=>setImmediate(r))}
 assert.equal(maxInflight,1,'one save at a time');
 assert.deepEqual(Object.keys(c.marks()).sort(),['a','b'],'no tick lost after replies');
 console.log('Task marks: serialized saves passed');
})().catch(e=>{console.error(e);process.exit(1)});
