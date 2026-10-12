// End-to-end checks of the real database rules, run on a throw-away in-memory database.
const { open } = require('../db');
function run(names = ['South', 'East', 'North'], levels = 3, per = 50) {
  const R = [], t = (n, f) => { try { const r = f(); R.push([n, r !== false, typeof r === 'string' ? r : '']); } catch (e) { R.push([n, false, e.message]); } }, th = f => { try { f(); } catch { return true; } return false; };
  const fresh = () => { const d = open(':memory:'); d.build(names, levels, per); return d; };
  const d = fresh(), ids = () => d.state(true).slots, all = ids().filter(s => s.st === 'available');
  t('Book every slot', () => { all.forEach(s => d.book(s.id)); return all.length + ' booked'; });
  const occ = ids().filter(s => s.st === 'occupied'), f = occ[0], o = occ[1];
  t('All verification codes are unique', () => new Set(occ.map(s => s.code)).size === occ.length && d.raw.prepare('SELECT COUNT(DISTINCT code) n FROM slots').get().n === occ.length);
  t('Codes are random (not sequential / not derived from slot)', () => { const c = occ.slice(0, 20).map(s => s.code); return new Set(c.map(x => x[0])).size > 1 && !c.every((x, i) => i === 0 || x > c[i - 1]); });
  t('Booking an occupied slot is rejected', () => th(() => d.book(f.id)));
  t('Wrong code is rejected, slot stays occupied', () => th(() => d.exit(f.eid, f.label, 'ZZZZZZ')) && ids().find(s => s.id === f.id).st === 'occupied');
  t("Another slot's code is rejected", () => !o || th(() => d.exit(f.eid, f.label, o.code)));
  t('Wrong exit gate is rejected', () => { const other = d.state(true).entrances.find(e => e.id !== f.eid); return other ? th(() => d.exit(other.id, f.label, f.code)) : 'skipped (single entrance)'; });
  t('Correct gate + code frees the slot', () => { const r = d.exit(f.eid, f.label.toLowerCase(), f.code.toLowerCase()); const s = ids().find(x => x.id === f.id); return s.st === 'available' && !s.code && r.exitedAt >= r.enteredAt; });
  t('Used code cannot be reused', () => th(() => d.exit(f.eid, f.label, f.code)));
  t('Re-booking issues a NEW code', () => d.book(f.id).code !== f.code);
  t('Admin can release a slot without a code', () => { d.release(o.id); return ids().find(s => s.id === o.id).st === 'available'; });
  t('Booking history is recorded', () => { const b = d.raw.prepare('SELECT COUNT(*) n, SUM(exited_at IS NOT NULL) x FROM bookings').get(); return `${b.n} bookings, ${b.x} completed`; });
  t('Maintenance entrance / level / slot issue no tickets', () => { const m = fresh(), s = m.state(true); m.toggle('entrances', s.entrances[0].id); const a = th(() => m.book(s.slots.find(x => x.eid === s.entrances[0].id).id)); m.toggle('entrances', s.entrances[0].id); m.toggle('levels', s.levels[0].id); const b = th(() => m.book(s.slots.find(x => x.lid === s.levels[0].id).id)); m.toggle('levels', s.levels[0].id); m.toggle('slots', s.slots[0].id); return a && b && th(() => m.book(s.slots[0].id)); });
  t('Layout can change: add/remove slots, level, entrance', () => { const m = fresh(), s = m.state(true), n0 = s.slots.length; m.setCount(s.entrances[0].id, s.levels[0].id, per + 5); m.setCount(s.entrances[0].id, s.levels[0].id, per); m.addLevel(10); m.addEntrance('West', 10); return m.state(true).slots.length === n0 + 10 * s.entrances.length + 10 * (s.levels.length + 1); });
  t('Occupied slots cannot be removed', () => { const m = fresh(), s = m.state(true); s.slots.filter(x => x.eid === s.entrances[0].id && x.lid === s.levels[0].id).forEach(x => m.book(x.id)); return th(() => m.setCount(s.entrances[0].id, s.levels[0].id, per - 1)) && th(() => m.remove('entrances', s.entrances[0].id)); });
  t('Stress: 8,000 random booking attempts', () => { const m = fresh(), s = m.state(true).slots, cap = s.length; let ok = 0, no = 0; const t0 = Date.now(); for (let i = 0; i < 8000; i++) { try { m.book(s[Math.random() * cap | 0].id); ok++; } catch { no++; } } const oc = m.state(true).slots.filter(x => x.st === 'occupied'); return ok <= cap && oc.length === ok && new Set(oc.map(x => x.code)).size === ok ? `${ok} accepted, ${no} rejected, capacity ${cap}, no double-booking, ${Date.now() - t0} ms` : false; });
  return R;
}
module.exports = { run };
