/* SmartPark database layer (SQLite). ALL business rules live here, on the server. */
const { DatabaseSync } = require('node:sqlite'), crypto = require('crypto'); // built into Node 22.13+, nothing to compile
const ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789', pad = n => String(n).padStart(3, '0');
class Fail extends Error {}                       // errors that are safe to show to the user
const fail = m => { throw new Fail(m); };

const hashPw = (pw, salt = crypto.randomBytes(16).toString('hex')) => salt + ':' + crypto.scryptSync(pw, salt, 32).toString('hex');
const checkPw = (pw, stored) => { const [salt, h] = stored.split(':'); return crypto.timingSafeEqual(Buffer.from(h, 'hex'), crypto.scryptSync(pw, salt, 32)); };

const SCHEMA = `
CREATE TABLE IF NOT EXISTS entrances(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, prefix TEXT UNIQUE NOT NULL, status TEXT NOT NULL DEFAULT 'open' CHECK(status IN('open','maintenance')));
CREATE TABLE IF NOT EXISTS levels(id INTEGER PRIMARY KEY AUTOINCREMENT, no INTEGER UNIQUE NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open' CHECK(status IN('open','maintenance')));
CREATE TABLE IF NOT EXISTS slots(id INTEGER PRIMARY KEY AUTOINCREMENT,
  entrance_id INTEGER NOT NULL REFERENCES entrances(id) ON DELETE CASCADE,
  level_id INTEGER NOT NULL REFERENCES levels(id) ON DELETE CASCADE,
  num INTEGER NOT NULL, label TEXT UNIQUE NOT NULL,
  status TEXT NOT NULL DEFAULT 'available' CHECK(status IN('available','occupied','maintenance')),
  code TEXT UNIQUE, booked_at INTEGER, UNIQUE(entrance_id, level_id, num));
CREATE TABLE IF NOT EXISTS admins(emp TEXT PRIMARY KEY, name TEXT NOT NULL, pass_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bookings(id INTEGER PRIMARY KEY AUTOINCREMENT, slot_label TEXT NOT NULL, entrance_name TEXT NOT NULL, code TEXT NOT NULL, entered_at INTEGER NOT NULL, exited_at INTEGER, released_by TEXT);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);`;

