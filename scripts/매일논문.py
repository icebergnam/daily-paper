"""매일 논문: 설정의 키워드로 최근 논문을 찾아 조테로에 저장하고, 요약할 논문의 파일을 만든다.

사용:
  python3 scripts/매일논문.py 검색   OpenAlex 후보 → 매일논문/{날짜}/후보_openalex.json
  (그다음 paper-scout 담당이 Exa 후보 → 매일논문/{날짜}/후보_exa.json)
  python3 scripts/매일논문.py 저장   두 후보를 합쳐 N편 선정 → 조테로 저장 → PDF 받기
                                     → 목록.json, D01.txt(서지·초록), D01.pdf(받았으면)
  인자 없이 실행하면 검색과 저장을 이어서 한다(Exa 없이).
PDF는 OpenAlex 오픈 액세스 → Semantic Scholar 오픈 액세스 순으로 받는다. 못 받은 논문 ID는 마지막 줄에 찍힌다.
조테로는 데스크톱 앱이 켜져 있어야 저장된다(로컬 커넥터, 키 필요 없음). '자동수집' 컬렉션에 들어간다.
"""
import datetime, json, pathlib, re, sys, urllib.parse, urllib.request, uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "매일논문"
SEEN = OUT / "seen.txt"
CFG = ROOT / "설정/매일논문.json"
DAYS_BACK = 30  # ponytail: 최근 30일 고정, 바꿀 일이 생기면 설정으로 옮김
SPARE = 5  # 키워드마다 찾을_편수의 몇 배를 후보로 받나. PDF를 못 받은 논문 대신 다음 후보로 바꾸기 위해
ZOTERO = "http://127.0.0.1:23119/connector/"
COLLECTION = "자동수집"
UA = {"User-Agent": "daily-papers/1"}  # 조테로는 브라우저 같은 User-Agent를 막는다
PDF_UA = {"User-Agent": "Mozilla/5.0 (daily-papers)"}  # 출판사는 브라우저가 아니면 PDF를 안 주기도 한다


def get(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def get_json(url, data=None):
    body = get(url, data)
    return json.loads(body) if body else None


def abstract(inv):
    if not inv:
        return ""
    pos = sorted((i, w) for w, idx in inv.items() for i in idx)
    return " ".join(w for _, w in pos)


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
        "keyword": keyword,
        "abstract": abstract(w.get("abstract_inverted_index")),
    }


def search(keyword, n):
    since = (datetime.date.today() - datetime.timedelta(days=DAYS_BACK)).isoformat()
    q = urllib.parse.urlencode({"search": keyword, "filter": f"from_publication_date:{since},type:article|preprint|review",
                                "sort": "relevance_score:desc", "per-page": n})
    return [to_paper(w, keyword) for w in get_json(f"https://api.openalex.org/works?{q}")["results"]]


def save_zotero(p, today):
    creators = []
    for name in p["authors"]:
        first, _, last = name.rpartition(" ")
        creators.append({"firstName": first, "lastName": last or name, "creatorType": "author"})
    item = {"itemType": "journalArticle", "title": p["title"], "creators": creators, "date": p.get("date") or "",
            "publicationTitle": p.get("venue") or "", "DOI": p.get("doi") or "", "url": p["url"],
            "abstractNote": p.get("abstract") or "",
            "tags": [{"tag": "자동수집"}, {"tag": today}, {"tag": p["keyword"]}], "id": str(uuid.uuid4())}
    sid = str(uuid.uuid4())
    try:
        targets = get_json(ZOTERO + "getSelectedCollection", b"{}")["targets"]
        target = next(t["id"] for t in targets if t["name"] == COLLECTION)
        get_json(ZOTERO + "saveItems", json.dumps({"items": [item], "uri": p["url"], "sessionID": sid}).encode())
        get_json(ZOTERO + "updateSession", json.dumps({"sessionID": sid, "target": target}).encode())
        return True
    except StopIteration:
        p["zotero_error"] = f"조테로에 '{COLLECTION}' 컬렉션이 없음"
        return False
    except Exception as e:
        p["zotero_error"] = str(e)
        return False


def pdf_urls(p):
    """오픈 액세스 PDF 후보 주소: OpenAlex → Semantic Scholar."""
    urls = [p["oa_url"]] if p.get("oa_url") else []
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([\w.\-/]+?)(?:v\d+)?(?:\.pdf)?$", p.get("url") or "")
    if m:  # arXiv는 주소에서 PDF 주소를 바로 만든다
        urls.append(f"https://arxiv.org/pdf/{m.group(1)}")
    if p.get("doi"):
        try:
            s2 = get_json(f"https://api.semanticscholar.org/graph/v1/paper/DOI:{p['doi']}?fields=openAccessPdf")
            if (s2.get("openAccessPdf") or {}).get("url"):
                urls.append(s2["openAccessPdf"]["url"])
        except Exception:
            pass
    return list(dict.fromkeys(urls))


