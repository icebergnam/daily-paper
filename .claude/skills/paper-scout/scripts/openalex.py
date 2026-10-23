"""paper-scout: 설정/paper-scout.json의 키워드로 OpenAlex에서 최근 논문 후보를 찾는다. 키 필요 없음.

사용: python3 .claude/skills/paper-scout/scripts/openalex.py {출력 폴더} [쪽]
  → {출력 폴더}/후보_openalex.json. 오픈 액세스 논문만, 키워드마다 '키워드당_후보'편씩 한 쪽을 받는다.
  쪽(기본 1)이 2 이상이면 그 쪽을 받아 기존 파일 뒤에 붙인다(PDF 있는 후보가 모자랄 때 다음 쪽을 더 본다).
  이미 본 논문(매일논문/seen.txt)과 이미 파일에 있는 논문은 뺀다. 끝에 키워드별 편수(PDF 주소 있는 편수)와 이번 쪽 위쪽 제목 5개를 찍는다.
OpenAlex 초록은 낱말 위치 사전(abstract_inverted_index)으로 오므로 여기서 문장으로 되돌린다(이 스크립트가 있는 이유).
"""
import datetime, json, pathlib, re, sys, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[4]
CFG = ROOT / "설정/paper-scout.json"
SEEN = ROOT / "매일논문/seen.txt"


def cfg():
    return json.loads(CFG.read_text())


def abstract(inv):
    if not inv:
        return ""
    return " ".join(w for _, w in sorted((i, w) for w, idx in inv.items() for i in idx))


def norm_title(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())[:120]


def keys(p):
    """중복 판단에 쓰는 열쇠들: OpenAlex ID, DOI, 정리한 제목."""
    return {k for k in (p.get("openalex"), (p.get("doi") or "").lower(), "t:" + norm_title(p["title"])) if k and k != "t:"}


def to_paper(w, keyword):
    loc = w.get("primary_location") or {}
    return {
        "source": "openalex",
        "openalex": w["id"].rsplit("/", 1)[-1],
        "title": w.get("title") or "",
        "authors": [a["author"]["display_name"] for a in w.get("authorships", [])],
        "year": w.get("publication_year"),
        "date": w.get("publication_date"),
        "venue": (loc.get("source") or {}).get("display_name") or "",
        "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
        "url": w.get("doi") or loc.get("landing_page_url") or w["id"],
        "oa_url": (w.get("open_access") or {}).get("oa_url"),
        "pdf_url": (w.get("best_oa_location") or {}).get("pdf_url") or loc.get("pdf_url"),  # 바로 받을 수 있는 PDF 주소(없으면 None)
        "keyword": keyword,
        "abstract": abstract(w.get("abstract_inverted_index")),
    }


def search(keyword, n, days=None, page=1, oa=False):
    since = (datetime.date.today() - datetime.timedelta(days=days or cfg().get("기간_일", 30))).isoformat()
    q = urllib.parse.urlencode({"search": keyword, "filter": f"from_publication_date:{since},type:article|preprint|review" + (",is_oa:true" if oa else ""),
                                "sort": "relevance_score:desc", "per-page": n, "page": page})
    req = urllib.request.Request(f"https://api.openalex.org/works?{q}", headers={"User-Agent": "daily-papers/1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return [to_paper(w, keyword) for w in json.loads(r.read())["results"]]


def main(out, page=1):
    c = cfg()
    if not c.get("키워드"):
        sys.exit("키워드가 비어 있습니다: 설정/paper-scout.json")
    f = out / "후보_openalex.json"
    old = json.loads(f.read_text()) if page > 1 and f.exists() else []
    skip = (set(SEEN.read_text().split()) if SEEN.exists() else set()) | {k for p in old for k in keys(p)}
    new = []
    for k in c["키워드"]:
        for p in search(k, min(200, c.get("키워드당_후보", 10)), page=page, oa=True):
            if not keys(p) & skip:
                skip |= keys(p)
                new.append(p)
    out.mkdir(parents=True, exist_ok=True)
    found = old + new
    f.write_text(json.dumps(found, ensure_ascii=False, indent=1))
    print(f"OpenAlex {page}쪽: 새 후보 {len(new)}편(PDF 주소 있음 {sum(bool(p['pdf_url']) for p in new)}편), 모두 {len(found)}편 → {f}")
    for k in c["키워드"]:
        print(f"  {k}: {sum(p['keyword'] == k for p in found)}편(PDF 주소 있음 {sum(p['keyword'] == k and bool(p['pdf_url']) for p in found)}편)")
    for p in new[:5]:
        print(f"  - {p['title']} ({p.get('date') or p.get('year') or ''}){'' if p['pdf_url'] else ' · PDF 주소 없음'}")


if __name__ == "__main__":
    if sys.argv[1:] == ["자체시험"]:
        assert abstract({"world": [1], "hello": [0]}) == "hello world" and abstract(None) == ""
        assert keys({"title": "A b!", "doi": "10.1/X"}) == {"10.1/x", "t:ab"}
        print("자체시험 통과")
    elif len(sys.argv) in (2, 3) and (len(sys.argv) == 2 or sys.argv[2].isdigit()):
        main(pathlib.Path(sys.argv[1]) if pathlib.Path(sys.argv[1]).is_absolute() else ROOT / sys.argv[1], int(sys.argv[2]) if len(sys.argv) == 3 else 1)
    else:
        sys.exit(__doc__)
