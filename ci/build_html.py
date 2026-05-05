#!/usr/bin/env python3
"""
Convert bible JSON chapters → HTML pages.
Extracted from 5formatNT.ipynb for use in GitHub Actions CI.

Usage:
    python build_html.py                    # default: bible/ → html/
    python build_html.py --out-dir docs     # custom output dir (e.g. for GitHub Pages)
"""

import argparse
import json
import time
import unicodedata
from pathlib import Path

import pandas as pd

# ─── Config ──────────────────────────────────────────────────────────────────

BASE_DIR = Path("bible")

# ─── Morphology maps ─────────────────────────────────────────────────────────

POS_MAP = {
    "V": "Verb", "N": "Noun", "Adv": "Adverb", "Adj": "Adjective",
    "Art": "Article", "DPro": "Demonstrative Pronoun",
    "IPro": "Interrogative / Indefinite Pronoun",
    "PPro": "Personal / Possessive Pronoun",
    "RecPro": "Reciprocal Pronoun", "RelPro": "Relative Pronoun",
    "RefPro": "Reflexive Pronoun", "Prep": "Preposition",
    "Conj": "Conjunction", "I": "Interjection", "Prtcl": "Particle",
    "Heb": "Hebrew Word", "Aram": "Aramaic Word"
}
PERSON_MAP = {"1": "1st Person", "2": "2nd Person", "3": "3rd Person"}
TENSE_MAP = {"P": "Present", "I": "Imperfect", "F": "Future",
             "A": "Aorist", "R": "Perfect", "L": "Pluperfect"}
MOOD_MAP = {"I": "Indicative", "M": "Imperative",
            "S": "Subjunctive", "O": "Optative",
            "N": "Infinitive", "P": "Participle"}
VOICE_MAP = {"A": "Active", "M": "Middle", "P": "Passive", "M/P": "Middle or Passive"}
CASE_MAP = {"N": "Nominative", "V": "Vocative", "A": "Accusative",
            "G": "Genitive", "D": "Dative"}
NUMBER_MAP = {"S": "Singular", "P": "Plural"}
GENDER_MAP = {"M": "Masculine", "F": "Feminine", "N": "Neuter"}
COMPARISON_MAP = {"C": "Comparative", "S": "Superlative"}


# ─── Morphology parser ──────────────────────────────────────────────────────

def parse_morph_code(code):
    if not isinstance(code, str) or not code:
        return {}

    parts = code.split("-")
    pos_key = parts[0]
    result = {"part_of_speech": POS_MAP.get(pos_key, pos_key)}

    if len(parts) < 2:
        return result

    if pos_key == "V":
        tmv = parts[1]
        if len(tmv) >= 3:
            result["tense"] = TENSE_MAP.get(tmv[0])
            result["mood"] = MOOD_MAP.get(tmv[1])
            result["voice"] = VOICE_MAP.get(tmv[2])
        if len(parts) >= 3:
            third_part = parts[2]
            if result.get("mood") == "Participle":
                for char in third_part:
                    if char in CASE_MAP:
                        result["case"] = CASE_MAP.get(char)
                    elif char in GENDER_MAP:
                        result["gender"] = GENDER_MAP.get(char)
                    elif char in NUMBER_MAP:
                        result["number"] = NUMBER_MAP.get(char)
            else:
                if len(third_part) >= 2:
                    result["person"] = PERSON_MAP.get(third_part[0])
                    result["number"] = NUMBER_MAP.get(third_part[1])
        return result

    details = parts[1]
    for char in details:
        if char in CASE_MAP:
            result["case"] = CASE_MAP.get(char)
        elif char in GENDER_MAP:
            result["gender"] = GENDER_MAP.get(char)
        elif char in NUMBER_MAP:
            result["number"] = NUMBER_MAP.get(char)
        elif char in COMPARISON_MAP:
            result["comparison"] = COMPARISON_MAP.get(char)
        elif char in PERSON_MAP and "Pro" in pos_key:
            result["person"] = PERSON_MAP.get(char)

    return result


# ─── Audio players ───────────────────────────────────────────────────────────

AUDIO_BASE_URL = "https://t.noit.pro/strongs_p_g"

# Loaded once at startup; set of filenames like {"g0001.mp3", "g0001-2.mp3", ...}
_MP3_MANIFEST = None

def load_mp3_manifest(manifest_path="ci/mp3list.csv"):
    """Load mp3 manifest from CSV. Falls back to empty set if file missing."""
    global _MP3_MANIFEST
    p = Path(manifest_path)
    if p.exists():
        df = pd.read_csv(p)
        _MP3_MANIFEST = set(df["filename"].str.strip())
        print(f"  📋 Loaded {len(_MP3_MANIFEST)} entries from {p}")
    else:
        print(f"  ⚠️ {p} not found — audio players will be disabled")
        _MP3_MANIFEST = set()

def make_audio_players(strong_num_raw, v_num, word_idx):
    if _MP3_MANIFEST is None:
        load_mp3_manifest()

    if not strong_num_raw:
        return ""
    try:
        sn = int(strong_num_raw)
    except (ValueError, TypeError):
        return ""
    if sn <= 0:
        return ""

    skey = f"g{sn:04d}"

    variants = []
    if f"{skey}.mp3" in _MP3_MANIFEST:
        variants.append((f"{AUDIO_BASE_URL}/{skey}.mp3", ""))
    vi = 2
    while f"{skey}-{vi}.mp3" in _MP3_MANIFEST:
        variants.append((f"{AUDIO_BASE_URL}/{skey}-{vi}.mp3", f" {vi}"))
        vi += 1

    if not variants:
        return ""

    out = "<br>"
    for src, label in variants:
        uid = f"{skey}_v{v_num}_w{word_idx}{label.strip()}"
        out += (
            f'<audio id="aud_{uid}" src="{src}" '
            f'onended="document.getElementById(\'btn_{uid}\').textContent=\'▶{label}\'"></audio>'
            f'<button id="btn_{uid}" style="font-size:0.8em;padding:1px 5px;cursor:pointer" '
            f'onclick="var a=document.getElementById(\'aud_{uid}\');'
            f'if(a.paused){{a.play();this.textContent=\'⏹{label}\';}}else{{a.pause();a.currentTime=0;this.textContent=\'▶{label}\';}}">'
            f'▶{label}</button> '
        )
    return out


# ─── Build chapter data ─────────────────────────────────────────────────────

