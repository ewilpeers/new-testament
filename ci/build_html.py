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

# ─── Morphology maps ────────────────────────────────────────────────────────

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
            if(LOG_DATA_WARNINGS):
                printer(f"⚠️ {key} not in l24_df latvian 24!")

        latvian_text_full_original_1694=""
        #???? mapping ????
        if not key in l1694_g.groups:
            if(LOG_DATA_WARNINGS or True):
                printer(f"⚠️ {key} not in 1694 GLUCK!")
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
        .line-box { flex: 1 1 45%; min-width: 300px; }
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
    </style>
    """

    book_title = data[0].get('book', 'Bible').capitalize()
    chapter = data[0].get('chapter', '')
    html = f"<!DOCTYPE html><html><head><meta charset='UTF-8'>{css}</head><body>"
    html += f"<h1>📖 {book_title} Chapter {chapter}</h1>"

    for verse_data in data:
        v_num = verse_data.get('verse')
        locus = f"{book_title} {chapter}:{v_num}"

        html += f'<div class="verse-container">'
        html += f'<div class="verse-header"><span class="index-badge">{v_num}</span> {locus}</div>'

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
                <div class="line-content frankfurt-line">{verse_data.get('latvian_text_full_original_1694', '')}</div>
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
            audio_html = make_audio_players(m.get('strong_num'), v_num, m_idx)

            html += f'''
                <tr>
                    <td class="greek-word">
                        {m.get('form', '')} <span class="greek-form">({m.get('translit', '')})</span>
                        {audio_html}
                    </td>
                    <td class="latvian-word">{lv_words}</td>
                    <td><a href="https://www.blueletterbible.org/lexicon/{strong.lower()}/" target="_blank">{strong}</a></td>
                    <td>
                        <span class="morph-info" title="{full_desc}">{raw_morph}</span>
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
    l1694_df = pd.read_csv(f"{args.data_dir}/GL1694_words.csv')
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
