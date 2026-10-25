"""매일 논문: 후보를 합쳐 그날 논문을 고르고 PDF를 받아, 요약할 논문의 파일을 만든다. 조테로 저장은 zotero-keeper 스킬이 한다.

사용(스킬 daily-paper의 4단계. 그 앞에서 paper-scout가 후보_openalex.json·후보_exa.json·제외.json을 쓴다):
  python3 scripts/매일논문.py 저장   두 후보를 합쳐 N편 선정(paper-scout가 거른 제외.json은 빼고) → PDF 받기
                                     → 목록.json, D01.txt(서지·초록), D01.pdf(받았으면)
  python3 scripts/매일논문.py 시험준비   paper-reader 시험용 한 편(대시보드가 부른다)
하루에 여러 번 받을 수 있다. 오늘 목록.json이 있으면 뒤에 이어 붙이고 ID도 이어서 매긴다(D03, D04…).
  기본(자동): 오늘 받은 편수가 설정 '찾을_편수'에 닿았으면 "오늘 이미 실행함"으로 건너뛰고, 모자라면 모자란 만큼만 받는다.
  '추가'를 붙이면(저장 추가) 언제든 설정 편수만큼 더 받는다.
새로 받은 ID는 "새 논문: D03 D04" 줄에 찍힌다. 이어 붙이면 노션완료.txt·판정상태.json을 지워 그날을 다시 열어 둔다.
PDF는 OpenAlex 오픈 액세스 → Semantic Scholar 오픈 액세스 순으로 받는다. 못 받은 논문 ID는 마지막 줄에 찍힌다.
조테로 저장은 이어서 zotero-keeper가 한다(zotero_saved는 처음엔 false, workspace/설정/zotero-keeper.json "사용"이 false면 이유가 "사용 안 함").
"""
import datetime, importlib.util, json, pathlib, re, sys, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "workspace/매일논문"  # 내 결과는 작업공간에만(git에 안 올라감)
SEEN = OUT / "seen.txt"
CFG = ROOT / "workspace/설정/매일논문.json"
# OpenAlex 검색과 중복 판단은 paper-scout 스킬의 것을 쓴다(키워드·기간은 workspace/설정/paper-scout.json)
_spec = importlib.util.spec_from_file_location("openalex", ROOT / ".claude/skills/paper-scout/scripts/openalex.py")
scout = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scout)
keys = scout.keys
UA = {"User-Agent": "daily-papers/1"}
PDF_UA = {"User-Agent": "Mozilla/5.0 (daily-papers)"}  # 출판사는 브라우저가 아니면 PDF를 안 주기도 한다