def build_chapter_from_json(book, chapter_num, strongs_g, lv_g, l24_g, l1694_g):
    chapter_path = BASE_DIR / str(book) / f"{chapter_num}.json"
    if not chapter_path.exists():
        print(f"  ❓ {chapter_path} not found, skipping.")
        return []

    with open(chapter_path, "r", encoding="utf-8") as f:
        verses_list = json.load(f)

    results = []

    for vi, verse_data in enumerate(verses_list):
        verse_num = vi + 1
        key = (book, chapter_num, verse_num)

        latvian_text = ""
        if key in lv_g.groups:
            latvian_text = lv_g.get_group(key).iloc[0]["text"]

        greek_words_json = verse_data.get("greek_words", [])
        leftover_latvian = verse_data.get("leftover_latvian", [])

        mappings = []
        greek_text_parts = []

        if key in strongs_g.groups:
            strong_sorted = strongs_g.get_group(key).sort_values("word")
            strong_data_list = strong_sorted.to_dict("records")
            greek_text_parts = list(strong_sorted["form"].astype(str))

            if len(strong_data_list) != len(greek_words_json):
                print(f"  ⚠️ {key}: strongs has {len(strong_data_list)} words, "
                      f"JSON has {len(greek_words_json)} — using min")

            for i in range(min(len(strong_data_list), len(greek_words_json))):
                gw = dict(greek_words_json[i])
                strong_row = strong_data_list[i]
                gw.update({
                    "strong_num": strong_row.get("strong_num"),
                    "form": strong_row.get("form"),
                    "translit_title": strong_row.get("translit_title"),
                    "translit": strong_row.get("translit"),
                    "strong_en_title": strong_row.get("strong_en_title")
                })
                mappings.append(gw)
        else:
            print(f"  ⚠️ {key}: no strongs data — skipping merge")
            for gw in greek_words_json:
                mappings.append(dict(gw))
            greek_text_parts = [gw.get("greek", "") for gw in greek_words_json]

        latvian_text_24=""
        if key in l24_g.groups:
            latvian_text_24 = " ".join(
                l24_g.get_group(key).sort_values("word_idx")["form"].astype(str)
            )
        else:
            latvian_text_24 = "-"
            print(f"⚠️ {key} not in l24_df latvian 24!")

        latvian_text_full_original_1694=""
        # ???? mapping ????
        if not key in l1694_g.groups:
            print(f"⚠️ {key} not in 1694 GLUCK!")
            latvian_text_full_original_1694="-"
        else:
            latvian_text_full_original_1694 =  " ".join(
                 l1694_g.get_group(key).sort_values("word_idx")["form"].astype(str)
        )
        results.append({
            "book": book,
            "chapter": chapter_num,
            "verse": verse_num,
            "greek_text": " ".join(greek_text_parts),
            "latvian_text": latvian_text,
            "latvian_text_24": latvian_text_24,
            "latvian_text_full_original_1694": latvian_text_full_original_1694,
            "mappings": mappings,
            "leftover_latvian": leftover_latvian
        })

    return results


# ─── HTML renderer ───────────────────────────────────────────────────────────

from gluck_1694_bible_map_pages import gl_map
def f_bcom_2_gluck_page(tple):
    if not tple:
        #wrong params, start with genesis then
        return -1
    #print( (tple[0], tple[1]) )
    if (tple[0], tple[1]) in gl_map:
        init, ls = gl_map[(tple[0], tple[1])]
        if tple[2] <= ls[0]:
            return init
        else:
            pointer = 1
            for i in range(1, len(ls)):
                if ls[i]<0:
                    pointer += ls[i] * -1
                if tple[2] <= ls[i]:
                    return init+pointer
                pointer +=1
        # the verse is larger than list shows, so return thousand days
        raise Exception(f"{tple} verse is larger than list shows!\nlist:\n{init, ls}")
        #return gl_map[tple]
    else:
        #not in map at all, so cover page returned
        raise Exception(f"{tple} not in map!")
        
def page_foto(pge):
    excepttions = {
2685: 'https://gramatas.lndb.lv/periodika2-viewer/?lang=fr#panel:pp|issue:722371|page:511',
2686: 'https://gramatas.lndb.lv/periodika2-viewer/?lang=fr#panel:pp|issue:722371|page:510',
2687: 'https://gramatas.lndb.lv/periodika2-viewer/?lang=fr#panel:pp|issue:722371|page:511',
2688: 'https://gramatas.lndb.lv/periodika2-viewer/?lang=fr#panel:pp|issue:722371|page:512',
2689: 'https://gramatas.lndb.lv/periodika2-viewer/?lang=fr#panel:pp|issue:722371|page:513',
2690: 'https://gramatas.lndb.lv/periodika2-viewer/?lang=fr#panel:pp|issue:722371|page:514',
    }
    if pge not in excepttions.keys():
        return  f"https://www.digitale-sammlungen.de/en/view/bsb10914821?page={pge}"#,{pge+1}"
    else: 
        return excepttions[pge]

