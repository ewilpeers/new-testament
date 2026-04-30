"""
Generates books-data.js from your authoritative source files.

Reads:
  - bbl_names_books.py  (Latvian names)
  - GL1694_maxverses.csv (Glück verse counts per chapter)

The output is a pure JS file that defines `BOOKS_DATA` with:
  - slug:        url slug (e.g. "1_corinthians")
  - name_en:     "1 Corinthians" (display only — derived)
  - name_lv:     full Latvian name from bbl_names_books.py
  - testament:   "ot" | "nt"
  - canon:       canonical order index (0-based, OT then NT)
  - priority:    NT-first sort key for "11:1"-style queries
                 (gospels=0..3, acts=4, 1cor=5, 2cor=6, 1john=7, 2john=8,
                  3john=9, then rest of NT in canon order, then OT in canon order)
  - max_verses:  array of verse counts, indexed [chapter-1]

Run:  python build_books_data.py > books-data.js
"""

import csv
import io
import json
import re

# ---------------------------------------------------------------------------
# 1. Books in canonical order  (matches biblehub-style URL slugs)
# ---------------------------------------------------------------------------
BKSLIST = [
    "genesis","exodus","leviticus","numbers","deuteronomy","joshua","judges",
    "ruth","1_samuel","2_samuel","1_kings","2_kings","1_chronicles","2_chronicles",
    "ezra","nehemiah","esther","job","psalms","proverbs","ecclesiastes","songs",
    "isaiah","jeremiah","lamentations","ezekiel","daniel","hosea","joel","amos",
    "obadiah","jonah","micah","nahum","habakkuk","zephaniah","haggai","zechariah",
    "malachi",
    "matthew","mark","luke","john","acts","romans","1_corinthians","2_corinthians",
    "galatians","ephesians","philippians","colossians","1_thessalonians",
    "2_thessalonians","1_timothy","2_timothy","titus","philemon","hebrews","james",
    "1_peter","2_peter","1_john","2_john","3_john","jude","revelation",
]
NT_START = BKSLIST.index("matthew")

# Latvian names (from bbl_names_books.py — dropped here verbatim)
TO_LV = {
    "genesis":"Pirmā Mozus grāmata (Genesis)",
    "exodus":"Otrā Mozus grāmata (Exodus)",
    "leviticus":"Trešā Mozus grāmata (Leviticus)",
    "numbers":"Ceturtā Mozus grāmata (Numeri)",
    "deuteronomy":"Piektā Mozus grāmata (Deuteronomium)",
    "joshua":"Jozuas grāmata",
    "judges":"Soģu grāmata",
    "ruth":"Rutes grāmata",
    "1_samuel":"Pirmā Samuēla grāmata",
    "2_samuel":"Otrā Samuēla grāmata",
    "1_kings":"Pirmā Ķēniņu grāmata",
    "2_kings":"Otrā Ķēniņu grāmata",
    "1_chronicles":"Pirmā Laiku grāmata",
    "2_chronicles":"Otrā Laiku grāmata",
    "ezra":"Ezras grāmata",
    "nehemiah":"Nehemijas grāmata",
    "esther":"Esteres grāmata",
    "job":"Ījaba grāmata",
    "psalms":"Psalmi",
    "proverbs":"Salamana Pamācības",
    "ecclesiastes":"Salamans Mācītājs",
    "songs":"Salamana Augstā dziesma",
    "isaiah":"Jesajas grāmata",
    "jeremiah":"Jeremijas grāmata",
    "lamentations":"Raudu dziesmas",
    "ezekiel":"Ecēhiēla grāmata",
    "daniel":"Daniēla grāmata",
    "hosea":"Hozejas grāmata",
    "joel":"Joēla grāmata",
    "amos":"Āmosa grāmata",
    "obadiah":"Obadjas grāmata",
    "jonah":"Jonas grāmata",
    "micah":"Mihas grāmata",
    "nahum":"Nahuma grāmata",
    "habakkuk":"Habakuka grāmata",
    "zephaniah":"Cefanjas grāmata",
    "haggai":"Hagaja grāmata",
    "zechariah":"Caharijas grāmata",
    "malachi":"Maleahija grāmata",
    "matthew":"Mateja evaņģēlijs",
    "mark":"Marka evaņģēlijs",
    "luke":"Lūkas evaņģēlijs",
    "john":"Jāņa evaņģēlijs",
    "acts":"Apustuļu darbi",
    "romans":"Pāvila vēstule romiešiem",
    "1_corinthians":"Pāvila 1. vēstule korintiešiem",
    "2_corinthians":"Pāvila 2. vēstule korintiešiem",
    "galatians":"Pāvila vēstule galatiešiem",
    "ephesians":"Pāvila vēstule efeziešiem",
    "philippians":"Pāvila vēstule filipiešiem",
    "colossians":"Pāvila vēstule kolosiešiem",
    "1_thessalonians":"Pāvila 1. vēstule tesaloniķiešiem",
    "2_thessalonians":"Pāvila 2. vēstule tesaloniķiešiem",
    "1_timothy":"Pāvila 1. vēstule Timotejam",
    "2_timothy":"Pāvila 2. vēstule Timotejam",
    "titus":"Pāvila vēstule Titam",
    "philemon":"Pāvila vēstule Filemonam",
    "hebrews":"Vēstule ebrejiem",
    "james":"Jēkaba vēstule",
    "1_peter":"Pētera 1. vēstule",
    "2_peter":"Pētera 2. vēstule",
    "1_john":"Jāņa 1. vēstule",
    "2_john":"Jāņa 2. vēstule",
    "3_john":"Jāņa 3. vēstule",
    "jude":"Jūdas vēstule",
    "revelation":"Jāņa atklāsmes grāmata",
}

