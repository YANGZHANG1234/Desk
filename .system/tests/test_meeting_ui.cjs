const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('.system/app/desk.js','utf8'),ctx={};vm.createContext(ctx);
vm.runInContext(src.slice(src.indexOf('function meetingSections('),src.indexOf('function meetingEditor(')),ctx);
for(const body of ['## Agenda\n\n- First\n- Second\n','Original historical notes\n\n## Confirmed decisions\n\nPending\n','## Agenda\n\nNo final newline'])assert.equal(ctx.meetingBody(ctx.meetingSections(body)),body,'Opening must not rewrite existing notes');
let sections=ctx.meetingSections('## Agenda\n\n- Original');let notes=sections.find(s=>s.label==='Notes');notes.text='新笔记\n\n';notes.virtual=false;let saved=ctx.meetingBody(sections);assert.equal(saved,'## Agenda\n\n- Original\n\n## Notes\n\n新笔记\n\n');assert.equal(ctx.meetingBody(ctx.meetingSections(saved)),saved);assert(!saved.includes('## Decisions'));
assert.equal(ctx.meetingSections('## Original notes\n\nText\n## Confirmed decisions\n\nYes\n').filter(s=>s.label==='Notes'||s.label==='Decisions').length,0);
console.log('Meeting section preservation, missing sections, bilingual notes and reopen round trip passed');

let end=ctx.meetingSections('## Agenda\n\nTopic\n\n## Notes');assert.equal(end.find(s=>s.label==='Notes').text,'');assert.equal(ctx.meetingBody(end),'## Agenda\n\nTopic\n\n## Notes');end.find(s=>s.label==='Notes').text='Text';assert(ctx.meetingBody(end).endsWith('## Notes\n\nText'));
