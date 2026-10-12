// npm test
const { run } = require('./selftest'); let failed = 0;
for (const [name, ...cfg] of [['Default mall', ['South', 'East', 'North'], 3, 50], ['Small mall: 1 entrance, 30 slots', ['Main'], 1, 30], ['Big site', ['A', 'B', 'C', 'D', 'E'], 4, 40]]) {
  console.log(`\n== ${name} ==`); for (const [t, ok, info] of run(...cfg)) { console.log((ok ? 'PASS ' : 'FAIL ') + t + (info ? '  (' + info + ')' : '')); if (!ok) failed++; }
}
console.log(failed ? `\n${failed} FAILED` : '\nAll tests passed'); process.exit(failed ? 1 : 0);