function open(file) {
  const db = new DatabaseSync(file); db.exec('PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;'); db.exec(SCHEMA);
  const tx = fn => (...a) => { db.exec('BEGIN IMMEDIATE'); try { const r = fn(...a); db.exec('COMMIT'); return r; } catch (e) { db.exec('ROLLBACK'); throw e; } }; // all-or-nothing
  const one = (sql, ...p) => db.prepare(sql).get(...p), all = (sql, ...p) => db.prepare(sql).all(...p), run = (sql, ...p) => db.prepare(sql).run(...p);
  const occupied = () => one("SELECT COUNT(*) n FROM slots WHERE status='occupied'").n;

  // Verification code: RANDOM (crypto.randomInt). The UNIQUE column + this loop only guarantee no two active codes collide.
  function genCode() { for (;;) { const c = Array.from({ length: 6 }, () => ALPHABET[crypto.randomInt(ALPHABET.length)]).join(''); if (!one('SELECT 1 FROM slots WHERE code=?', c)) return c; } }

  function mk(e, l, n) { // add n new slots to an entrance+level, numbering continues after the highest existing number
    const max = one('SELECT COALESCE(MAX(num),0) m FROM slots WHERE entrance_id=? AND level_id=?', e.id, l.id).m, ins = db.prepare('INSERT INTO slots(entrance_id,level_id,num,label) VALUES(?,?,?,?)');
    for (let i = 1; i <= n; i++) ins.run(e.id, l.id, max + i, `${e.prefix}-L${l.no}-${pad(max + i)}`);
  }
  function newEntrance(name) {
    name = String(name || '').trim(); if (!name) fail('Enter an entrance name.');
    if (one('SELECT 1 FROM entrances WHERE lower(name)=lower(?)', name)) fail('That entrance already exists.');
    let p = name[0].toUpperCase(), i = 1; while (one('SELECT 1 FROM entrances WHERE prefix=?', p)) p = name[0].toUpperCase() + (++i);
    const id = Number(run('INSERT INTO entrances(name,prefix) VALUES(?,?)', name, p).lastInsertRowid); return one('SELECT * FROM entrances WHERE id=?', id);
  }
  const newLevel = () => { const no = one('SELECT COALESCE(MAX(no),0)+1 n FROM levels').n; const id = Number(run('INSERT INTO levels(no,name) VALUES(?,?)', no, 'Level ' + no).lastInsertRowid); return one('SELECT * FROM levels WHERE id=?', id); };
  const posInt = (v, what) => { v = Math.floor(+v); if (!(v >= 1)) fail(what + ' must be at least 1.'); return v; };

  const api = {
    raw: db, close: () => db.close(),
    build: tx((names, levels, per) => {          // (re)build the whole layout
      names = names.map(s => String(s).trim()).filter(Boolean); levels = posInt(levels, 'Levels'); per = posInt(per, 'Slots per level'); if (!names.length) fail('Enter at least one entrance.');
      if (occupied()) fail('Release all occupied slots before rebuilding.');
      db.exec('DELETE FROM slots; DELETE FROM entrances; DELETE FROM levels;');
      const es = names.map(newEntrance), ls = Array.from({ length: levels }, newLevel);
      es.forEach(e => ls.forEach(l => mk(e, l, per))); return { slots: one('SELECT COUNT(*) n FROM slots').n };
    }),
    state(withCodes) { // what the browser is allowed to see. Codes are only sent to a logged-in admin.
      const cols = 'id, entrance_id eid, level_id lid, num, label, status st' + (withCodes ? ', code, booked_at at' : '');
      const s = { entrances: all('SELECT id,name,prefix,status st FROM entrances ORDER BY id'), levels: all('SELECT id,no,name,status st FROM levels ORDER BY no'), slots: all(`SELECT ${cols} FROM slots ORDER BY entrance_id, level_id, num`) };
      if (withCodes) s.admins = all('SELECT emp,name FROM admins ORDER BY name'); else s.admins = []; return s;
    },
    // ---- ticket issuing: one transaction, one conditional UPDATE => two drivers can never get the same slot
    book: tx(id => {
      const s = one(`SELECT s.*, e.status es, l.status ls, e.name en FROM slots s JOIN entrances e ON e.id=s.entrance_id JOIN levels l ON l.id=s.level_id WHERE s.id=?`, id);
      if (!s) fail('Slot does not exist');
      if (s.es !== 'open') fail('This entrance is under maintenance'); if (s.ls !== 'open') fail('This level is under maintenance'); if (s.status === 'maintenance') fail('This slot is under maintenance');
      const code = genCode(), now = Date.now();
      if (!Number(run("UPDATE slots SET status='occupied', code=?, booked_at=? WHERE id=? AND status='available'", code, now, id).changes)) fail('That slot was just taken. Please pick another.');
      run('INSERT INTO bookings(slot_label,entrance_name,code,entered_at) VALUES(?,?,?,?)', s.label, s.en, code, now);
      return { label: s.label, code, eid: s.entrance_id, at: now };
    }),
    // ---- exit: slot must exist + be occupied, gate must equal entrance used, code must equal the code linked to this slot
    exit: tx((eid, label, code) => {
      const s = one('SELECT * FROM slots WHERE label=?', String(label || '').trim().toUpperCase());
      if (!s) fail('Slot number not found.'); if (s.status !== 'occupied') fail('This slot is not currently occupied.');
      if (s.entrance_id != eid) fail('Wrong exit gate. The exit must match the entrance this vehicle used.');
      if (s.code !== String(code || '').trim().toUpperCase()) fail('Verification code does not match this slot.');
      const now = Date.now();
      run("UPDATE slots SET status='available', code=NULL, booked_at=NULL WHERE id=?", s.id);
      run("UPDATE bookings SET exited_at=?, released_by='driver' WHERE slot_label=? AND exited_at IS NULL", now, s.label);
      return { label: s.label, eid: s.entrance_id, enteredAt: s.booked_at, exitedAt: now };
    }),
    release: tx(id => { // admin override: free a slot without a code
      const s = one('SELECT * FROM slots WHERE id=?', id); if (!s || s.status !== 'occupied') fail('Slot is not occupied.');
      run("UPDATE slots SET status='available', code=NULL, booked_at=NULL WHERE id=?", id);
      run("UPDATE bookings SET exited_at=?, released_by='admin' WHERE slot_label=? AND exited_at IS NULL", Date.now(), s.label);
    }),
    setCount: tx((eid, lid, n) => {
      n = Math.max(0, Math.floor(+n) || 0); const e = one('SELECT * FROM entrances WHERE id=?', eid), l = one('SELECT * FROM levels WHERE id=?', lid); if (!e || !l) fail('Not found.');
      const cur = one('SELECT COUNT(*) n FROM slots WHERE entrance_id=? AND level_id=?', eid, lid).n;
      if (n > cur) return mk(e, l, n - cur);
      const rm = all("SELECT id FROM slots WHERE entrance_id=? AND level_id=? AND status!='occupied' ORDER BY num DESC LIMIT ?", eid, lid, cur - n);
      if (rm.length < cur - n) fail('Cannot go that low: occupied slots cannot be removed.');
      rm.forEach(r => run('DELETE FROM slots WHERE id=?', r.id));
    }),
    addEntrance: tx((name, per) => { per = posInt(per, 'Slots per level'); const e = newEntrance(name); all('SELECT * FROM levels').forEach(l => mk(e, l, per)); }),
    addLevel: tx(per => { per = posInt(per, 'Slots per entrance'); const l = newLevel(); all('SELECT * FROM entrances').forEach(e => mk(e, l, per)); }),
    toggle(table, id) { // maintenance on/off for an entrance, level or single slot
      if (table === 'slots') { const s = one('SELECT status FROM slots WHERE id=?', id); if (!s) fail('Not found.'); if (s.status === 'occupied') fail('Occupied slots cannot be changed.'); return run('UPDATE slots SET status=? WHERE id=?', s.status === 'maintenance' ? 'available' : 'maintenance', id); }
      if (!['entrances', 'levels'].includes(table)) fail('Bad request.'); run(`UPDATE ${table} SET status = CASE status WHEN 'open' THEN 'maintenance' ELSE 'open' END WHERE id=?`, id);
    },
    remove(table, id) { // delete an entrance or level (its slots go with it, ON DELETE CASCADE)
      const col = table === 'entrances' ? 'entrance_id' : 'level_id'; if (!['entrances', 'levels'].includes(table)) fail('Bad request.');
      if (one(`SELECT 1 FROM slots WHERE ${col}=? AND status='occupied'`, id)) fail('It has occupied slots. Release them first.'); run(`DELETE FROM ${table} WHERE id=?`, id);
    },
    login(emp, pw) { const a = one('SELECT * FROM admins WHERE lower(emp)=lower(?)', String(emp || '').trim()); return a && checkPw(String(pw || ''), a.pass_hash) ? { emp: a.emp, name: a.name } : null; },
    addAdmin(emp, name, pw) { emp = String(emp || '').trim(); name = String(name || '').trim(); if (!emp || !name || String(pw || '').length < 6) fail('Fill all fields. Password needs 6+ characters.'); if (one('SELECT 1 FROM admins WHERE lower(emp)=lower(?)', emp)) fail('Employee number already exists.'); run('INSERT INTO admins VALUES(?,?,?)', emp, name, hashPw(pw)); },
    removeAdmin(emp) { if (one('SELECT COUNT(*) n FROM admins').n < 2) fail('Cannot remove the last admin.'); run('DELETE FROM admins WHERE emp=?', emp); },
  };
  if (!one("SELECT 1 FROM meta WHERE k='seeded'")) { // first run only: starter layout + first admin (everything is editable afterwards)
    api.build(['South', 'East', 'North'], 3, 50); api.addAdmin('ADM001', 'Main Admin', 'admin123'); run("INSERT INTO meta VALUES('seeded','1')");
  }
  return api;
}
module.exports = { open, Fail };