def chapter_to_html_render(data):
    if not data or len(data) < 1:
        return ""

    css = """
    <style>
        body { font-family: 'Segoe UI', Tahoma, sans-serif; line-height: 1.6; color: #333; max-width: 1600px; margin: 0 auto; padding: 20px; background-color: #f8f9fa; }
        h1 { text-align: center; color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
        .verse-container { background-color: white; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); margin-bottom: 40px; padding: 25px; border-left: 5px solid #3498db; }
        .verse-header { font-weight: bold; color: #2c3e50; background-color: #ecf0f1; padding: 8px 15px; border-radius: 20px; margin-bottom: 15px; }
        .verse-lines { display: flex; flex-wrap: wrap; gap: 15px; margin-bottom: 20px; }
        .line-box { flex: 1 1 45%; min-width: 100px; }
        .line-label { font-weight: bold; color: #16a085; margin-bottom: 5px; }
        .line-content { background-color: #f0f7f4; padding: 12px; border-radius: 8px; border: 1px solid #bdc3c7; font-size: 1.1em; }
        .greek-line { background-color: #f0f0f0; font-family: 'Times New Roman', serif; }
        .mapping-table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 0.9em; }
        .mapping-table th { background-color: #3498db; color: white; padding: 12px; text-align: left; position: sticky; top: 0; }
        .mapping-table td { padding: 10px; border-bottom: 1px solid #ddd; vertical-align: top; }
        .greek-word { font-weight: bold; color: #8e44ad; font-size: 1.1em; }
        .greek-form { color: #7f8c8d; font-weight: normal; font-size: 0.85em; }
        .latvian-word { font-weight: bold; color: #27ae60; }
        .morph-info { font-style: italic; color: #e67e22; cursor: text; border-bottom: 1px dotted #e67e22; display: inline-block; }
        .definition-cell { color: #555; font-size: 0.85em; line-height: 1.3; max-width: 400px; }
        .index-badge { display: inline-block; width: 25px; height: 25px; background-color: #e74c3c; color: white; border-radius: 50%; text-align: center; line-height: 25px; margin-right: 8px; }
    /* gothic old print render */
@font-face {
    font-family: 'UnifrakturMaguntia';
    src: url('../fonts/unifrakturmaguntia-webfont.woff2') format('woff2'),
         url('../fonts/unifrakturmaguntia-webfont.woff') format('woff'),
         url('../fonts/unifrakturmaguntia-webfont.ttf') format('truetype');
    font-weight: normal;
    font-style: normal;
    font-display: swap;
}
.frankfurt-line {
    font-family: 'UnifrakturMaguntia', 'Times New Roman', serif;
   /* background-color: #fdf6ec; */
}
/* verse-collapse toggle */
.verse-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.verse-header-main {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
}
.verse-collapse {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: normal;
  font-size: 0.85em;
  color: #34495e;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}
.verse-collapse input {
  cursor: pointer;
  accent-color: #3498db;
  margin: 0;
}

body.details-collapsed .mapping-table { display: none; }
/* ~~~~~~~~ morphology parts colors ~~~~~~~~~~~~~~~~~ */
/* Morph POS color coding — shared across Hebrew and Greek */
.pos-verb     { color: #c0392b; }   /* red    — verbs */
.pos-noun     { color: #2c3e50; }   /* navy   — nouns */
.pos-adj      { color: #16a085; }   /* teal   — adjectives */
.pos-adv      { color: #d35400; }   /* orange — adverbs */
.pos-pron     { color: #8e44ad; }   /* purple — pronouns */
.pos-art      { color: #95a5a6; }   /* grey   — articles */
.pos-prep     { color: #2980b9; }   /* blue   — prepositions */
.pos-conj     { color: #7f8c8d; }   /* slate  — conjunctions */
.pos-particle { color: #7f8c8d; }
.pos-num      { color: #b7950b; }   /* gold   — numerals */
.pos-interj   { color: #e67e22; }
/* Slightly stronger weight on the form cell to make color pop */
.morph-colored { font-weight: 600; }
.morph-info.morph-colored { font-weight: normal; }  /* keep tag itself less shouty */
    </style>
    """
    srch_css="""
    <style>
/* bible-search.css
 * Matches the palette of the chapter renderer (#3498db / #2c3e50 / #ecf0f1).
 */
.bs-root {
  font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
  max-width: 720px;
  margin: 0 auto 16px;
}
.bs-box {
  position: relative;
}
.bs-input {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 14px;
  font-size: 1em;
  border: 2px solid #bdc3c7;
  border-radius: 8px;
  background: #fff;
  color: #2c3e50;
  transition: border-color .15s, box-shadow .15s;
}
.bs-input::placeholder { color: #95a5a6; }
.bs-input:focus {
  outline: none;
  border-color: #3498db;
  box-shadow: 0 0 0 3px rgba(52, 152, 219, .15);
}

.bs-peek {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: #fff;
  border: 1px solid #d5dbe0;
  border-radius: 8px;
  box-shadow: 0 8px 20px rgba(0,0,0,.08);
  max-height: 60vh;
  overflow-y: auto;
  z-index: 50;
}
.bs-peek[hidden] { display: none; }

.bs-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  text-decoration: none;
  color: inherit;
  border-bottom: 1px solid #f1f3f5;
  cursor: pointer;
}
.bs-row:last-child { border-bottom: none; }
.bs-row:hover, .bs-row--active {
  background: #ecf0f1;
}
.bs-row-icon {
  flex: 0 0 auto;
  font-size: 1.05em;
  line-height: 1;
  width: 1.5em;
  text-align: center;
}
.bs-row-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.bs-row-label {
  font-weight: 600;
  color: #2c3e50;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bs-row-sub {
  font-size: 0.82em;
  color: #7f8c8d;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* slight visual cue per row kind */
.bs-row--book    .bs-row-icon { color: #16a085; }
.bs-row--chapter .bs-row-icon { color: #2980b9; }
.bs-row--verse   .bs-row-icon { color: #8e44ad; }

/* mobile tweaks */
@media (max-width: 540px) {
  .bs-input { font-size: 16px; } /* avoid iOS auto-zoom */
  .bs-peek { max-height: 70vh; }
}
    </style>
"""
    books_data_js="""
<script type="text/javascript">
// Auto-generated by build_books_data.py — do not edit by hand.
// Source: bbl_names_books.py + GL1694_maxverses.csv
window.BOOKS_DATA = [{"slug":"genesis","name_en":"Genesis","name_lv":"Pirmā Mozus grāmata (Genesis)","testament":"ot","canon":0,"priority":27,"max_verses":[31,25,24,26,32,22,24,22,29,32,32,20,18,24,21,16,27,33,38,18,34,24,20,67,34,35,46,22,35,43,55,32,20,31,29,43,36,30,23,23,57,38,34,34,28,34,31,22,33,26]},{"slug":"exodus","name_en":"Exodus","name_lv":"Otrā Mozus grāmata (Exodus)","testament":"ot","canon":1,"priority":28,"max_verses":[22,25,22,31,23,30,25,32,35,29,10,51,22,31,27,36,16,27,25,26,36,31,33,18,40,37,21,43,46,38,18,35,23,35,35,38,29,31,43,38]},{"slug":"leviticus","name_en":"Leviticus","name_lv":"Trešā Mozus grāmata (Leviticus)","testament":"ot","canon":2,"priority":29,"max_verses":[17,16,17,35,19,30,38,36,24,20,47,8,59,57,32,34,16,30,37,27,24,33,44,23,55,46,34]},{"slug":"numbers","name_en":"Numbers","name_lv":"Ceturtā Mozus grāmata (Numeri)","testament":"ot","canon":3,"priority":30,"max_verses":[54,34,51,49,31,26,89,26,23,36,35,15,33,45,41,50,13,32,22,29,35,41,30,25,18,65,23,31,39,16,54,42,56,29,34,13]},{"slug":"deuteronomy","name_en":"Deuteronomy","name_lv":"Piektā Mozus grāmata (Deuteronomium)","testament":"ot","canon":4,"priority":31,"max_verses":[46,37,29,49,33,25,26,20,29,22,32,32,18,29,23,22,20,22,21,20,23,30,25,22,19,19,26,68,29,20,30,52,29,12]},{"slug":"joshua","name_en":"Joshua","name_lv":"Jozuas grāmata","testament":"ot","canon":5,"priority":32,"max_verses":[18,24,17,24,15,27,26,35,27,43,23,24,33,15,63,10,18,28,51,9,45,34,16,33]},{"slug":"judges","name_en":"Judges","name_lv":"Soģu grāmata","testament":"ot","canon":6,"priority":33,"max_verses":[36,23,31,24,31,40,25,35,57,18,40,15,25,20,20,31,13,31,30,48,25]},{"slug":"ruth","name_en":"Ruth","name_lv":"Rutes grāmata","testament":"ot","canon":7,"priority":34,"max_verses":[22,23,18,22]},{"slug":"1_samuel","name_en":"1 Samuel","name_lv":"Pirmā Samuēla grāmata","testament":"ot","canon":8,"priority":35,"max_verses":[28,36,22,22,12,21,17,22,27,27,15,25,23,52,35,23,58,30,24,43,15,23,28,23,44,25,12,25,11,31,13]},{"slug":"2_samuel","name_en":"2 Samuel","name_lv":"Otrā Samuēla grāmata","testament":"ot","canon":9,"priority":36,"max_verses":[27,32,39,12,25,23,29,18,13,19,27,31,39,33,37,23,29,33,43,26,22,51,39,25]},{"slug":"1_kings","name_en":"1 Kings","name_lv":"Pirmā Ķēniņu grāmata","testament":"ot","canon":10,"priority":37,"max_verses":[53,46,28,34,18,38,51,66,28,29,43,33,34,31,34,34,24,46,21,43,29,54]},{"slug":"2_kings","name_en":"2 Kings","name_lv":"Otrā Ķēniņu grāmata","testament":"ot","canon":11,"priority":38,"max_verses":[18,25,27,44,27,33,20,29,37,36,21,21,25,29,38,20,41,37,37,21,26,20,37,20,30]},{"slug":"1_chronicles","name_en":"1 Chronicles","name_lv":"Pirmā Laiku grāmata","testament":"ot","canon":12,"priority":39,"max_verses":[54,55,25,44,26,81,40,40,44,14,47,40,14,17,29,43,27,17,19,8,30,19,32,31,31,32,34,21,30]},{"slug":"2_chronicles","name_en":"2 Chronicles","name_lv":"Otrā Laiku grāmata","testament":"ot","canon":13,"priority":40,"max_verses":[17,18,17,22,14,42,22,18,31,19,23,16,22,15,19,14,19,34,11,37,20,12,21,27,28,23,9,27,36,27,21,33,25,33,27,23]},{"slug":"ezra","name_en":"Ezra","name_lv":"Ezras grāmata","testament":"ot","canon":14,"priority":41,"max_verses":[11,70,13,24,17,23,28,36,15,44]},{"slug":"nehemiah","name_en":"Nehemiah","name_lv":"Nehemijas grāmata","testament":"ot","canon":15,"priority":42,"max_verses":[11,20,32,23,19,19,73,18,38,39,36,47,31]},{"slug":"esther","name_en":"Esther","name_lv":"Esteres grāmata","testament":"ot","canon":16,"priority":43,"max_verses":[22,23,15,17,14,14,10,17,32,3]},{"slug":"job","name_en":"Job","name_lv":"Ījaba grāmata","testament":"ot","canon":17,"priority":44,"max_verses":[22,13,26,21,27,30,21,22,35,22,20,25,28,22,35,22,16,21,29,29,34,30,17,25,6,14,23,28,25,31,40,22,33,37,16,33,24,38,30,24,28,17,17]},{"slug":"psalms","name_en":"Psalms","name_lv":"Psalmi","testament":"ot","canon":18,"priority":45,"max_verses":[6,12,9,9,13,11,18,10,21,18,8,9,7,7,5,11,15,51,15,10,14,32,6,10,22,12,14,9,11,13,25,11,22,23,28,13,40,23,14,18,14,12,5,27,18,12,10,15,21,23,21,11,7,9,24,14,12,12,18,14,9,13,12,11,14,20,8,36,37,5,24,20,28,23,11,13,21,72,13,20,17,8,19,13,14,17,7,19,53,17,16,16,5,23,11,13,12,9,9,5,8,29,22,35,45,48,43,14,31,7,10,10,9,8,18,19,2,29,176,7,8,9,4,8,5,6,5,6,8,8,3,18,3,3,21,26,9,8,24,14,10,7,12,15,21,10,20,14,9,6]},{"slug":"proverbs","name_en":"Proverbs","name_lv":"Salamana Pamācības","testament":"ot","canon":19,"priority":46,"max_verses":[33,22,35,27,23,35,27,36,18,32,31,28,25,35,33,33,28,24,29,30,31,29,35,34,28,28,27,28,27,33,31]},{"slug":"ecclesiastes","name_en":"Ecclesiastes","name_lv":"Salamans Mācītājs","testament":"ot","canon":20,"priority":47,"max_verses":[18,26,22,16,19,11,29,17,18,20,10,14]},{"slug":"songs","name_en":"Song of Solomon","name_lv":"Salamana Augstā dziesma","testament":"ot","canon":21,"priority":48,"max_verses":[17,17,11,16,16,13,13,14]},{"slug":"isaiah","name_en":"Isaiah","name_lv":"Jesajas grāmata","testament":"ot","canon":22,"priority":49,"max_verses":[31,22,26,6,30,13,25,22,21,34,16,6,22,32,9,14,14,7,25,6,17,25,18,23,12,21,13,29,24,33,9,20,24,17,10,22,38,22,8,31,29,25,28,28,25,13,15,22,26,11,23,15,13,17,13,12,21,14,21,22,11,12,19,12,25,24]},{"slug":"jeremiah","name_en":"Jeremiah","name_lv":"Jeremijas grāmata","testament":"ot","canon":23,"priority":50,"max_verses":[19,37,25,31,31,30,34,22,26,25,23,17,27,22,21,21,27,23,15,18,14,30,40,10,38,24,22,17,32,24,40,44,26,22,19,32,21,28,18,16,18,22,13,30,5,28,7,47,39,46,64,34]},{"slug":"lamentations","name_en":"Lamentations","name_lv":"Raudu dziesmas","testament":"ot","canon":24,"priority":51,"max_verses":[22,22,66,22,22]},{"slug":"ezekiel","name_en":"Ezekiel","name_lv":"Ecēhiēla grāmata","testament":"ot","canon":25,"priority":52,"max_verses":[28,10,27,17,17,14,27,18,11,22,25,28,23,23,8,63,24,32,13,49,32,31,49,27,17,21,36,26,21,26,18,32,33,31,15,38,28,23,29,49,26,20,27,31,25,24,23,35]},{"slug":"daniel","name_en":"Daniel","name_lv":"Daniēla grāmata","testament":"ot","canon":26,"priority":53,"max_verses":[21,49,30,34,31,28,28,27,27,21,45,13]},{"slug":"hosea","name_en":"Hosea","name_lv":"Hozejas grāmata","testament":"ot","canon":27,"priority":54,"max_verses":[11,23,5,19,15,11,16,14,17,15,12,14,15,9]},{"slug":"joel","name_en":"Joel","name_lv":"Joēla grāmata","testament":"ot","canon":28,"priority":55,"max_verses":[20,32,21]},{"slug":"amos","name_en":"Amos","name_lv":"Āmosa grāmata","testament":"ot","canon":29,"priority":56,"max_verses":[15,16,15,13,27,14,17,14,15]},{"slug":"obadiah","name_en":"Obadiah","name_lv":"Obadjas grāmata","testament":"ot","canon":30,"priority":57,"max_verses":[21]},{"slug":"jonah","name_en":"Jonah","name_lv":"Jonas grāmata","testament":"ot","canon":31,"priority":58,"max_verses":[16,10,10,11]},{"slug":"micah","name_en":"Micah","name_lv":"Mihas grāmata","testament":"ot","canon":32,"priority":59,"max_verses":[16,13,12,13,14,16,20]},{"slug":"nahum","name_en":"Nahum","name_lv":"Nahuma grāmata","testament":"ot","canon":33,"priority":60,"max_verses":[15,13,19]},{"slug":"habakkuk","name_en":"Habakkuk","name_lv":"Habakuka grāmata","testament":"ot","canon":34,"priority":61,"max_verses":[17,20,19]},{"slug":"zephaniah","name_en":"Zephaniah","name_lv":"Cefanjas grāmata","testament":"ot","canon":35,"priority":62,"max_verses":[18,15,20]},{"slug":"haggai","name_en":"Haggai","name_lv":"Hagaja grāmata","testament":"ot","canon":36,"priority":63,"max_verses":[14,24]},{"slug":"zechariah","name_en":"Zechariah","name_lv":"Caharijas grāmata","testament":"ot","canon":37,"priority":64,"max_verses":[21,13,10,14,11,15,14,23,17,12,17,14,9,21]},{"slug":"malachi","name_en":"Malachi","name_lv":"Maleahija grāmata","testament":"ot","canon":38,"priority":65,"max_verses":[14,17,18,6]},{"slug":"matthew","name_en":"Matthew","name_lv":"Mateja evaņģēlijs","testament":"nt","canon":39,"priority":0,"max_verses":[25,23,17,25,48,34,29,34,38,42,30,50,58,36,39,28,27,35,30,34,46,46,39,51,46,75,66,20]},{"slug":"mark","name_en":"Mark","name_lv":"Marka evaņģēlijs","testament":"nt","canon":40,"priority":1,"max_verses":[45,28,35,41,43,56,37,38,50,52,33,44,37,72,47,20]},{"slug":"luke","name_en":"Luke","name_lv":"Lūkas evaņģēlijs","testament":"nt","canon":41,"priority":2,"max_verses":[80,52,38,44,39,49,50,56,62,42,54,59,35,35,32,31,37,43,48,47,38,71,56,53]},{"slug":"john","name_en":"John","name_lv":"Jāņa evaņģēlijs","testament":"nt","canon":42,"priority":3,"max_verses":[52,25,36,54,47,71,53,59,41,42,57,50,38,31,27,33,26,40,42,31,25]},{"slug":"acts","name_en":"Acts","name_lv":"Apustuļu darbi","testament":"nt","canon":43,"priority":4,"max_verses":[26,47,26,37,42,15,60,40,43,48,30,25,52,28,41,40,34,28,40,38,40,30,35,27,27,32,44,31]},{"slug":"romans","name_en":"Romans","name_lv":"Pāvila vēstule romiešiem","testament":"nt","canon":44,"priority":10,"max_verses":[32,29,31,25,21,23,25,39,33,21,36,21,14,23,33,27]},{"slug":"1_corinthians","name_en":"1 Corinthians","name_lv":"Pāvila 1. vēstule korintiešiem","testament":"nt","canon":45,"priority":5,"max_verses":[31,16,23,21,13,20,40,13,27,33,34,31,13,40,58,24]},{"slug":"2_corinthians","name_en":"2 Corinthians","name_lv":"Pāvila 2. vēstule korintiešiem","testament":"nt","canon":46,"priority":6,"max_verses":[24,17,18,18,21,18,16,24,15,18,33,21,13]},{"slug":"galatians","name_en":"Galatians","name_lv":"Pāvila vēstule galatiešiem","testament":"nt","canon":47,"priority":11,"max_verses":[24,21,29,31,26,18]},{"slug":"ephesians","name_en":"Ephesians","name_lv":"Pāvila vēstule efeziešiem","testament":"nt","canon":48,"priority":12,"max_verses":[23,22,21,32,33,24]},{"slug":"philippians","name_en":"Philippians","name_lv":"Pāvila vēstule filipiešiem","testament":"nt","canon":49,"priority":13,"max_verses":[30,30,21,23]},{"slug":"colossians","name_en":"Colossians","name_lv":"Pāvila vēstule kolosiešiem","testament":"nt","canon":50,"priority":14,"max_verses":[29,23,25,18]},{"slug":"1_thessalonians","name_en":"1 Thessalonians","name_lv":"Pāvila 1. vēstule tesaloniķiešiem","testament":"nt","canon":51,"priority":15,"max_verses":[10,20,13,18,28]},{"slug":"2_thessalonians","name_en":"2 Thessalonians","name_lv":"Pāvila 2. vēstule tesaloniķiešiem","testament":"nt","canon":52,"priority":16,"max_verses":[12,17,18]},{"slug":"1_timothy","name_en":"1 Timothy","name_lv":"Pāvila 1. vēstule Timotejam","testament":"nt","canon":53,"priority":17,"max_verses":[20,15,16,16,25,21]},{"slug":"2_timothy","name_en":"2 Timothy","name_lv":"Pāvila 2. vēstule Timotejam","testament":"nt","canon":54,"priority":18,"max_verses":[18,26,17,22]},{"slug":"titus","name_en":"Titus","name_lv":"Pāvila vēstule Titam","testament":"nt","canon":55,"priority":19,"max_verses":[16,15,15]},{"slug":"philemon","name_en":"Philemon","name_lv":"Pāvila vēstule Filemonam","testament":"nt","canon":56,"priority":20,"max_verses":[25]},{"slug":"hebrews","name_en":"Hebrews","name_lv":"Vēstule ebrejiem","testament":"nt","canon":57,"priority":21,"max_verses":[14,18,19,16,14,20,28,13,28,39,40,29,25]},{"slug":"james","name_en":"James","name_lv":"Jēkaba vēstule","testament":"nt","canon":58,"priority":22,"max_verses":[27,26,18,17,20]},{"slug":"1_peter","name_en":"1 Peter","name_lv":"Pētera 1. vēstule","testament":"nt","canon":59,"priority":23,"max_verses":[25,25,22,19,14]},{"slug":"2_peter","name_en":"2 Peter","name_lv":"Pētera 2. vēstule","testament":"nt","canon":60,"priority":24,"max_verses":[21,22,18]},{"slug":"1_john","name_en":"1 John","name_lv":"Jāņa 1. vēstule","testament":"nt","canon":61,"priority":7,"max_verses":[10,29,24,21,21]},{"slug":"2_john","name_en":"2 John","name_lv":"Jāņa 2. vēstule","testament":"nt","canon":62,"priority":8,"max_verses":[13]},{"slug":"3_john","name_en":"3 John","name_lv":"Jāņa 3. vēstule","testament":"nt","canon":63,"priority":9,"max_verses":[14]},{"slug":"jude","name_en":"Jude","name_lv":"Jūdas vēstule","testament":"nt","canon":64,"priority":25,"max_verses":[25]},{"slug":"revelation","name_en":"Revelation","name_lv":"Jāņa atklāsmes grāmata","testament":"nt","canon":65,"priority":26,"max_verses":[20,29,22,11,14,17,17,13,21,11,19,18,18,20,8,21,18,24,21,15,27,21]}];
</script>
"""
    bib_search_js ="""
<script type="text/javascript">
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
      .replace(/[\\u0300-\\u036f]/g, '') // strip combining marks
      .toLowerCase();
  }

  // Normalize a query fragment so matching is forgiving of dots/extra spaces:
  //   "1. kor"  -> "1 kor"
  //   "1.cor"   -> "1 cor"
  //   "1kor"    -> "1kor" (matched directly by the {ord}{stem} haystacks)
  function normFrag(f) {
    return fold(f).replace(/[.,]+/g, ' ').replace(/\\s+/g, ' ').trim();
  }

  // ---------------------------------------------------------------------
  // Build search index over book metadata.
  // For each book we collect a list of "haystacks": slug, English name,
  // Latvian name, Latvian short, plus — for numbered books — a set of
  // ordinal-aware short forms ("1 kor", "1kor", "1k", "1 cor", "1c", ...).
  // ---------------------------------------------------------------------
  var BOOKS = window.BOOKS_DATA;

  // Ordinal prefixes / common filler words to skip when picking a Latvian
  // short name. Kept conservative: a missed heuristic just costs zero
  // coverage, since the full lv name is also in the haystack.
  var LV_STOP = new Set([
    'pirma','otra','tresa','ceturta','piekta', // ordinal feminine
    'pavila','vestule','grāmata','gramata',
  ]);

  function lvShort(nameLv) {
    var parts = fold(nameLv).split(/[\\s().,]+/).filter(Boolean);
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i].replace(/[^a-z0-9]/g, '');
      if (p && !LV_STOP.has(p) && !/^\\d+$/.test(p)) return p;
    }
    return parts[0] || '';
  }

  // Extract a leading ordinal digit from a folded name, if any:
  //   "1. pavila vestule korintiesiem" -> "1"
  //   "1 corinthians"                  -> "1"
  //   "matthew"                        -> ""
  function leadingOrdinal(folded) {
    var m = folded.match(/^(\\d+)\\b/);
    return m ? m[1] : '';
  }

  // Build per-book search record
  BOOKS.forEach(function (b) {
    b._slug_f   = fold(b.slug.replace(/_/g, ' '));
    b._en_f     = fold(b.name_en);
    b._lv_f     = fold(b.name_lv);
    b._lv_short = lvShort(b.name_lv);

    // Collect a list of haystacks. Anything in this list is matched against
    // the query independently (exact / prefix / contains).
    var hay = [b._slug_f, b._en_f, b._lv_f, b._lv_short];

    // Ordinal-aware short forms. For a numbered book, expose every reasonable
    // shorthand a user might type — "1 kor", "1kor", "1k", "1 cor", "1c", etc.
    // Drawn from both the Latvian short and the English name's first word.
    var ord = leadingOrdinal(b._lv_f) || leadingOrdinal(b._en_f) || leadingOrdinal(b._slug_f);
    if (ord) {
      var enWord = b._en_f.replace(/^\\d+\\s*/, '').split(/\\s+/)[0] || '';
      var lvWord = b._lv_short || '';
      var stems  = [];
      // Various-length prefixes of each word (1..4 chars), plus the full word
      [enWord, lvWord].forEach(function (w) {
        if (!w) return;
        for (var n = 1; n <= Math.min(4, w.length); n++) stems.push(w.slice(0, n));
        stems.push(w);
      });
      // Dedupe + emit "{ord}{stem}" and "{ord} {stem}"
      var seen = {};
      stems.forEach(function (s) {
        if (!s || seen[s]) return;
        seen[s] = 1;
        hay.push(ord + s);
        hay.push(ord + ' ' + s);
      });
    }

    b._hay = hay;             // array of haystacks for exact/prefix tests
    b._all = hay.join(' | '); // flat haystack for contains fallback
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

    var folded = fold(q);

    // Split into a leading book-fragment and an optional trailing
    // "<num>(:<num>(-<num>)?)?". The trailing block may also stand alone.
    //
    // Regex pieces:
    //   ^(.*?)             — book fragment (non-greedy, may be empty)
    //   \\s*                — separator
    //   (\\d+)              — chapter
    //   (?::(\\d+)          — :verse
    //     (?:-(\\d+))?      — -verseEnd
    //   )?
    //   $
    var m = folded.match(/^(.*?)\\s*(\\d+)(?::(\\d+)(?:-(\\d+))?)?$/);
    if (m) {
      var bf   = normFrag(m[1]);
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

    // No numeric tail — pure book fragment (e.g. "mat", "1 kor", "1. kor")
    return { bookFrag: normFrag(folded) };
  }

  // ---------------------------------------------------------------------
  // Match books against a fragment.
  // Returns books with a quality score:
  //    0 = exact match on any haystack
  //    1 = startswith on any haystack
  //    2 = contains on flat haystack
  // Lower score = better. Books without a match are excluded.
  // Within the same score, books are sorted by `priority` (NT-first per spec).
  // ---------------------------------------------------------------------
  function matchBooks(frag) {
    if (!frag) return BOOKS.slice().sort(function (a, b) {
      return a.priority - b.priority;
    });
    var f = normFrag(frag);
    var hits = [];
    BOOKS.forEach(function (b) {
      var score = -1;
      // Exact on any haystack
      for (var i = 0; i < b._hay.length; i++) {
        if (b._hay[i] === f) { score = 0; break; }
      }
      // Prefix on any haystack
      if (score < 0) {
        for (var j = 0; j < b._hay.length; j++) {
          if (b._hay[j] && b._hay[j].indexOf(f) === 0) { score = 1; break; }
        }
      }
      // Contains fallback
      if (score < 0 && b._all.indexOf(f) !== -1) score = 2;
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

  var nt_books = ["matthew", "mark", "luke", "john", "acts", "romans", "1_corinthians", "2_corinthians", "galatians", "ephesians", "philippians", "colossians", "1_thessalonians", "2_thessalonians", "1_timothy", "2_timothy", "titus", "philemon", "hebrews", "james", "1_peter", "2_peter", "1_john", "2_john", "3_john", "jude", "revelation"];

  function makeBookRow(b, baseAttr) {
    return {
      kind: 'book',
      book: b,
      label: b.name_lv,
      sublabel: b.name_en,
      href: (nt_books.includes(b['slug']) ? siteRoot(b, '/g') : siteRoot(b, '/e')) + '/' + b.slug + '/1.html',
    };
  }
  function makeChapterRow(b, chap, baseAttr) {
    return {
      kind: 'chapter',
      book: b, chap: chap,
      label: b.name_lv + ' ' + chap,
      sublabel: b.name_en + ' ' + chap,
      href: (nt_books.includes(b['slug']) ? siteRoot(b, '/g') : siteRoot(b, '/e')) + '/' + b.slug + '/' + chap + '.html',
    };
  }
  function makeVerseRow(b, chap, verse, baseAttr) {
    return {
      kind: 'verse',
      book: b, chap: chap, verse: verse,
      label: b.name_lv + ' ' + chap + ':' + verse,
      sublabel: b.name_en + ' ' + chap + ':' + verse,
      href: (nt_books.includes(b['slug']) ? siteRoot(b, '/g') : siteRoot(b, '/e')) + '/' + b.slug + '/' + chap + '.html#v' + verse,
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
    normFrag: normFrag,
  };
})();
document.addEventListener('DOMContentLoaded', function () {
  var boxes = document.querySelectorAll('.verse-collapse-cb');
  boxes.forEach(function (cb) {
    cb.addEventListener('change', function () {
      var on = cb.checked;
      document.body.classList.toggle('details-collapsed', on);
      // sync all other checkboxes
      boxes.forEach(function (other) { if (other !== cb) other.checked = on; });
    });
  });
});
</script>
"""
    book_title = data[0].get('book', 'Bible').capitalize()
    chapter = data[0].get('chapter', '')
    html = f"<!DOCTYPE html><html><head><meta charset='UTF-8'>{css}{srch_css}{books_data_js}{bib_search_js}</head><body>"
    html += f"<h1>📖 {book_title} Chapter {chapter}</h1>"
    html += '<div id="bible-search" data-base="/g"></div>'

    for verse_data in data:
        v_num = verse_data.get('verse')
        locus = f"{book_title} {chapter}:{v_num}"

        html += f'<div class="verse-container" id="v{v_num}">'
        html += (
    f'<div class="verse-header">'
    f'<span class="verse-header-main"><span class="index-badge">{v_num}</span> {locus}</span>'
    f'<label class="verse-collapse" title="Saglabā tikai panta tekstu, paslēpj vārdu detaļas">'
    f'<input type="checkbox" class="verse-collapse-cb"> 📋 Tikai pants'
    f'</label>'
    f'</div>'
    )

        html += f'''
        <div class="verse-lines">
            <div class="line-box">
                <div class="line-label">🇬🇷 Greek:</div>
                <div class="line-content greek-line">{verse_data.get('greek_text', '')}</div>
            </div>
            <div class="line-box">
                <div class="line-label">🇱🇻 Latvian (65):</div>
                <div class="line-content">{verse_data.get('latvian_text', '')}</div>
            </div>
            <div class="line-box">
                <div class="line-label">🇱🇻 Latvian (1694):</div>
                <div class="line-content frankfurt-line">{verse_data.get('latvian_text_full_original_1694', '')} <a href="{page_foto(f_bcom_2_gluck_page((data[0].get('book', 'Bible'), chapter, v_num)))}" target="_blank" style="text-decoration: none;">📖</a></div>
            </div>
            <div class="line-box">
                <div class="line-label">🇱🇻 Latvian (2024):</div>
                <div class="line-content">{verse_data.get('latvian_text_24', '')}</div>
            </div>
        </div>
        '''

        html += '''<table class="mapping-table"><thead><tr>
                    <th>Greek (Form)</th><th>Latvian</th><th>Strong's</th><th>Morphology</th><th>Definition</th>
                </tr></thead><tbody>'''
        for m_idx, m in enumerate(verse_data.get('mappings', [])):
            lv_words = ", ".join(m.get('latvian', [])) if m.get('latvian') else "-"
            strong = f"G{m.get('strong_num')}" if m.get('strong_num') else "-"

            raw_morph = m.get('strong_en_title', '')
            morph_dict = parse_morph_code(raw_morph)
            full_desc = ", ".join([f"{k.replace('_', ' ').lower()}: {v.title()}" for k, v in morph_dict.items() if v])
            pos_cls_gr = greek_pos_class(raw_morph)
            audio_html = make_audio_players(m.get('strong_num'), v_num, m_idx)

            html += f'''
                <tr>
                    <td class="greek-word">
                        <span class="{pos_cls_gr} morph-colored">{m.get('form', '')}</span> <span class="greek-form">({m.get('translit', '')})</span>
                        {audio_html}
                    </td>
                    <td class="latvian-word">{lv_words}</td>
                    <td><a href="https://www.blueletterbible.org/lexicon/{strong.lower()}/" target="_blank">{strong}</a></td>
                    <td>
                        {render_morph_cell(raw_morph, full_desc, pos_cls_gr)}
                    </td>
                    <td class="definition-cell">{m.get('translit_title', '')}</td>
                </tr>
            '''
        if len(verse_data.get('leftover_latvian', [])) > 0:
            html += f'''
                <tr>
                    <td>
                    <span class="greek-form">- (no match)</span>
                    </td>
                    <td colspan="4">
                        {" ,".join(verse_data.get('leftover_latvian', []))}
                    </td>
                </tr>
            '''
        html += "</tbody></table></div>"

    html += "</body></html>"
    return html

