"""매일 논문 판정: 그날 요약(D*.md)과 다이제스트가 '끝났다'의 기준을 지켰는지 코드로 판정한다.

사용: python3 scripts/매일논문_판정.py [날짜]   (날짜를 빼면 가장 최근 날짜 폴더)
      python3 scripts/매일논문_판정.py 요약 {폴더}   요약 기준(J1~J5, J7)만. paper-reader 시험에서 쓴다
출력 약속(루프 훅이 이대로 읽음, 바꾸지 않음):
  실패 하나마다 한 줄 `FAIL <기준> <ID>: <이유>`, 마지막 줄 `판정 결과: 실패 N개`
  종료 코드: 실패 없으면 0, 있으면 1, 읽을 수 없으면 2
기준:
  J1 요약 대상마다 D*.md가 있다
  J2 ※ 줄이 실제로 읽은 원문과 맞다(PDF가 있으면 PDF 기준, 본문이 있으면 웹 본문 기준, 아니면 초록 기준)
  J3 연구 질문·방법·결과·저자가 밝힌 한계 항목이 모두 있다
  J4 각 항목에 근거 표시가 있다(초록 "(초록)", PDF "§"·"p.", 웹 본문 괄호) 또는 "확인 안 됨"
  J5 초록·웹 본문 기준 요약의 숫자가 모두 그 원문에 있다(지어낸 숫자 막기)
  J7 요약 대상은 PDF를 받은 논문이다(못 받았으면 다른 논문으로 바꿔야 함)
  J6 다이제스트: ※ 경고 줄, 찾음·조테로 저장·요약 편수가 목록.json과 같음, 논문 제목이 모두 있음, 미저장이면 "조테로 미저장"
ponytail: PDF 기준 요약의 숫자는 대조하지 않는다(PDF 글자 추출에 패키지가 필요). 필요해지면 pdftotext로 J5를 넓힌다.
"""
import json, pathlib, re, sys

OUT = pathlib.Path(__file__).resolve().parent.parent / "매일논문"
ITEMS = ["연구 질문", "방법", "결과", "저자가 밝힌 한계"]
NUM = re.compile(r"\d+(?:[.,]\d+)*")


def blocks(md):
    """'- 항목:'부터 다음 맨 앞 '- ' 줄 전까지를 항목 하나로 묶는다(여러 줄 항목 포함)."""
    out, key = {}, None
    for line in md.splitlines():
        m = re.match(r"- ([^:：]+)[:：]", line)
        if m:
            key = m.group(1).strip()
            out[key] = line
        elif key and line.startswith((" ", "\t")):
            out[key] += "\n" + line
    return out


WORDS = "zero one two three four five six seven eight nine ten eleven twelve".split()


def nums(text):
    """글 속 숫자. 원문이 영어 낱말로 쓴 숫자(one-year, Two-wave)도 센다."""
    found = {n.replace(",", "") for n in NUM.findall(text)}
    return found | {str(i) for i, w in enumerate(WORDS) if re.search(rf"\b{w}\b", text, re.I)}


def judge_summaries(day, papers):
    fails = []
    for p in (p for p in papers if p.get("summarize")):
        i = p["id"]
        if not ((day / f"{i}.pdf").exists() or (day / f"{i}_원문.pdf").exists()):
            fails.append(f"J7 {i}: PDF 없이 요약 대상이 됨 — `python3 scripts/매일논문.py 저장`이 PDF 있는 다른 논문으로 골라야 함")
        md_path = day / f"{i}.md"
        if not md_path.exists():
            fails.append(f"J1 {i}: {i}.md가 없음")
            continue
        md = md_path.read_text()
        if (day / f"{i}.pdf").exists():
            basis, src = "원문 PDF 기준", None
        elif (day / f"{i}_본문.md").exists():
            basis, src = "웹 본문 기준", (day / f"{i}_본문.md").read_text()
        else:
            basis, src = "초록 기준", (day / f"{i}.txt").read_text() if (day / f"{i}.txt").exists() else p.get("abstract", "")
        mark = next((l for l in md.splitlines() if l.startswith("※")), "")
        if basis not in mark:
            fails.append(f"J2 {i}: ※ 줄이 '{basis}'여야 함 (지금: {mark or '없음'})")
        b = blocks(md)
        for item in ITEMS:
            text = b.get(item)
            if text is None:
                fails.append(f"J3 {i}: '{item}' 항목이 없음")
                continue
            ok = {"초록 기준": "(초록)" in text, "원문 PDF 기준": "§" in text or "p." in text,
                  "웹 본문 기준": re.search(r"\([^)]+\)", text) is not None}[basis]
            if not ok and "확인 안 됨" not in text:
                fails.append(f"J4 {i}: '{item}'에 근거 표시가 없음")
            if src is not None:
                missing = sorted(nums(text) - nums(src))
                if missing:
                    fails.append(f"J5 {i}: '{item}'의 숫자 {', '.join(missing)}가 원문에 없음")
    return fails


def judge(day):
    papers = json.loads((day / "목록.json").read_text())
    fails = judge_summaries(day, papers)
    dg_path = day / "다이제스트.md"
    if not dg_path.exists():
        return fails + ["J6 다이제스트: 다이제스트.md가 없음"]
    dg = dg_path.read_text()
    if not re.search(r"^※ .*근거로 쓰지 않습니다", dg, re.M):
        fails.append("J6 다이제스트: 맨 위 ※ 경고 줄이 없음")
    n, z, s = len(papers), sum(bool(p.get("zotero_saved")) for p in papers), sum(bool(p.get("summarize")) for p in papers)
    for label, pat, v in (("찾음", "찾(?:음|은 편수)", n), ("조테로 저장", "조테로 저장(?: 편수)?", z), ("요약", "요약(?: 편수)?", s)):
        if not re.search(rf"{pat}[:\s]*{v}편", dg):
            fails.append(f"J6 다이제스트: '{label} {v}편'이 없음(목록.json 기준)")
    for p in papers:
        if p["title"] and p["title"] not in dg:
            fails.append(f"J6 {p['id']}: 다이제스트에 제목이 없음")
    if z < n and "조테로 미저장" not in dg:
        fails.append("J6 다이제스트: 조테로에 저장 못 한 논문이 있는데 '조테로 미저장' 표시가 없음")
    return fails


def latest_day():
    days = sorted(d for d in OUT.glob("20*") if (d / "목록.json").exists())
    return days[-1] if days else None


if __name__ == "__main__":
    only = sys.argv[1:2] == ["요약"] and len(sys.argv) == 3
    day = (OUT.parent / sys.argv[2] if only else OUT / sys.argv[1]) if len(sys.argv) > 1 else latest_day()
    if not day or not (day / "목록.json").exists():
        print("판정할 수 없음: 목록.json이 없습니다")
        sys.exit(2)
    fails = judge_summaries(day, json.loads((day / "목록.json").read_text())) if only else judge(day)
    for f in fails:
        print("FAIL " + f)
    print(f"판정 결과: 실패 {len(fails)}개")
    sys.exit(1 if fails else 0)
