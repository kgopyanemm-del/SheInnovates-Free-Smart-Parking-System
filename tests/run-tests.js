// Run with:  node tests/run-tests.js
const c=require('../js/core.js');
const layouts=[['Default mall',['South','East','North'],3,50],['Small mall: 1 entrance, 30 slots',['Main'],1,30],['Big site',['A','B','C','D','E'],4,40]];
let failed=0;
for(const [name,ent,lv,per] of layouts){
  const DB={next:1,admins:[],entrances:[],levels:[],slots:[]};c.build(DB,ent,lv,per);
  console.log(`\n== ${name}: ${DB.slots.length} slots ==`);
  for(const [t,ok,info] of c.selfTest(DB)){console.log((ok?'PASS ':'FAIL ')+t+(info?'  ('+info+')':''));if(!ok)failed++}
}
console.log(failed?`\n${failed} FAILED`:'\nAll tests passed');process.exit(failed?1:0);