import re

# Map normalized POS labels (the values your POS_MAP / parse_hebrew_morph_code emit)
# to short CSS class suffixes. One source of truth, used by both Greek and Hebrew.
_POS_CLASS = {
    'Verb':        'verb',
    'Noun':        'noun',
    'Adjective':   'adj',
    'Adverb':      'adv',
    'Article':     'art',
    'Preposition': 'prep',
    'Conjunction': 'conj',
    'Interjection': 'interj',
    'Particle':    'particle',
    'Number':      'num',
    # Pronoun family — fold all six Greek variants and the Hebrew "Pronoun" into one class
    'Pronoun':                            'pron',
    'Demonstrative Pronoun':              'pron',
    'Interrogative / Indefinite Pronoun': 'pron',
    'Personal / Possessive Pronoun':      'pron',
    'Reciprocal Pronoun':                 'pron',
    'Relative Pronoun':                   'pron',
    'Reflexive Pronoun':                  'pron',
    # Hebrew-specific
    'Definite Article':       'art',
    'Direct Object Marker':   'particle',
    'Interrogative':          'particle',
    # Foreign words: leave uncolored — they're transliterated, not really inflected
    # 'Hebrew Word', 'Aramaic Word' deliberately omitted
}

def _pos_to_class(label):
    """Convert a POS label like 'Verb' to 'pos-verb'. Empty string if unknown."""
    cls = _POS_CLASS.get(label, '')
    return f'pos-{cls}' if cls else ''


