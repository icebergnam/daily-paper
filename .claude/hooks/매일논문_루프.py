"""매일 논문 루프 문지기 — 노션에 올리기 전 "판정하고 다시 고치기"를 강제하는 훅 하나 (5주차 loop_gate.pl을 매일 논문에 맞춤)

.claude/settings.json의 hooks에 등록하고, 두 가지 때에 불린다:
  PreToolUse : 그날 실행 중(목록.json은 있고 노션완료.txt는 없음)에
               - 판정 장치·원천 파일(판정 스크립트, 이 훅, 설정, 목록.json, D*.txt, 판정 기록)을 고치려 하면 막는다.
               - notion-publisher를 부르려 하면 판정을 돌린다. 실패가 남으면 막고 실패 목록을 돌려준다(고친 뒤 다시 부름).
  Stop       : 다이제스트까지 썼는데 판정 실패가 남았으면 끝내지 못하게 하고 실패 목록을 돌려준다.
멈춤: 다 통과 / 최대 회차 / 두 번 연속 나아지지 않음 / 판정 장치가 바뀜 → 노션에 올리지 않고 사람에게 넘긴다.
회차와 결과는 workspace/매일논문/{날짜}/판정기록.md에 남는다. 표준 라이브러리만 쓴다.
"""
import datetime, hashlib, json, os, pathlib, subprocess, sys

MAX_ROUNDS = 3  # 회차마다 paper-reader를 다시 부르므로 5주차(5회)보다 적게
ROOT = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR") or pathlib.Path(__file__).resolve().parents[2])
OUT = ROOT / "workspace/매일논문"
JUDGE = ROOT / "scripts/매일논문_판정.py"


def emit(o):
    print(json.dumps(o, ensure_ascii=False))
    sys.exit(0)


def active_day():
    """루프가 지키는 날: 어제 이후 폴더 중 목록.json은 있고 노션완료.txt는 없는 가장 최근 날."""
    since = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    days = sorted(d for d in OUT.glob("20*") if d.name >= since and (d / "목록.json").exists())
    return days[-1] if days and not (days[-1] / "노션완료.txt").exists() else None


def watched(day):
    """루프 중 바뀌면 안 되는 판정 장치·원천 파일(해시로 지킴)."""
    return [JUDGE, pathlib.Path(__file__).resolve(), ROOT / ".claude/settings.json", day / "목록.json",
            *sorted(day.glob("D*.txt"))]


def protected(day):
    """편집 도구로 고칠 수 없는 파일: 지키는 파일 + 훅이 쓰는 상태·기록."""
    return watched(day) + [day / "판정상태.json", day / "판정기록.md"]


def digest(paths):
    return {str(p): hashlib.sha1(p.read_bytes()).hexdigest() if p.exists() else "missing" for p in paths}


def log(day, line):
    f = day / "판정기록.md"
    if not f.exists():
        f.write_text("# 판정 기록\n\n루프 문지기 훅(매일논문_루프.py)이 적는 파일입니다. 고치지 마세요.\n\n"
                     "| 회차 | 시각 | 때 | 실패 수 | 실패 (앞 3개) |\n|---|---|---|---|---|\n")
    with f.open("a") as fh:
        fh.write(line + "\n")


