"""zotero-keeper: 이 컴퓨터의 조테로 7 데스크톱 앱(로컬 커넥터, 키 필요 없음)에 논문을 저장한다.

사용: python3 .claude/skills/zotero-keeper/scripts/zotero.py 점검
        앱이 켜졌는지, 설정의 컬렉션이 있는지
      python3 .claude/skills/zotero-keeper/scripts/zotero.py 저장 {날짜 폴더} [ID ...]
        {날짜 폴더}/목록.json에서 아직 저장 안 된 논문(ID를 주면 그것만)을 저장하고 zotero_saved·zotero_error를 고쳐 쓴다
      python3 .claude/skills/zotero-keeper/scripts/zotero.py 시험
        paper-scout 시험 후보(거른 것 빼고) 첫 편을 '시험' 태그를 붙여 저장 → workspace/매일논문/시험/zotero-keeper/시험저장.json
설정: workspace/설정/zotero-keeper.json("사용", "컬렉션"). 논문 글(제목·초록)을 셸 명령에 넣지 않으려고 저장은 이 스크립트가 한다.
"""
import datetime, json, pathlib, sys, urllib.request, uuid

ROOT = pathlib.Path(__file__).resolve().parents[4]
CFG = ROOT / "workspace/설정/zotero-keeper.json"
ZOTERO = "http://127.0.0.1:23119/connector/"
UA = {"User-Agent": "daily-papers/1"}  # 조테로는 브라우저 같은 User-Agent를 막는다


def cfg():
    return json.loads(CFG.read_text()) if CFG.exists() else {"사용": True, "컬렉션": "자동수집"}


def call(path, body=None):
    req = urllib.request.Request(ZOTERO + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read()
    try:
        return json.loads(data) if data else None
    except ValueError:  # ping은 글자("Zotero is running")로 답한다
        return data.decode()


def target():
    """설정 컬렉션의 id. 앱이 꺼졌으면 예외, 컬렉션이 없으면 None."""
    name = cfg()["컬렉션"]
    return next((t["id"] for t in call("getSelectedCollection", {})["targets"] if t["name"] == name), None)


def item(p, tags):
    creators = []
    for name in p.get("authors") or []:
        first, _, last = name.rpartition(" ")
        creators.append({"firstName": first, "lastName": last or name, "creatorType": "author"})
    return {"itemType": "journalArticle", "title": p["title"], "creators": creators, "date": p.get("date") or "",
            "publicationTitle": p.get("venue") or "", "DOI": p.get("doi") or "", "url": p["url"],
            "abstractNote": p.get("abstract") or "", "tags": [{"tag": t} for t in tags if t], "id": str(uuid.uuid4())}


def save(p, tags):
    """논문 한 편을 저장한다. (성공 여부, 실패 이유)."""
    try:
        t = target()
        if not t:
            return False, f"조테로에 '{cfg()['컬렉션']}' 컬렉션이 없음"
        sid = str(uuid.uuid4())
        call("saveItems", {"items": [item(p, tags)], "uri": p["url"], "sessionID": sid})
        call("updateSession", {"sessionID": sid, "target": t})
        return True, ""
    except Exception as e:
        return False, f"조테로 앱에 연결 못 함({e})"


def cmd_check():
    try:
        call("ping")
    except Exception as e:
        print(f"❌ 조테로 앱 꺼짐({e}) → 조테로 7을 켜고, 설정 → 고급 → '다른 앱과 통신 허용'을 켜세요")
        return 1
    print("✅ 조테로 앱 켜짐")
    if target() is None:
        print(f"❌ '{cfg()['컬렉션']}' 컬렉션 없음 → 조테로 왼쪽 '내 라이브러리' 오른쪽 클릭 → 새 컬렉션 → 이름 '{cfg()['컬렉션']}'")
        return 1
    print(f"✅ '{cfg()['컬렉션']}' 컬렉션 있음")
    return 0


def cmd_save(day, ids):
    if not cfg().get("사용", True):
        print("조테로 사용 안 함(workspace/설정/zotero-keeper.json): 저장하지 않습니다")
        return 0
    f = day / "목록.json"
    papers = json.loads(f.read_text())
    todo = [p for p in papers if (p["id"] in ids if ids else not p.get("zotero_saved"))]
    for p in todo:
        p["zotero_saved"], p["zotero_error"] = save(p, [cfg()["컬렉션"], day.name, p.get("keyword")])
        print(f"{p['id']} | " + ("조테로 저장됨" if p["zotero_saved"] else f"미저장({p['zotero_error']})"))
    f.write_text(json.dumps(papers, ensure_ascii=False, indent=1))
    print(f"조테로 저장 {sum(p['zotero_saved'] for p in todo)}/{len(todo)}편")
    return 0 if all(p["zotero_saved"] for p in todo) else 1


def cmd_test():
    src, out = ROOT / "workspace/매일논문/시험/paper-scout", ROOT / "workspace/매일논문/시험/zotero-keeper"
    drop = {x.get("openalex") for x in json.loads((src / "제외.json").read_text())} if (src / "제외.json").exists() else set()
    pool = [p for n in ("후보_openalex.json", "후보_exa.json") if (src / n).exists()
            for p in json.loads((src / n).read_text()) if not (p.get("openalex") and p.get("openalex") in drop)]
    out.mkdir(parents=True, exist_ok=True)
    r = {"시각": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "컬렉션": cfg()["컬렉션"]}
    if not pool:
        r |= {"저장": False, "이유": "paper-scout 시험 후보가 없습니다. 논문 찾기 단계의 시험을 먼저 하세요"}
    else:
        p = pool[0]
        ok, err = save(p, [cfg()["컬렉션"], "시험", p.get("keyword")])
        r |= {"저장": ok, "이유": err, "제목": p["title"], "url": p["url"]}
    (out / "시험저장.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))
    print(json.dumps(r, ensure_ascii=False))
    return 0 if r["저장"] else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["자체시험"]:
        it = item({"title": "T", "authors": ["Ada Lovelace", "Plato"], "url": "u"}, ["x", None, "y"])
        assert it["creators"][0] == {"firstName": "Ada", "lastName": "Lovelace", "creatorType": "author"}
        assert it["creators"][1]["lastName"] == "Plato" and [t["tag"] for t in it["tags"]] == ["x", "y"]
        print("자체시험 통과")
    elif a == ["점검"]:
        sys.exit(cmd_check())
    elif a[:1] == ["저장"] and len(a) >= 2:
        d = pathlib.Path(a[1])
        sys.exit(cmd_save(d if d.is_absolute() else ROOT / d, a[2:]))
    elif a == ["시험"]:
        sys.exit(cmd_test())
    else:
        sys.exit(__doc__)