def greek_pos_class(code):
    """Map a Greek morph code (e.g. 'V-PAI-3S', 'DPro-NSM') to a 'pos-xxx' CSS class."""
    if not code:
        return ''
    head = code.strip().split('-', 1)[0]
    label = POS_MAP.get(head, '')
    return _pos_to_class(label)


def hebrew_pos_class(code):
    """Map a Hebrew morph code to a 'pos-xxx' CSS class via the head segment's POS."""
    if not code:
        return ''
    parsed = parse_hebrew_morph_code(code)
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not parsed:
        return ''
    # Walk segments from the end — tail PGN suffixes like '3fs' have empty pos,
    # so we fall back to the previous segment which carries the real head POS.
    for seg in reversed(parsed):
        cls = _pos_to_class(seg.get('pos', ''))
        if cls:
            return cls
    return ''


def render_morph_cell(raw_morph, full_desc, pos_class):
    """Render the morph table cell with optional POS coloring."""
    classes = 'morph-info morph-colored' + (f' {pos_class}' if pos_class else '')
    return f'<span class="{classes}" title="{full_desc}">{raw_morph}</span>'

def render_chapter_html(book, chapter_num, data, out_dir=None):
    if not data:
        return
    if out_dir:
        out_path = Path(out_dir) / str(book) / f"{chapter_num}.html"
    else:
        out_path = BASE_DIR / str(book) / f"{chapter_num}.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(chapter_to_html_render(data))


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build HTML from bible JSON chapters")
    parser.add_argument("--out-dir", default="html",
                        help="Output directory for HTML files (default: html)")
    parser.add_argument("--data-dir", default="html",
                        help="Output directory for HTML files (default: html)")
    args = parser.parse_args()

    print(f"Reading datasets...")
    strongs_df = pd.read_csv(f"{args.data_dir}/strongs.csv")
    lv65_df = pd.read_csv(f"{args.data_dir}/latvian_full65.csv")
    l24_df = pd.read_csv(f"{args.data_dir}/JTR2024_words.csv", dtype={'strong_num': str})
    l1694_df = pd.read_csv(f"{args.data_dir}/GL1694_words.csv")
    strongs_g = strongs_df.groupby(["book", "chapter", "verse"])
    lv_g = lv65_df.groupby(["book", "chapter", "verse"])
    l24_g = l24_df.groupby(["book", "chapter", "verse"])
    l1694_g = l1694_df.groupby(["book", "chapter", "verse"])

    total_start = time.perf_counter()
    total_chapters = 0
    total_verses = 0
    
    import shutil
    from pathlib import Path

    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    

    for book_dir in sorted(BASE_DIR.iterdir()):
        if not book_dir.is_dir():
            continue
        book_name = book_dir.name

        chapter_jsons = sorted(
            (int(f.stem), f) for f in book_dir.iterdir()
            if f.is_file() and f.suffix == '.json' and f.stem.isdigit()
        )
        if not chapter_jsons:
            continue

        book_start = time.perf_counter()
        book_verses = 0

        for ch_num, _ in chapter_jsons:
            data = build_chapter_from_json(book_name, ch_num, strongs_g, lv_g, l24_g, l1694_g)
            if data:
                render_chapter_html(book_name, ch_num, data, out_dir=args.out_dir)
                book_verses += len(data)
                total_chapters += 1

        total_verses += book_verses
        elapsed = time.perf_counter() - book_start
        print(f"  ✅ {book_name}: {len(chapter_jsons)} chapters, {book_verses} verses ({elapsed:.2f}s)")

    total_elapsed = time.perf_counter() - total_start
    print(f"\n{'='*50}")
    print(f"Done: {total_chapters} chapters, {total_verses} verses in {total_elapsed:.1f}s")


if __name__ == "__main__":
    main()