def judge_round(day, when):
    """판정 한 회차. (통과 여부, 사람에게 보여 줄 글)을 돌려준다. 멈추면 state에 stopped를 남긴다."""
    sf = day / "판정상태.json"
    st = json.loads(sf.read_text()) if sf.exists() else {"round": 0, "history": [], "hashes": digest(watched(day))}
    if st.get("stopped"):
        return False, f"루프가 이미 멈췄습니다({st['stopped']}). 노션에 올리지 말고 사람에게 넘기세요. → {day.name}/판정기록.md"
    changed = [pathlib.Path(p).name for p, h in st["hashes"].items() if digest([pathlib.Path(p)])[p] != h]
    if changed:
        st["stopped"] = "판정 장치·원천 파일이 바뀜: " + ", ".join(changed)
        sf.write_text(json.dumps(st, ensure_ascii=False, indent=1))
        log(day, f"\n- **멈춤: {st['stopped']}** — 꼼수인지 사람이 확인하세요\n")
        return False, f"루프 멈춤 · {st['stopped']} → 노션에 올리지 말고 사람에게 넘기세요"

    r = subprocess.run([sys.executable, "-I", str(JUDGE), day.name], capture_output=True, text=True)
    fails = [l[5:] for l in r.stdout.splitlines() if l.startswith("FAIL ")]
    n = len(fails) or (1 if r.returncode else 0)  # 판정 스크립트가 약속대로 끝나지 않으면 실패 1개로 친다
    st["round"] += 1
    st["history"].append(n)
    h, rd = st["history"], st["round"]
    short = " / ".join(fails[:3]).replace("|", "\\|")
    log(day, f"| {rd} | {datetime.datetime.now():%H:%M} | {when} | {n} | {short} |")

    stop = ("판정 기준을 모두 통과" if n == 0 else
            f"최대 회차({MAX_ROUNDS}) 도달" if rd >= MAX_ROUNDS else
            "두 번 연속 나아지지 않음" if len(h) >= 3 and h[-1] >= h[-2] >= h[-3] else "")
    if stop and n:
        st["stopped"] = stop
        log(day, f"\n- **멈춤: {stop}** (회차 {rd}, 남은 실패 {n}개) — 사람이 판단할 차례입니다\n")
    elif n == 0:
        log(day, f"\n- **통과** (회차 {rd})\n")
    sf.write_text(json.dumps(st, ensure_ascii=False, indent=1))
    if n == 0:
        return True, ""
    if stop:
        return False, f"루프 멈춤 · {stop} · 남은 실패 {n}개 → 노션에 올리지 말고, 알림에 '판정 실패로 노션 미업로드'를 적고 끝내세요."
    body = "\n".join(fails[:15] + (["…"] if len(fails) > 15 else []) or [r.stdout])
    return False, (f"[판정 {rd}/{MAX_ROUNDS}] 실패 {n}개가 남았습니다.\n{body}\n"
                   "D*.md는 paper-reader를 다시 불러 고치고(실패 줄을 전달), 다이제스트.md는 메인이 목록.json대로 고친 뒤 다시 진행하세요. "
                   "판정 스크립트·목록.json·D*.txt는 고칠 수 없습니다.")


def main():
    inp = json.load(sys.stdin)
    if os.environ.get("DAILY_PAPER_TEST"):  # 대시보드의 담당 시험(workspace/매일논문/시험/만 씀)은 그날 판정으로 막지 않는다
        sys.exit(0)
    day = active_day()
    if not day:
        sys.exit(0)
    event, ti = inp.get("hook_event_name"), inp.get("tool_input") or {}

    if event == "PreToolUse":
        path = ti.get("file_path") or ti.get("notebook_path")
        if path:
            p = (pathlib.Path(inp.get("cwd") or ROOT) / path).resolve()
            if p in {q.resolve() for q in protected(day)}:
                emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                      "permissionDecisionReason": f"매일 논문 실행 중에는 {p.name}을(를) 고칠 수 없습니다. 판정 장치와 원천 파일은 사람이 실행 밖에서만 고칩니다."}})
        if ti.get("subagent_type") == "notion-publisher":
            ok, msg = judge_round(day, "노션 전")
            if not ok:
                emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                      "permissionDecisionReason": msg}})
        sys.exit(0)

    if event == "Stop" and (day / "다이제스트.md").exists():
        st_file = day / "판정상태.json"
        if st_file.exists() and json.loads(st_file.read_text()).get("stopped"):
            sys.exit(0)  # 이미 멈춰 사람에게 넘겼으면 끝내게 둔다
        ok, msg = judge_round(day, "끝내기 전")
        if not ok:
            emit({"systemMessage": msg} if msg.startswith("루프") else {"decision": "block", "reason": msg})
    sys.exit(0)


if __name__ == "__main__":
    main()