def get(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def get_json(url, data=None):
    body = get(url, data)
    return json.loads(body) if body else None


def pdf_urls(p):
    """오픈 액세스 PDF 후보 주소: OpenAlex → Semantic Scholar."""
    urls = [u for u in (p.get("pdf_url"), p.get("oa_url")) if u]  # paper-scout가 찾은 PDF 주소가 먼저
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


def write_bib(day, p):
    """paper-reader가 읽는 서지·초록 파일 {ID}.txt."""
    (day / f"{p['id']}.txt").write_text(
        f"제목: {p['title']}\n저자: {', '.join(p['authors'])}\n연도: {p.get('year') or ''}\n"
        f"출처: {p.get('venue') or ''}\nDOI/URL: {p['url']}\n\n초록:\n{p.get('abstract') or '초록 없음'}\n")


def cmd_test_prep():
    """paper-reader 시험 준비: paper-scout 시험 후보(거른 것 빼고) 중 PDF를 받은 첫 편을 workspace/매일논문/시험/paper-reader/D01로 둔다.
    PDF를 받은 후보가 없으면 첫 후보의 초록만 둔다(그러면 판정 J7이 실패로 알린다). 그날 논문·seen.txt는 건드리지 않는다."""
    src, out = OUT / "시험/paper-scout", OUT / "시험/paper-reader"
    drop = {x.get("openalex") for x in json.loads((src / "제외.json").read_text())} - {None, ""} if (src / "제외.json").exists() else set()
    pool = [p for f in ("후보_openalex.json", "후보_exa.json") if (src / f).exists()
            for p in json.loads((src / f).read_text()) if p.get("openalex") not in drop or not p.get("openalex")]
    if not pool:
        sys.exit("paper-scout 시험 후보가 없습니다. 논문 찾기 단계의 시험을 먼저 하세요")
    out.mkdir(parents=True, exist_ok=True)
    p = next((p for p in pool[:8] if fetch_pdf(p, out / "D01.pdf")), pool[0])  # ponytail: 앞 8편만 시도
    p.setdefault("authors", [])
    p |= {"id": "D01", "summarize": True, "fulltext": "pdf" if (out / "D01.pdf").exists() else "abstract"}
    write_bib(out, p)
    (out / "목록.json").write_text(json.dumps([p], ensure_ascii=False, indent=1))
    print(f"시험 논문: {p['title']} ({'PDF 받음' if (out / 'D01.pdf').exists() else 'PDF 못 받음, 초록만'})")


def cmd_save(day, seen, n, m, old):
    since = (datetime.date.today() - datetime.timedelta(days=scout.cfg().get("기간_일", 30))).isoformat()
    lists = {}
    # paper-scout가 키워드 분야와 관계없다고 거른 OpenAlex 후보(Exa는 남은 것만 후보 파일에 쓴다)
    drop = {x.get("openalex") for x in (json.loads((day / "제외.json").read_text()) if (day / "제외.json").exists() else [])} - {None, ""}
    for name in ("후보_openalex.json", "후보_exa.json"):
        f = day / name
        for p in json.loads(f.read_text()) if f.exists() else []:
            if p.get("openalex") in drop:
                continue
            p.setdefault("source", "exa")
            p.setdefault("authors", [])
            if (p.get("date") or "9999")[:10] < since:  # 날짜가 있는데 30일보다 오래된 후보는 뺀다
                continue
            lists.setdefault(p["keyword"], []).append(p)
    for q in lists.values():  # 키워드 안에서는 PDF 주소가 있는 후보를 앞으로(나머지 순서는 그대로)
        q.sort(key=lambda p: not (p.get("pdf_url") or p.get("oa_url")))
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

    # 찾을 편수를 모두 PDF를 실제로 받은 논문으로 채운다. 못 받으면 그 논문은 건너뛰고 다음 후보로(판정 J7)
    # 요약은 그중 앞의 m편. PDF 받은 논문이 n편보다 적을 때만 PDF 없는 후보로 나머지를 채운다
    with_pdf, tried = [], 0
    for p in pool:
        if len(with_pdf) >= n:
            break
        tmp = day / f"_tmp{tried}.pdf"
        tried += 1
        if fetch_pdf(p, tmp):
            with_pdf.append(p)
            p["_tmp"] = tmp
    if len(with_pdf) < n:
        print(f"PDF를 받은 후보가 {len(with_pdf)}편뿐입니다(후보 {tried}편 시도). 나머지는 PDF 없는 후보로 채웁니다")
    summ = with_pdf[:m]
    picked = (with_pdf + [p for p in pool if p not in with_pdf])[:n]
    seen |= {k for p in picked for k in keys(p)}

    if not picked:
        for f in day.glob("_tmp*.pdf"):
            f.unlink()
        print("새 논문이 없습니다(오늘 후보를 다 봤습니다)")
        return
    batch = max((p.get("batch", 1) for p in old), default=0) + 1
    zf = ROOT / "workspace/설정/zotero-keeper.json"
    zotero_on = json.loads(zf.read_text()).get("사용", True) if zf.exists() else True
    for i, p in enumerate(picked, len(old) + 1):
        p["id"] = f"D{i:02d}"
        p["batch"] = batch
        p["zotero_saved"], p["zotero_error"] = False, "아직 저장 안 함" if zotero_on else "사용 안 함"
        p["summarize"] = p in summ
        tmp = p.pop("_tmp", None)
        if tmp:  # 요약하지 않는 논문도 받은 PDF는 남긴다
            tmp.rename(day / f"{p['id']}.pdf")
        if p["summarize"]:
            write_bib(day, p)
            p["fulltext"] = "pdf"
    for f in day.glob("_tmp*.pdf"):
        f.unlink()
    (day / "목록.json").write_text(json.dumps(old + picked, ensure_ascii=False, indent=1))
    SEEN.write_text("\n".join(sorted(seen)) + "\n")
    if old:  # 새 논문이 붙었으니 그날을 다시 연다: 노션에 새 줄을 올리고 판정 루프를 처음부터
        for f in ("노션완료.txt", "판정상태.json"):
            (day / f).unlink(missing_ok=True)
    print(f"찾음 {len(picked)}편, 요약 대상 {len(summ)}편 → {day}" + (f" (오늘 모두 {len(old) + len(picked)}편)" if old else ""))
    print("새 논문: " + " ".join(p["id"] for p in picked))
    print("PDF 못 받음: " + (" ".join(p["id"] for p in picked if not (day / f"{p['id']}.pdf").exists()) or "없음"))


def main():
    if not (ROOT / "workspace/설정").is_dir():  # 개인 설정·결과는 작업공간에만 둔다
        sys.exit("작업공간(workspace/)이 없습니다. 대시보드 → 기본 점검에서 '작업공간 만들기'를 누르세요.")
    cfg = json.loads(CFG.read_text())
    if not scout.cfg()["키워드"]:
        print("키워드가 비어 있습니다. workspace/설정/paper-scout.json에 키워드를 적어 주세요.")
        return
    today = datetime.date.today().isoformat()
    day = OUT / today
    old = json.loads((day / "목록.json").read_text()) if (day / "목록.json").exists() else []
    rf = ROOT / "workspace/설정/paper-reader.json"  # 요약은 paper-reader(선택) 설정: 사용 안 함이면 요약 0편(PDF는 그대로 받는다)
    r = json.loads(rf.read_text()) if rf.exists() else {"사용": True, "요약할_편수": 2}
    n, m = cfg["찾을_편수"], r["요약할_편수"] if r.get("사용", True) else 0
    if "추가" not in sys.argv[1:]:  # 자동: 설정 편수를 채웠으면 건너뛰고, 모자라면 그만큼만
        n, m = n - len(old), m - sum(bool(p.get("summarize")) for p in old)
        if n <= 0:
            print(f"오늘 이미 실행함: {len(old)}편(설정 {cfg['찾을_편수']}편) → {day / '목록.json'}")
            return
    m = max(0, min(m, n))
    seen = set(SEEN.read_text().split()) if SEEN.exists() else set()
    day.mkdir(parents=True, exist_ok=True)
    cmd_save(day, seen, n, m, old)


if __name__ == "__main__":
    if sys.argv[1:] == ["시험준비"]:
        cmd_test_prep()
    elif sys.argv[1:2] == ["저장"]:
        main()
    else:
        sys.exit(__doc__)
