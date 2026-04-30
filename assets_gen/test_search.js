// Node test harness — exercises parseQuery / matchBooks / buildResults
// Run: node test_search.js
//
// Loads books-data.js then bible-search.js into a minimal `window` shim
// and runs assertions.

const fs = require('fs');
const path = require('path');

// --- minimal browser shim ---
global.window = {};
global.document = {
  readyState: 'complete',
  addEventListener() {},
  querySelectorAll() { return []; },
  createElement() { return { setAttribute(){}, addEventListener(){}, classList:{add(){}}, appendChild(){}, scrollIntoView(){} }; },
};

// load
eval(fs.readFileSync(path.join(__dirname, 'books-data.js'), 'utf8'));
eval(fs.readFileSync(path.join(__dirname, 'bible-search.js'), 'utf8'));

const { parseQuery, matchBooks, buildResults, fold } = window.BibleSearch;

let failures = 0;
function canonical(x) {
  if (x === null || typeof x !== 'object') return x;
  if (Array.isArray(x)) return x.map(canonical);
  const out = {};
  Object.keys(x).sort().forEach(k => { out[k] = canonical(x[k]); });
  return out;
}
function eq(a, b, label) {
  const sa = JSON.stringify(canonical(a));
  const sb = JSON.stringify(canonical(b));
  if (sa === sb) {
    console.log(`  ✔ ${label}`);
  } else {
    console.log(`  ✘ ${label}\n      got:    ${sa}\n      wanted: ${sb}`);
    failures++;
  }
}
function ok(cond, label) {
  if (cond) console.log(`  ✔ ${label}`);
  else { console.log(`  ✘ ${label}`); failures++; }
}

console.log('== parseQuery ==');
eq(parseQuery(''), null, 'empty -> null');
eq(parseQuery('   '), null, 'whitespace -> null');
eq(parseQuery('ma'), { bookFrag: 'ma' }, 'plain frag');
eq(parseQuery('MAT'), { bookFrag: 'mat' }, 'uppercase folded');
eq(parseQuery('Jāņa'), { bookFrag: 'jana' }, 'diacritics folded');
eq(parseQuery('mateja 5'), { bookFrag: 'mateja', chap: 5 }, 'book + chap');
eq(parseQuery('mateja 5:3'), { bookFrag: 'mateja', chap: 5, verse: 3 }, 'book + chap:verse');
eq(parseQuery('mateja 5:3-12'), { bookFrag: 'mateja', chap: 5, verse: 3, verseEnd: 12 }, 'book + range');
eq(parseQuery('11:1'), { chap: 11, verse: 1 }, 'bare chap:verse');
eq(parseQuery('11'), { chap: 11 }, 'bare chap');
eq(parseQuery('1 kor 13'), { bookFrag: '1 kor', chap: 13 }, 'numeric-prefixed book + chap');
eq(parseQuery('1kor 13:4-7'), { bookFrag: '1kor', chap: 13, verse: 4, verseEnd: 7 }, 'no-space numeric-prefixed book + range');

console.log('\n== matchBooks ==');
const ma = matchBooks('ma');
ok(ma.length > 1, 'ma matches more than one book');
ok(ma.some(b => b.slug === 'matthew'), 'ma -> matthew is a hit');
ok(ma.some(b => b.slug === 'mark'),    'ma -> mark is a hit');
ok(ma.some(b => b.slug === 'malachi'), 'ma -> malachi is a hit');
// ordering: NT-priority means matthew before mark before malachi
const idxMt = ma.findIndex(b => b.slug === 'matthew');
const idxMk = ma.findIndex(b => b.slug === 'mark');
const idxMl = ma.findIndex(b => b.slug === 'malachi');
ok(idxMt < idxMk, 'matthew before mark');
ok(idxMk < idxMl, 'mark before malachi (NT before OT)');

const oz = matchBooks('oz');
ok(oz.some(b => b.slug === 'hosea'),
   'oz -> hosea (Latvian "Hozejas grāmata", short "hozejas") — contains "oz"');
// "Mozus" appears in 5 OT book names — Genesis..Deuteronomy. Those should hit too.
ok(oz.some(b => b.slug === 'genesis'),
   'oz -> genesis (Latvian "Pirmā Mozus grāmata") — contains "oz"');

console.log('\n== buildResults ==');
const r1 = buildResults(parseQuery('11:1'), '', 100);
ok(r1.length > 30, '11:1 returns lots of books');
// First should be NT — Matthew 11:1 exists
ok(r1[0].book.slug === 'matthew' && r1[0].chap === 11 && r1[0].verse === 1,
   '11:1 first row is Matthew 11:1');
// Genesis 11:1 should also be present
ok(r1.some(r => r.book.slug === 'genesis' && r.verse === 1), 'Genesis 11:1 present');
// Books with fewer than 11 chapters should NOT be present (e.g. Ruth has 4)
ok(!r1.some(r => r.book.slug === 'ruth'), 'Ruth (4 chapters) excluded from 11:1');

const r2 = buildResults(parseQuery('11:22'), '', 100);
// Books whose chapter 11 has fewer than 22 verses should be excluded
// e.g. 1 Samuel 11 has 15 verses (per Glück counts)
const oneSamMatch = r2.find(r => r.book.slug === '1_samuel');
ok(!oneSamMatch, '1 Samuel excluded from 11:22 (chap 11 has only 15 verses)');
// Matthew 11 has 30 verses, so 11:22 is valid
ok(r2.some(r => r.book.slug === 'matthew'), 'Matthew 11:22 included');

const r3 = buildResults(parseQuery('mateja 5:3-12'), '', 100);
// First row chapter, then verses 3..12 (10 verse rows)
ok(r3[0].kind === 'chapter' && r3[0].book.slug === 'matthew' && r3[0].chap === 5,
   'range: row 0 is the chapter');
ok(r3[1].kind === 'verse' && r3[1].verse === 3, 'range: row 1 is v3');
ok(r3[10].kind === 'verse' && r3[10].verse === 12, 'range: row 10 is v12');
ok(r3.length === 11, 'range produces chapter + 10 verses');

const r4 = buildResults(parseQuery('mateja 99:1'), '', 100);
ok(r4.length === 0, 'invalid chapter -> no rows');

const r5 = buildResults(parseQuery('mateja 1:99'), '', 100);
ok(r5.length === 0, 'invalid verse -> no rows');

const r6 = buildResults(parseQuery('ma'), '', 100);
ok(r6.every(r => r.kind === 'book'), 'pure book frag -> only book rows');
ok(r6[0].book.slug === 'matthew', 'ma top hit is matthew');

// href integrity
const r7 = buildResults(parseQuery('mateja 5:3'), '/g', 100);
ok(r7[0].href === '/g/matthew/5.html#v3', 'href with explicit /g base');
const r8 = buildResults(parseQuery('mateja 5:3'), '', 100);
ok(r8[0].href === '/g/matthew/5.html#v3', 'href with auto base routes NT to /g');
const r9 = buildResults(parseQuery('genesis 1:1'), '', 100);
ok(r9[0].href === '/e/genesis/1.html#v1', 'href with auto base routes OT to /e');

console.log('\n' + (failures ? `❌ ${failures} failure(s)` : '✅ all passed'));
process.exit(failures ? 1 : 0);