# ---------------------------------------------------------------------------
# 2. Glück verse counts (parsed from GL1694_maxverses.csv content embedded below)
#    Note: Glück's Job has 43 chapters, hence using these counts.
# ---------------------------------------------------------------------------
GLUCK_VERSE_CSV = open("/home/claude/bible-search/GL1694_maxverses.csv").read()

max_verses = {b: [] for b in BKSLIST}
reader = csv.reader(io.StringIO(GLUCK_VERSE_CSV))
header = next(reader)
for row in reader:
    if not row or len(row) < 4:
        continue
    _, bk, ch, mx = row[0], row[1], int(row[2]), int(row[3])
    if bk in max_verses:
        # ensure chapter index alignment
        while len(max_verses[bk]) < ch - 1:
            max_verses[bk].append(0)  # pad if any gaps (shouldn't happen)
        if len(max_verses[bk]) == ch - 1:
            max_verses[bk].append(mx)
        else:
            # already filled — overwrite (last wins)
            max_verses[bk][ch - 1] = mx

# ---------------------------------------------------------------------------
# 3. Display name in English (derive from slug)
# ---------------------------------------------------------------------------
SPECIAL_EN = {
    "songs": "Song of Solomon",
}
def slug_to_en(slug):
    if slug in SPECIAL_EN:
        return SPECIAL_EN[slug]
    parts = slug.split("_")
    if parts[0] in ("1","2","3"):
        return f"{parts[0]} {' '.join(p.capitalize() for p in parts[1:])}"
    return " ".join(p.capitalize() for p in parts)

# ---------------------------------------------------------------------------
# 4. NT-first priority order (per user spec)
#    gospels (0-3), acts (4), corinthians (5,6), johannine letters (7,8,9),
#    rest of NT in canonical order, then OT in canonical order
# ---------------------------------------------------------------------------
PRIORITY_HEAD = [
    "matthew","mark","luke","john","acts",
    "1_corinthians","2_corinthians",
    "1_john","2_john","3_john",
]
priority_order = list(PRIORITY_HEAD)
# rest of NT in canonical order, skipping ones already placed
for b in BKSLIST[NT_START:]:
    if b not in priority_order:
        priority_order.append(b)
# then OT in canonical order
for b in BKSLIST[:NT_START]:
    priority_order.append(b)

priority_index = {b: i for i, b in enumerate(priority_order)}

# ---------------------------------------------------------------------------
# 5. Build records
# ---------------------------------------------------------------------------
records = []
for canon, slug in enumerate(BKSLIST):
    rec = {
        "slug": slug,
        "name_en": slug_to_en(slug),
        "name_lv": TO_LV[slug],
        "testament": "nt" if canon >= NT_START else "ot",
        "canon": canon,
        "priority": priority_index[slug],
        "max_verses": max_verses[slug],
    }
    records.append(rec)

# Sanity check: every book should have at least one chapter
for r in records:
    assert r["max_verses"], f"empty max_verses for {r['slug']}"

# ---------------------------------------------------------------------------
# 6. Emit JS
# ---------------------------------------------------------------------------
out = []
out.append("// Auto-generated by build_books_data.py — do not edit by hand.")
out.append("// Source: bbl_names_books.py + GL1694_maxverses.csv")
out.append("window.BOOKS_DATA = " + json.dumps(records, ensure_ascii=False, separators=(",",":")) + ";")
out.append("")

print("\n".join(out))