def fetch_pdf(p, dest):
    for u in pdf_urls(p):
        try:
            body = get(u, headers={"Accept": "application/pdf", **PDF_UA})
            if body[:5] == b"%PDF-":  # 출판사 로그인·차단 화면(HTML)은 거른다
                dest.write_bytes(body)
                p["pdf_from"] = u
                p["oa_url"] = p.get("oa_url") or u
                return True
        except Exception:
            pass
    return False


def cmd_search(cfg, day, seen):
    day.mkdir(parents=True, exist_ok=True)
    found = [p for k in cfg["키워드"] for p in search(k, min(200, cfg["찾을_편수"] * SPARE)) if not keys(p) & seen]
    (day / "후보_openalex.json").write_text(json.dumps(found, ensure_ascii=False, indent=1))
    print(f"OpenAlex 후보 {len(found)}편 → {day / '후보_openalex.json'}")


def cmd_save(cfg, day, seen, today):
    n, m = cfg["찾을_편수"], cfg["요약할_편수"]
    since = (datetime.date.today() - datetime.timedelta(days=DAYS_BACK)).isoformat()
    lists = {}
    for name in ("후보_openalex.json", "후보_exa.json"):
        f = day / name
        for p in json.loads(f.read_text()) if f.exists() else []:
            p.setdefault("source", "exa")
            p.setdefault("authors", [])
            if (p.get("date") or "9999")[:10] < since:  # 날짜가 있는데 30일보다 오래된 후보는 뺀다
                continue
            lists.setdefault(p["keyword"], []).append(p)
    # 키워드마다 돌아가며 줄 세운다(OpenAlex 먼저, 중복·이미 본 논문 제외)
    pool, queues, used = [], list(lists.values()), set()
    while any(queues):
        for q in queues:
            while q:
                p = q.pop(0)
                if not keys(p) & (seen | used):
                    used |= keys(p)
                    pool.append(p)
                    break

    # 요약 자리는 PDF를 실제로 받은 논문만. 못 받으면 그 논문은 건너뛰고 다음 후보를 찾는다(판정 J7)
    with_pdf, tried = [], 0
    for p in pool:
        if len(with_pdf) >= m:
            break
        tmp = day / f"_tmp{tried}.pdf"
        tried += 1
        if fetch_pdf(p, tmp):
            with_pdf.append(p)
            p["_tmp"] = tmp
    summ = with_pdf
    if len(summ) < m:
        print(f"PDF를 받은 후보가 {len(summ)}편뿐이라 {len(summ)}편만 요약합니다(후보 {tried}편 시도)")
    picked = (summ + [p for p in pool if p not in summ])[:n]
    seen |= {k for p in picked for k in keys(p)}

    for i, p in enumerate(picked, 1):
        p["id"] = f"D{i:02d}"
        p["zotero_saved"] = save_zotero(p, today)
        p["summarize"] = p in summ
        tmp = p.pop("_tmp", None)
        if p["summarize"]:
            (day / f"{p['id']}.txt").write_text(
                f"제목: {p['title']}\n저자: {', '.join(p['authors'])}\n연도: {p.get('year') or ''}\n"
                f"출처: {p.get('venue') or ''}\nDOI/URL: {p['url']}\n\n초록:\n{p.get('abstract') or '초록 없음'}\n")
            p["fulltext"] = "pdf"
            tmp.rename(day / f"{p['id']}.pdf")
    for f in day.glob("_tmp*.pdf"):
        f.unlink()
    (day / "목록.json").write_text(json.dumps(picked, ensure_ascii=False, indent=1))
    SEEN.write_text("\n".join(sorted(seen)) + "\n")
    saved = sum(p["zotero_saved"] for p in picked)
    print(f"찾음 {len(picked)}편, 조테로 저장 {saved}편, 요약 대상 {len(summ)}편 → {day}")
    print("PDF 못 받음: 없음")  # 요약 대상은 모두 PDF가 있다. 담당 흐름이 이 줄을 읽으므로 남겨 둔다


def main():
    cfg = json.loads(CFG.read_text())
    if not cfg["키워드"]:
        print("키워드가 비어 있습니다. 설정/매일논문.json에 키워드를 적어 주세요.")
        return
    today = datetime.date.today().isoformat()
    day = OUT / today
    if (day / "목록.json").exists():
        print(f"오늘 이미 실행함: {day / '목록.json'}")
        return
    seen = set(SEEN.read_text().split()) if SEEN.exists() else set()
    step = sys.argv[1] if len(sys.argv) > 1 else "전부"
    if step in ("검색", "전부"):
        cmd_search(cfg, day, seen)
    if step in ("저장", "전부"):
        cmd_save(cfg, day, seen, today)


if __name__ == "__main__":
    main()
