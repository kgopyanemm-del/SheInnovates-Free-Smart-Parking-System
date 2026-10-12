/* SmartPark core rules: pure functions, no UI. Used by the app AND by tests/run-tests.js */
const pad=n=>String(n).padStart(3,'0'),fe=(d,id)=>d.entrances.find(e=>e.id==id),fl=(d,id)=>d.levels.find(l=>l.id==id);
/* ===== CORE LOGIC (pure functions on a db object: also used by the self-test) ===== */
function mk(d,e,l,n){let max=0;d.slots.forEach(s=>{if(s.eid==e.id&&s.lid==l.id&&s.num>max)max=s.num});
 for(let i=1;i<=n;i++){const num=max+i;d.slots.push({id:d.next++,eid:e.id,lid:l.id,num,label:`${e.prefix}-L${l.no}-${pad(num)}`,st:'available',code:null,at:null})}}
function build(d,names,levels,per){d.entrances=[];d.levels=[];d.slots=[];const used=new Set();
 names.forEach(n=>{let p=n[0].toUpperCase(),k=1;while(used.has(p))p=n[0].toUpperCase()+(++k);used.add(p);d.entrances.push({id:d.next++,name:n,prefix:p,st:'open'})});
 for(let i=1;i<=levels;i++)d.levels.push({id:d.next++,no:i,name:'Level '+i,st:'open'});
 d.entrances.forEach(e=>d.levels.forEach(l=>mk(d,e,l,per)))}
function genCode(d){const A='ABCDEFGHJKLMNPQRSTUVWXYZ23456789',used=new Set(d.slots.map(s=>s.code));let c;
 do{c=[...crypto.getRandomValues(new Uint8Array(6))].map(b=>A[b%A.length]).join('')}while(used.has(c));return c}
function book(d,id){const s=d.slots.find(x=>x.id==id);if(!s)throw Error('Slot does not exist');
 if(fe(d,s.eid).st!=='open')throw Error('This entrance is under maintenance');
 if(fl(d,s.lid).st!=='open')throw Error('This level is under maintenance');
 if(s.st==='maintenance')throw Error('This slot is under maintenance');
 if(s.st==='occupied')throw Error('That slot was just taken. Please pick another.');
 s.st='occupied';s.code=genCode(d);s.at=Date.now();return s}
function release(s){s.st='available';s.code=null;s.at=null}
function verifyExit(d,gateEid,label,code){const s=d.slots.find(x=>x.label===String(label).trim().toUpperCase());
 if(!s)throw Error('Slot number not found.');
 if(s.st!=='occupied')throw Error('This slot is not currently occupied.');
 if(s.eid!=gateEid)throw Error('Wrong exit gate. The exit must match the entrance this vehicle used.');
 if(s.code!==String(code).trim().toUpperCase())throw Error('Verification code does not match this slot.');
 const at=s.at;release(s);return{label:s.label,eid:s.eid,enteredAt:at}}
function setCount(d,eid,lid,n){const cur=d.slots.filter(s=>s.eid==eid&&s.lid==lid);
 if(n>cur.length)mk(d,fe(d,eid),fl(d,lid),n-cur.length);
 else{const rm=cur.filter(s=>s.st!=='occupied').sort((a,b)=>b.num-a.num).slice(0,cur.length-n);
  if(rm.length<cur.length-n)throw Error('Cannot go that low: occupied slots cannot be removed.');
  const ids=new Set(rm.map(s=>s.id));d.slots=d.slots.filter(s=>!ids.has(s.id))}}
const hasOcc=(d,f)=>d.slots.some(s=>s.st==='occupied'&&f(s));
function selfTest(DB){const R=[],t=(n,f)=>{try{const r=f();R.push([n,r!==false,typeof r==='string'?r:''])}catch(x){R.push([n,false,x.message])}},th=f=>{try{f()}catch{return true}return false};
 const fresh=()=>{const d=structuredClone(DB);d.entrances.forEach(e=>e.st='open');d.levels.forEach(l=>l.st='open');d.slots.forEach(s=>{if(s.st!=='maintenance'){s.st='available';s.code=null}});return d};
 const d=fresh(),av=d.slots.filter(s=>s.st==='available');if(!av.length)return[['No slots configured',false,'']];
 t('Book every available slot',()=>{av.forEach(s=>book(d,s.id));return av.length+' booked'});
 const occ=d.slots.filter(s=>s.st==='occupied'),f=occ[0],o=occ[1];
 t('All verification codes are unique',()=>new Set(occ.map(s=>s.code)).size===occ.length);
 t('Booking an occupied slot is rejected',()=>th(()=>book(d,f.id)));
 t('Wrong code is rejected, slot stays occupied',()=>th(()=>verifyExit(d,f.eid,f.label,'ZZZZZZ'))&&f.st==='occupied');
 t('Another slot\'s code is rejected',()=>!o||th(()=>verifyExit(d,f.eid,f.label,o.code)));
 t('Wrong exit gate is rejected',()=>{const other=d.entrances.find(e=>e.id!==f.eid);return other?th(()=>verifyExit(d,other.id,f.label,f.code)):'skipped (single entrance)'});
 const old=f.code;t('Correct gate + code frees the slot',()=>{verifyExit(d,f.eid,f.label,f.code);return f.st==='available'&&f.code===null});
 t('Used code cannot be reused',()=>th(()=>verifyExit(d,f.eid,f.label,old)));
 t('Re-booking issues a NEW code',()=>{book(d,f.id);return f.code!==old});
 t('Maintenance entrance issues no tickets',()=>{const m=fresh();m.entrances[0].st='maintenance';return th(()=>book(m,m.slots.find(s=>s.eid===m.entrances[0].id).id))});
 t('Maintenance level / slot issue no tickets',()=>{const m=fresh();m.levels[0].st='maintenance';const a=th(()=>book(m,m.slots.find(s=>s.lid===m.levels[0].id).id));m.levels[0].st='open';m.slots[0].st='maintenance';return a&&th(()=>book(m,m.slots[0].id))});
 t('Stress: 8,000 random booking attempts',()=>{const m=fresh(),cap=m.slots.filter(s=>s.st==='available').length;let ok=0,no=0,t0=performance.now();for(let i=0;i<8000;i++){try{book(m,m.slots[Math.random()*m.slots.length|0].id);ok++}catch{no++}}
  const oc=m.slots.filter(s=>s.st==='occupied');return ok<=cap&&oc.length===ok&&new Set(oc.map(s=>s.code)).size===ok?`${ok} accepted, ${no} rejected, capacity ${cap}, no double-booking, ${Math.round(performance.now()-t0)} ms`:false});
 return R}

if(typeof module!=='undefined')module.exports={pad,fe,fl,mk,build,genCode,book,release,verifyExit,setCount,hasOcc,selfTest};
