/* bible-search.js
 * Serverless reference search for the Bible explore site.
 *
 * Anchors:
 *   When a verse is specified, the link uses #v{n}. The chapter generator
 *   should add id="v{n}" to each .verse-container div. Without anchors, the
 *   link still loads the right page; the browser just doesn't scroll.
 *
 * No framework, no jQuery, ~6 KB minified.
 */
(function () {
  'use strict';

  if (!window.BOOKS_DATA) {
    console.error('[bible-search] BOOKS_DATA not loaded — include books-data.js first.');
    return;
  }

  // ---------------------------------------------------------------------
  // Diacritic-fold + normalize for matching
  //   "Mateja"  -> "mateja"
  //   "Jāņa"    -> "jana"
  //   "MAT"     -> "mat"
  //   "1. Kor." -> "1 kor"
  // ---------------------------------------------------------------------
  function fold(s) {
    return (s || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '') // strip combining marks
      .toLowerCase();
  }

  // ---------------------------------------------------------------------
  // Build search index over book metadata.
  // For each book we collect a few "haystacks": slug, English name,
  // Latvian name, plus a few common short forms / abbreviations derived
  // from the Latvian name (first word, prefixes "mat", "mar", "jan", ...).
  // ---------------------------------------------------------------------
  var BOOKS = window.BOOKS_DATA;

  // Derive a primary Latvian short name = first significant word of name_lv,
  // skipping leading ordinal prefixes like "Pirmā", "Otrā", "Trešā", "Pāvila",
  // "Vēstule" etc. — but we keep BOTH the short form and full form as
  // searchable haystacks, so a missed heuristic just costs zero coverage.
  var LV_STOP = new Set([
    'pirma','otra','tresa','ceturta','piekta', // ordinal feminine
    'pavila','vestule','grāmata','gramata',
  ]);

  function lvShort(nameLv) {
    var parts = fold(nameLv).split(/[\s().,]+/).filter(Boolean);
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i].replace(/[^a-z0-9]/g, '');
      if (p && !LV_STOP.has(p) && !/^\d+$/.test(p)) return p;
    }
    return parts[0] || '';
  }

  // Build per-book search record
  BOOKS.forEach(function (b) {
    b._slug_f = fold(b.slug.replace(/_/g, ' '));
    b._en_f   = fold(b.name_en);
    b._lv_f   = fold(b.name_lv);
    b._lv_short = lvShort(b.name_lv);
    // a flat haystack used for "contains" matching as fallback
    b._all = [b._slug_f, b._en_f, b._lv_f, b._lv_short].join(' | ');
  });

  // ---------------------------------------------------------------------
  // Parse a query string into a structured reference candidate.
  //
  // Accepted shapes (case + diacritics insensitive):
  //   "ma"                -> { bookFrag: "ma" }
  //   "mateja"            -> { bookFrag: "mateja" }
  //   "1 kor"             -> { bookFrag: "1 kor" }
  //   "1kor"              -> { bookFrag: "1kor" }      (treated as one frag)
  //   "mateja 5"          -> { bookFrag: "mateja", chap: 5 }
  //   "mateja 5:3"        -> { bookFrag: "mateja", chap: 5, verse: 3 }
  //   "mateja 5:3-12"     -> { bookFrag: "mateja", chap: 5, verse: 3, verseEnd: 12 }
  //   "11:1"              -> { chap: 11, verse: 1 }       (no book)
  //   "11"                -> { chap: 11 }                 (bare chapter — only
  //                            triggers if it parses cleanly as a number AND
  //                            no other token; otherwise treated as bookFrag.
  //                            Numeric-only queries are interpreted as chapter
  //                            search across all books.)
  //   ""                  -> null
  // ---------------------------------------------------------------------
  function parseQuery(raw) {
    var q = (raw || '').trim();
    if (!q) return null;

    // Normalize separators: any run of whitespace + " : " around colon
    var folded = fold(q);

    // Split into a leading book-fragment and an optional trailing
    // "<num>(:<num>(-<num>)?)?". The trailing block may also stand alone.
    //
    // Regex pieces:
    //   ^(.*?)             — book fragment (non-greedy, may be empty)
    //   \s*                — separator
    //   (\d+)              — chapter
    //   (?::(\d+)          — :verse
    //     (?:-(\d+))?      — -verseEnd
    //   )?
    //   $
    var m = folded.match(/^(.*?)\s*(\d+)(?::(\d+)(?:-(\d+))?)?$/);
    if (m) {
      var bf = m[1].trim();
      var chap = parseInt(m[2], 10);
      var v    = m[3] ? parseInt(m[3], 10) : null;
      var v2   = m[4] ? parseInt(m[4], 10) : null;
      // If bookFrag is empty AND no verse, treat as bare-chapter search.
      var out = { chap: chap };
      if (bf) out.bookFrag = bf;
      if (v != null)  out.verse = v;
      if (v2 != null) out.verseEnd = v2;
      return out;
    }

    // No numeric tail — pure book fragment (e.g. "mat", "1 kor")
    return { bookFrag: folded };
  }

  // ---------------------------------------------------------------------
  // Match books against a fragment.
  // Returns books with a quality score:
  //    0 = exact slug / Latvian short / English match
  //    1 = startswith on any haystack
  //    2 = contains on flat haystack
  // Lower score = better. Books without a match are excluded.
  // Within the same score, books are sorted by `priority` (NT-first per spec).
  // ---------------------------------------------------------------------
  function matchBooks(frag) {
    if (!frag) return BOOKS.slice().sort(function (a, b) {
      return a.priority - b.priority;
    });
    var f = fold(frag);
    var hits = [];
    BOOKS.forEach(function (b) {
      var score = -1;
      if (b._slug_f === f || b._en_f === f || b._lv_short === f) {
        score = 0;
      } else if (
        b._slug_f.startsWith(f) ||
        b._en_f.startsWith(f)   ||
        b._lv_f.startsWith(f)   ||
        b._lv_short.startsWith(f)
      ) {
        score = 1;
      } else if (b._all.indexOf(f) !== -1) {
        score = 2;
      }
      if (score >= 0) hits.push({ book: b, score: score });
    });
    hits.sort(function (a, b) {
      if (a.score !== b.score) return a.score - b.score;
      return a.book.priority - b.book.priority;
    });
    return hits.map(function (h) { return h.book; });
  }

  // ---------------------------------------------------------------------
  // Resolve a parsed query into a list of result rows (for the peek).
  // Each row = { kind, book, chap?, verse?, label, sublabel, href }
  //   kind: 'book' | 'chapter' | 'verse'
  // ---------------------------------------------------------------------
  function buildResults(parsed, baseAttr, maxRows) {
    var rows = [];
    if (!parsed) return rows;

    var books;
    if (parsed.bookFrag != null) {
      books = matchBooks(parsed.bookFrag);
    } else {
      // pure numeric query — all books considered, sorted by priority
      books = BOOKS.slice().sort(function (a, b) { return a.priority - b.priority; });
    }

    for (var i = 0; i < books.length; i++) {
      var b = books[i];

      // No chapter specified → row per book (link to chapter 1)
      if (parsed.chap == null) {
        rows.push(makeBookRow(b, baseAttr));
        if (rows.length >= maxRows) return rows;
        continue;
      }

      // Chapter specified → must exist in this book
      if (parsed.chap < 1 || parsed.chap > b.max_verses.length) continue;

      // Verse specified?
      if (parsed.verse == null) {
        // chapter row
        rows.push(makeChapterRow(b, parsed.chap, baseAttr));
        if (rows.length >= maxRows) return rows;
        continue;
      }

      // Single verse
      var maxV = b.max_verses[parsed.chap - 1];
      if (parsed.verse < 1 || parsed.verse > maxV) continue;

      if (parsed.verseEnd == null) {
        rows.push(makeVerseRow(b, parsed.chap, parsed.verse, baseAttr));
        if (rows.length >= maxRows) return rows;
        continue;
      }

      // Verse range — emit the chapter row, then each verse row up to maxRows.
      var vEnd = Math.min(parsed.verseEnd, maxV);
      if (vEnd < parsed.verse) continue;
      rows.push(makeChapterRow(b, parsed.chap, baseAttr));
      if (rows.length >= maxRows) return rows;
      for (var v = parsed.verse; v <= vEnd; v++) {
        rows.push(makeVerseRow(b, parsed.chap, v, baseAttr));
        if (rows.length >= maxRows) return rows;
      }
    }
    return rows;
  }

  function siteRoot(b, baseAttr) {
    if (baseAttr === '/e' || baseAttr === '/g') return baseAttr;
    return b.testament === 'nt' ? '/g' : '/e';
  }

   var nt_books=["matthew", "mark", "luke", "john", "acts", "romans", "1_corinthians", "2_corinthians", "galatians", "ephesians", "philippians", "colossians", "1_thessalonians", "2_thessalonians", "1_timothy", "2_timothy", "titus", "philemon", "hebrews", "james", "1_peter", "2_peter", "1_john", "2_john", "3_john", "jude", "revelation"];
  function makeBookRow(b, baseAttr) {
    
    return {
      kind: 'book',
      book: b,
      label: b.name_lv,
      sublabel: b.name_en,
      
      href: (b['slug']b in nt_books ? siteRoot(b, '/g') :siteRoot(b, '/e')) + '/' + b.slug + '/1.html',
    };
  }
  function makeChapterRow(b, chap, baseAttr) {
    return {
      kind: 'chapter',
      book: b, chap: chap,
      label: b.name_lv + ' ' + chap,
      sublabel: b.name_en + ' ' + chap,
      href: (b['slug'] in nt_books ? siteRoot(b, '/g') :siteRoot(b, '/e')) + '/' + b.slug + '/' + chap + '.html',
    };
  }
  function makeVerseRow(b, chap, verse, baseAttr) {
    return {
      kind: 'verse',
      book: b, chap: chap, verse: verse,
      label: b.name_lv + ' ' + chap + ':' + verse,
      sublabel: b.name_en + ' ' + chap + ':' + verse,
      href: (b['slug'] in nt_books ? siteRoot(b, '/g') :siteRoot(b, '/e')) + '/' + b.slug + '/' + chap + '.html#v' + verse,
    };
  }


  // ---------------------------------------------------------------------
  // UI
  // ---------------------------------------------------------------------
  var MAX_PEEK_ROWS = 30;

  function renderInto(container) {
    var baseAttr = container.getAttribute('data-base') || '';
    var placeholder = container.getAttribute('data-placeholder') ||
      'Meklēt grāmatā / nodaļā / pantā — piem. mateja 5:3 vai 11:1';

    container.classList.add('bs-root');
    container.innerHTML = ''; // clean
    var box = document.createElement('div');
    box.className = 'bs-box';
    var input = document.createElement('input');
    input.type = 'search';
    input.className = 'bs-input';
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('autocorrect', 'off');
    input.setAttribute('autocapitalize', 'off');
    input.setAttribute('spellcheck', 'false');
    input.placeholder = placeholder;
    input.setAttribute('aria-label', placeholder);
    var peek = document.createElement('div');
    peek.className = 'bs-peek';
    peek.setAttribute('role', 'listbox');
    peek.hidden = true;

    box.appendChild(input);
    box.appendChild(peek);
    container.appendChild(box);

    var activeIdx = -1;
    var currentRows = [];

    function update() {
      var parsed = parseQuery(input.value);
      currentRows = buildResults(parsed, baseAttr, MAX_PEEK_ROWS);
      activeIdx = currentRows.length ? 0 : -1;
      paint();
    }

    function paint() {
      if (!currentRows.length) {
        peek.hidden = true;
        peek.innerHTML = '';
        return;
      }
      peek.hidden = false;
      peek.innerHTML = '';
      currentRows.forEach(function (r, i) {
        var el = document.createElement('a');
        el.className = 'bs-row bs-row--' + r.kind + (i === activeIdx ? ' bs-row--active' : '');
        el.href = r.href;
        el.setAttribute('role', 'option');
        el.setAttribute('data-idx', String(i));
        var icon = r.kind === 'book' ? '📖' : (r.kind === 'chapter' ? '📑' : '✦');
        el.innerHTML =
          '<span class="bs-row-icon">' + icon + '</span>' +
          '<span class="bs-row-main">' +
            '<span class="bs-row-label">' + escapeHtml(r.label) + '</span>' +
            '<span class="bs-row-sub">' + escapeHtml(r.sublabel) + '</span>' +
          '</span>';
        // mousedown beats blur — prevents the peek from disappearing before navigation
        el.addEventListener('mousedown', function (ev) {
          ev.preventDefault();
          window.location.href = r.href;
        });
        peek.appendChild(el);
      });
    }

    function setActive(i) {
      if (!currentRows.length) return;
      activeIdx = ((i % currentRows.length) + currentRows.length) % currentRows.length;
      paint();
      var act = peek.querySelector('.bs-row--active');
      if (act && act.scrollIntoView) act.scrollIntoView({ block: 'nearest' });
    }

    input.addEventListener('input', update);
    input.addEventListener('focus', function () {
      if (input.value) update();
    });
    input.addEventListener('blur', function () {
      // small delay so click handlers fire first
      setTimeout(function () { peek.hidden = true; }, 120);
    });
    input.addEventListener('keydown', function (ev) {
      if (ev.key === 'ArrowDown') { ev.preventDefault(); setActive(activeIdx + 1); }
      else if (ev.key === 'ArrowUp')   { ev.preventDefault(); setActive(activeIdx - 1); }
      else if (ev.key === 'Enter') {
        if (activeIdx >= 0 && currentRows[activeIdx]) {
          ev.preventDefault();
          window.location.href = currentRows[activeIdx].href;
        }
      } else if (ev.key === 'Escape') {
        peek.hidden = true;
      }
    });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // Auto-mount any <... id="bible-search"> or class="bible-search"
  function mountAll() {
    var nodes = document.querySelectorAll(
      '#bible-search, .bible-search'
    );
    nodes.forEach(renderInto);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountAll);
  } else {
    mountAll();
  }

  // Expose for ad-hoc usage / tests
  window.BibleSearch = {
    parseQuery: parseQuery,
    matchBooks: matchBooks,
    buildResults: buildResults,
    mount: renderInto,
    fold: fold,
  };
})();
