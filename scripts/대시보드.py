"""매일 논문 대시보드: 설정·담당 에이전트·날짜별 실행 기록을 웹 화면에서 보고 고친다.

사용: python3 scripts/대시보드.py [포트]   (기본 9008, 이 컴퓨터에서만 열림: http://127.0.0.1:9008)
      python3 scripts/대시보드.py 자체시험
      python3 scripts/대시보드.py 매일실행 [추가]   스킬 daily-paper를 한 번 끝까지 돌린다(매일 예약이 부른다)
고칠 수 있는 파일은 설정/(매일논문.json, 담당 설정, 연구자_정보.md)과 .claude/agents/*.md 뿐이고, 작업공간(.git 없는 폴더)에서만 저장한다.
담당 시험·새로 시작·매일 실행은 이 컴퓨터의 Claude Code(claude -p)로 담당을 부른다. 조테로 탐색은 읽기만 한다.
"""
import datetime, importlib.util, json, os, pathlib, plistlib, re, shutil, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "매일논문"
CFG_FILE, INFO_FILE = ROOT / "설정/매일논문.json", ROOT / "설정/연구자_정보.md"
PLIST = pathlib.Path.home() / "Library/LaunchAgents/com.daily-paper.plist"  # 매일 예약(launchd)
SCOUT_FILE = ROOT / "설정/paper-scout.json"  # 담당별 설정: paper-scout(키워드·기간·후보 수)
ZOTERO_FILE = ROOT / "설정/zotero-keeper.json"  # zotero-keeper(사용·컬렉션). 선택 담당
ZOTERO_DEFAULT = {"사용": True, "컬렉션": "자동수집"}
READER_FILE = ROOT / "설정/paper-reader.json"  # paper-reader(사용·요약할_편수). 선택 담당
READER_DEFAULT = {"사용": True, "요약할_편수": 2}
NOTION_FILE = ROOT / "설정/notion-publisher.json"  # notion-publisher(표지·아카이브 주소). 필수 담당, 새로 시작 때 담당이 쓴다
NOTION_DEFAULT = {"notion_url": "", "notion_db_url": ""}
AGENTS = ROOT / ".claude/agents"



def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


판정 = load("판정", "매일논문_판정.py")


def read_json(f, default=None):
    return json.loads(f.read_text()) if f.exists() else default


def front(text):
    """담당 파일 머리말(--- 사이)의 '키: 값'."""
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    return dict(re.findall(r"^(\w+):\s*(.+)$", m.group(1), re.M)) if m else {}


# 파일 메뉴: (묶음, 위치 패턴, 화면에서 고칠 수 있나). 고칠 수 있는 것은 담당·스킬·규칙 글(.md)뿐이다.
# 설정은 처음 설정의 각 단계 화면에서, 스크립트와 판정 장치는 화면에서 고치지 않는다(읽기만).
FILE_GROUPS = [("담당 에이전트", ".claude/agents/*.md", True), ("스킬 · 업무 매뉴얼", ".claude/skills/*/SKILL.md", True),
               ("스킬 · 참고 틀", ".claude/skills/*/references/*.md", True), ("스킬 · 스크립트", ".claude/skills/*/scripts/*.py", False),
               ("규칙·안내", "CLAUDE.md", True), ("규칙·안내", "시작하기.md", True), ("설정", "설정/*.json", False), ("설정", "설정/*.md", False),
               ("스크립트·훅", "scripts/*.py", False), ("스크립트·훅", ".claude/hooks/*.py", False), ("스크립트·훅", ".claude/settings.json", False)]
FILE_DESC = {"CLAUDE.md": "메인(대화·실행기)이 세션마다 읽는 규칙, 담당표, 호출표", "시작하기.md": "원본 저장소에서 '설정해 줘'로 처음 설정할 때 Claude가 따르는 순서",
             "설정/매일논문.json": "하루에 받을 편수(찾을_편수). 고치는 곳: 처음 설정 → 논문 찾기",
             "설정/paper-scout.json": "paper-scout 설정: 키워드·기간·키워드당 후보. 고치는 곳: 처음 설정 → 논문 찾기",
             "설정/zotero-keeper.json": "zotero-keeper 설정: 사용·컬렉션. 고치는 곳: 처음 설정 → 조테로 저장",
             "설정/paper-reader.json": "paper-reader 설정: 사용·요약할 편수. 고치는 곳: 처음 설정 → 요약",
             "설정/notion-publisher.json": "notion-publisher 설정: 표지·아카이브 주소. 새로 시작 때 담당이 씁니다",
             "설정/연구자_정보.md": "privacy-guard가 보는 '넣으면 안 되는 자료'. 고치는 곳: 처음 설정 → 넣으면 안 되는 자료",
             ".claude/settings.json": "Claude Code 프로젝트 설정: 판정 루프 훅 등록"}
BACKUP = OUT / "파일백업"  # 화면에서 저장하기 전 원래 내용을 여기 남긴다(git에 안 올라감)


def file_desc(rel, text):
    """파일 설명: 정해 둔 글 → 머리말 description 첫 문장 → 모듈 설명 첫 줄 → 첫 제목 줄."""
    if rel in FILE_DESC:
        return FILE_DESC[rel]
    if d := front(text).get("description"):
        return re.split(r"(?<=[다.])\s", d)[0]
    if m := re.match(r'\s*"""(.+)', text):
        return m.group(1).strip().rstrip('"')
    return next((l.lstrip("# ").strip() for l in text.splitlines() if l.startswith("#")), "")


def file_list():
    out, seen = [], set()
    for group, pat, editable in FILE_GROUPS:
        for f in sorted(ROOT.glob(pat)):
            rel = f.relative_to(ROOT).as_posix()
            if rel in seen or not f.is_file():
                continue
            seen.add(rel)
            text = f.read_text(errors="replace")
            out.append({"group": group, "path": rel, "desc": file_desc(rel, text), "editable": editable,
                        "size": f.stat().st_size, "mtime": f.stat().st_mtime_ns})
    return out


def file_get(rel):
    item = next((x for x in file_list() if x["path"] == rel), None)  # 목록에 있는 파일만 연다(../ 같은 경로 막기)
    if not item:
        return 404, {"error": "목록에 없는 파일입니다"}
    return 200, item | {"text": (ROOT / rel).read_text(errors="replace")}


def file_save(rel, text, mtime):
    """화면에서 고친 담당·스킬·규칙 글을 저장한다. 열어 둔 뒤 다른 곳에서 바뀌었으면 덮어쓰지 않는다. 원래 내용은 파일백업에 남긴다."""
    item = next((x for x in file_list() if x["path"] == rel), None)
    if not item or not item["editable"]:
        return False, "화면에서 고칠 수 없는 파일입니다"
    f = ROOT / rel
    if mtime and int(mtime) != f.stat().st_mtime_ns:
        return False, "열어 둔 뒤 다른 곳에서 이 파일이 바뀌었습니다. 다시 열어 최신 내용에 고쳐 주세요"
    want = f.parent.name if f.name == "SKILL.md" else f.stem if rel.startswith(".claude/agents/") else None
    if want and front(text).get("name") != want:
        return False, f"머리말(--- 사이)에 'name: {want}'이 있어야 합니다"
    BACKUP.mkdir(parents=True, exist_ok=True)
    (BACKUP / f"{time.strftime('%Y%m%d-%H%M%S')}_{rel.replace('/', '__')}").write_text(f.read_text())
    f.write_text(text)
    CHECKS.pop("에이전트", None)
    return True, f"{rel} 저장 — 대시보드의 시험·지금 논문 찾기·예약은 다음 실행부터 바로 반영됩니다(원래 내용은 매일논문/파일백업/)"


def day_record(d):
    papers = read_json(d / "목록.json", [])
    try:
        fails = 판정.judge(d)
    except Exception as e:
        fails = [f"판정할 수 없음: {e}"]
    loop = read_json(d / "판정상태.json", {})
    done, sent = d / "노션완료.txt", d / "노션올림.txt"
    return {"day": d.name, "digest": (d / "다이제스트.md").exists(), "fails": fails, "stopped": loop.get("stopped", ""),
            "rounds": loop.get("round", 0), "notion": done.read_text().strip() if done.exists() else "",
            "sent": sent.read_text().split() if sent.exists() else [],
            "papers": [{k: p.get(k) for k in ("id", "title", "url", "keyword", "zotero_saved", "zotero_error", "summarize", "batch")}
                       | {"has_md": (d / f"{p['id']}.md").exists()} for p in papers]}


def state():
    return {
        "config": read_json(CFG_FILE),
        "scout": read_json(SCOUT_FILE),
        "zotero": read_json(ZOTERO_FILE, ZOTERO_DEFAULT),
        "reader": read_json(READER_FILE, READER_DEFAULT),
        "notion": read_json(NOTION_FILE, NOTION_DEFAULT),
        "tests": {f.stem: read_json(TESTS / f.stem / "결과.json") for f in AGENTS.glob("*.md")},
        "info": INFO_FILE.read_text(),
        "agents": [{"name": f.stem, "text": f.read_text(), **{k: v for k, v in front(f.read_text()).items() if k in ("model", "tools", "description")},
                    "unset": "_ID__" in f.read_text()} for f in sorted(AGENTS.glob("*.md"))],
        "days": [day_record(d) for d in sorted(OUT.glob("20*"), reverse=True) if (d / "목록.json").exists()],
        "schedule": schedule_get(),
        "readonly": (ROOT / ".git").exists(),
        "root": str(ROOT),
        "today": datetime.date.today().isoformat(),
        "checks": {"claude": claude_now(), "기본": CHECKS.get("기본") or run_check("기본"),
                   **{k: CHECKS.get(k) for k in ("찾기", "조테로", "에이전트")}},
    }


def hint(err, kind):
    """Claude Code 오류에 붙일 한 줄 안내."""
    e = err.lower()
    if kind == "claude-code" and re.search(r"authenticat|oauth|revoked|log ?in|401", e):
        return "터미널에서 claude를 실행해 다시 로그인하세요"
    if "찾을 수 없음" in err:
        return "Claude Code를 설치하고 터미널에서 claude로 로그인하세요"
    if "timed out" in e or "timeout" in e:
        return "응답이 너무 늦습니다. 잠시 뒤 다시 확인하세요"
    return ""


def claude_case(err, installed, logged_in):
    """Claude Code 연결 실패의 갈래: install / login / limit / model / network / other."""
    e = err.lower()
    if not installed:
        return "install"
    if logged_in is False or re.search(r"authenticat|oauth|revoked|log ?in|401", e):
        return "login"
    if re.search(r"rate.?limit|usage limit|limit reached|429|overloaded|529", e):
        return "limit"
    if "model" in e:
        return "model"
    if re.search(r"enotfound|network|getaddrinfo|econn|timed out|timeout", e):
        return "network"
    return "other"


def claude_diag(err):
    """claude가 어디 있는지, 버전, 로그인 상태(claude auth status)를 모아 갈래를 정한다."""
    exe, d = shutil.which("claude"), {}
    if exe:
        d["path"] = exe
        try:
            d["version"] = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15).stdout.strip()
            st = json.loads(subprocess.run([exe, "auth", "status"], capture_output=True, text=True, timeout=15).stdout)
            d["loggedIn"], d["account"] = st.get("loggedIn"), st.get("email", "")
        except Exception:
            pass
    d["case"] = claude_case(err, bool(exe), d.get("loggedIn"))
    return d


def ask_claude(system, prompt):
    """claude CLI로 한 번 묻는다(설정 도우미). 도구·MCP·설정(훅)을 모두 끄고 임시 폴더에서 돌린다."""
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("claude 명령을 찾을 수 없음 → Claude Code를 설치하고 터미널에서 claude로 로그인")
    r = subprocess.run([exe, "-p", "--tools", "", "--strict-mcp-config", "--setting-sources", "", "--no-session-persistence",
                        "--system-prompt", system], input=prompt, capture_output=True, text=True, timeout=600, cwd=tempfile.gettempdir())
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300] or f"claude 종료 코드 {r.returncode}")
    return r.stdout


CHECKS = {}  # 설정점검 결과를 기억한다: {"기본": {...}, "조테로": {...}, "에이전트"(전부): {...}}
SECTION_MODES = ("설치", "기본", "찾기", "조테로", "요약", "노션")  # 묶음 하나만 보는 점검은 ❌가 없어야 통과


def run_check(mode):
    """설정점검.py를 돌린다. 설치 점검은 ❌가 없어야, 나머지는 종료 코드 0(설정 항목이 다 있음)이어야 통과."""
    r = subprocess.run([sys.executable, str(ROOT / "scripts/설정점검.py"), *([mode] if mode != "에이전트" else [])],
                       capture_output=True, text=True, timeout=90)
    out = r.stdout + r.stderr
    CHECKS[mode] = {"out": out, "ok": "❌" not in out if mode in SECTION_MODES else r.returncode == 0, "at": time.strftime("%H:%M")}
    return CHECKS[mode]


def claude_now(refresh=False):
    """이 컴퓨터의 Claude Code 설치·로그인 상태(처음 설정 1단계). 느리니 기억해 두고 '다시 확인' 때만 새로 본다."""
    if refresh or "claude" not in CHECKS:
        d = claude_diag("")
        CHECKS["claude"] = d | {"ok": bool(d.get("loggedIn")), "at": time.strftime("%H:%M")}
    return CHECKS["claude"]


HELP_SYS = """너는 '매일 논문' 대시보드의 설정 도우미다. 사용자는 개발자가 아닐 수 있다.
한국어로, 짧은 번호 목록으로, 대시보드에서 무엇을 누르고 터미널에 무엇을 치면 되는지 알려 준다.
노션·Exa 커넥터는 claude.ai → 설정 → 커넥터에서 연결하라고 안내한다. 담당 시험은 각 단계의 "시험 실행" 버튼으로 한다.
키·토큰 값을 묻거나 대화창에 붙여넣으라고 하지 않는다. 모르면 모른다고 말한다.
대시보드의 처음 설정은 8단계다. 기본을 갖춘 뒤 담당 에이전트 순서로 담당마다 필요한 것을 채운다:
1 Claude Code 로그인 → 2 기본 점검 → 3 논문 찾기(paper-scout) → 4 조테로 저장(zotero-keeper) → 5 요약(paper-reader) → 6 넣으면 안 되는 자료(privacy-guard) → 7 노션 올리기(notion-publisher) → 8 마무리 점검.
단계 번호는 이 순서로 말한다. 노션 올리기 단계에서는 페이지 주소를 넣고 '새로 시작'을 누르면 notion-publisher가 아카이브와 표지를 만들고 시험한다."""


def help_answer(step, detail, question):
    """처음 설정에서 막힌 단계의 실패 내용을 Claude Code에 보내 고치는 방법을 묻는다(도구는 모두 끈 채로)."""
    now = {"키워드": read_json(SCOUT_FILE, {}).get("키워드"), "표지 페이지 있음": bool(read_json(NOTION_FILE, NOTION_DEFAULT).get("notion_url")),
           "노션 아카이브 있음": bool(read_json(NOTION_FILE, NOTION_DEFAULT).get("notion_db_url")),
           "조테로 사용": read_json(ZOTERO_FILE, ZOTERO_DEFAULT).get("사용"), "요약 사용": read_json(READER_FILE, READER_DEFAULT).get("사용")}
    guide_text = (ROOT / "시작하기.md").read_text()[:6000] if (ROOT / "시작하기.md").exists() else ""
    prompt = (f"[참고: 설정 안내서]\n{guide_text}\n\n[지금 설정]\n{json.dumps(now, ensure_ascii=False)}\n\n"
              f"[막힌 단계] {step}\n[화면에 나온 실패]\n{detail[:4000]}\n\n[질문] {question or '어떻게 고치면 되나요?'}")
    t = time.monotonic()
    try:
        return {"ok": True, "answer": ask_claude(HELP_SYS, prompt).strip(), "secs": round(time.monotonic() - t, 1)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300], "hint": hint(str(e), "claude-code")}


RUN = {"proc": None, "log": OUT / "실행.jsonl", "started": None}  # 지금 실행은 한 번에 하나만
# 매일 실행의 메인(스킬 daily-paper)이 직접 쓰는 도구. 담당들의 도구는 담당 파일에서 더한다
DAILY_TOOLS = ["Task", "Read", "Glob", "Write", "Bash(python3 scripts/설정점검.py:*)", "Bash(python3 scripts/매일논문.py 저장:*)",
               "Bash(python3 scripts/매일논문_판정.py:*)", "Bash(osascript -e:*)"]


def daily_cmd():
    """매일 실행(스킬 daily-paper)을 머리 없이 띄우는 claude 명령. 허용 도구 밖은 묻지 않고 거절(dontAsk). 판정 루프 훅은 그대로 돈다."""
    tools = list(dict.fromkeys(DAILY_TOOLS + [x for f in sorted(AGENTS.glob("*.md")) for x in agent_tools(f.stem)]))
    system = ("너는 대시보드·예약이 띄운 매일 논문 실행기다. CLAUDE.md의 처음 열었을 때 절차는 하지 않고, 스킬 daily-paper의 순서만 따른다. "
              "Bash 명령은 스킬에 적힌 글자 그대로만 실행하고 앞뒤에 아무것도(;, &&, |, echo, 2>&1, cd) 붙이지 않는다. "
              "거절되면 붙인 것이 없는지 보고 글자 그대로 다시 실행한다. 사람에게 묻지 않는다(아무도 보고 있지 않다).")
    return [shutil.which("claude") or "claude", "-p", "--model", "sonnet", "--no-session-persistence", "--permission-mode", "dontAsk",
            "--append-system-prompt", system, "--agents", json.dumps(agents_json(), ensure_ascii=False),
            "--allowedTools", ",".join(tools), "--output-format", "stream-json", "--verbose"]


def start_run(extra=True):
    """'지금 논문 찾기'(extra: 설정 편수만큼 더)와 예약 실행: Claude Code가 스킬 daily-paper를 따른다. 진행은 실행.jsonl."""
    if RUN["proc"] and RUN["proc"].poll() is None:
        return False, "이미 실행 중입니다"
    if not shutil.which("claude"):
        return False, "claude 명령을 찾을 수 없습니다. 처음 설정 1단계를 보세요"
    OUT.mkdir(exist_ok=True)
    with RUN["log"].open("w") as f:
        RUN["proc"] = subprocess.Popen(daily_cmd(), stdin=subprocess.PIPE, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT, text=True)
    RUN["proc"].stdin.write("/daily-paper" + (" 추가" if extra else ""))  # 프롬프트는 표준 입력으로(--allowedTools가 뒤 인자를 삼킨다)
    RUN["proc"].stdin.close()
    RUN["started"] = time.time()
    return True, "시작했습니다"


def read_stream(f):
    """claude stream-json 기록에서 도구 호출 줄, 마지막 보고, JSON이 아닌 줄(오류), 부른 담당 이름들."""
    steps, report, other, called = [], "", [], []
    for line in f.read_text().splitlines() if f.exists() else []:
        try:
            e = json.loads(line)
        except ValueError:
            other.append(line)
            continue
        for c in (e.get("message") or {}).get("content") or []:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                steps.append(tool_step(c))
                if c.get("name") in ("Task", "Agent"):
                    called.append((c.get("input") or {}).get("subagent_type") or "")
        if e.get("type") == "result":
            report = e.get("result") or ""
    return steps, report, "\n".join(other)[-1500:], called


def run_status():
    p = RUN["proc"]
    steps, report, err, called = read_stream(RUN["log"])
    return {"running": bool(p and p.poll() is None), "code": p.poll() if p else None, "steps": steps[-40:], "report": report,
            "error": err, "agents": called, "secs": round(time.time() - RUN["started"]) if RUN["started"] else 0}


def make_workspace():
    """원본 저장소 안에 작업공간 workspace/를 만든다(시작하기.md 2단계의 rsync와 같은 것을 뺀다). 이미 있으면 그대로 쓴다."""
    ws = ROOT / "workspace"
    if not (ROOT / ".git").exists():
        return False, "이미 작업공간에서 열려 있습니다"
    if not (ws / "scripts" / "대시보드.py").exists():
        if ws.exists():
            return False, f"{ws} 폴더가 있지만 작업공간이 아닙니다. 확인한 뒤 옮기거나 지우고 다시 누르세요"
        def skip(d, names):
            d = pathlib.Path(d)
            return [n for n in names if n in (".git", ".idea", "__pycache__", ".DS_Store", "매일논문")
                    or (d == ROOT and n == "workspace") or (d == ROOT / ".claude" and n == "worktrees")]
        shutil.copytree(ROOT, ws, ignore=skip, symlinks=True)
    return True, str(ws)


def reopen_in(ws, port):
    """대시보드를 작업공간 쪽 대시보드로 바꿔 띄운다(같은 포트, 새 창은 열지 않음). 응답을 보낸 뒤 부른다."""
    os.environ["DASH_REOPEN"] = "1"
    os.execv(sys.executable, [sys.executable, str(ws / "scripts" / "대시보드.py"), str(port)])


def schedule_get():
    """지금 예약 시각 'HH:MM'(없으면 빈 글자)."""
    try:
        c = plistlib.loads(PLIST.read_bytes())["StartCalendarInterval"]
        return f"{c['Hour']:02d}:{c['Minute']:02d}"
    except Exception:
        return ""


def schedule_set(at):
    """매일 그 시각에 '대시보드.py 매일실행'이 돌게 Mac(launchd)에 등록한다. at이 빈 글자면 끈다."""
    if at and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", at):
        return False, "시각은 HH:MM(24시간)으로 적어 주세요"
    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
    if not at:
        PLIST.unlink(missing_ok=True)
        return True, "예약을 껐습니다"
    h, m = map(int, at.split(":"))
    OUT.mkdir(exist_ok=True)  # launchd는 로그 폴더를 만들어 주지 않는다
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_bytes(plistlib.dumps({
        "Label": "com.daily-paper", "ProgramArguments": [sys.executable, str(pathlib.Path(__file__).resolve()), "매일실행"],
        "StartCalendarInterval": {"Hour": h, "Minute": m}, "WorkingDirectory": str(ROOT),
        "EnvironmentVariables": {"PATH": os.environ.get("PATH", "")},  # launchd 기본 PATH에는 claude가 없다
        "StandardOutPath": str(OUT / "예약실행.log"), "StandardErrorPath": str(OUT / "예약실행.log")}))
    r = subprocess.run(["launchctl", "load", str(PLIST)], capture_output=True, text=True)
    return (r.returncode == 0), (f"매일 {at}에 돕니다(그 시각에 Mac이 켜져 있어야 합니다)" if r.returncode == 0 else "launchd 등록 실패: " + r.stderr.strip())


TESTS = OUT / "시험"  # 담당 시험 결과: 매일논문/시험/{담당}/(실행.jsonl, 결과.json)
AGENT_RUNS = {}  # 담당 시험은 담당마다 한 번에 하나
TEST_PREP = {"paper-reader": [sys.executable, str(ROOT / "scripts/매일논문.py"), "시험준비"]}  # paper-scout 시험 후보에서 PDF 한 편


def agent_tools(name):
    """담당 파일 머리말의 tools를 --allowedTools 목록으로. Bash(…) 괄호 안의 쉼표는 자르지 않는다."""
    tools = front((AGENTS / f"{name}.md").read_text()).get("tools", "")
    return [x.strip() for x in re.split(r",(?![^()]*\))", tools) if x.strip()]


CANARY = """# 시험용 가짜 자료 (privacy-guard가 '중단'을 내야 함)
Confidential — Do not distribute. Manuscript ID: TEST-2026-0001 (under review)
연락: 010-0000-0000, fake.person@example.com
"""


def prep_privacy(d):
    """privacy-guard 시험 재료: 앞 담당의 실제 결과(통과해야 함)와 가짜 민감 자료(중단해야 함)."""
    md = TESTS / "paper-reader/D01.md"
    if md.exists():
        normal = md.read_text()
    else:
        f = TESTS / "paper-scout/후보_exa.json"
        if not f.exists():
            return "paper-scout 시험 결과가 없습니다. 논문 찾기 단계의 시험을 먼저 하세요"
        normal = "# paper-scout가 찾은 제목\n" + "\n".join(f"- {p.get('title', '')}" for p in json.loads(f.read_text())[:5])
    (d / "대상_정상.md").write_text(normal)
    (d / "대상_민감.md").write_text(CANARY)
    return ""


def prep_notion(d):
    """notion-publisher 시험 재료: paper-reader 시험 결과(요약 포함), 없으면 paper-scout 시험 후보 한 편(요약 없이)."""
    r = TESTS / "paper-reader"
    if (r / "목록.json").exists():
        shutil.copy(r / "목록.json", d / "목록.json")
        if (r / "D01.md").exists():
            shutil.copy(r / "D01.md", d / "D01.md")
        return ""
    s = TESTS / "paper-scout"
    pool = [p for f in ("후보_exa.json", "후보_openalex.json") if (s / f).exists() for p in json.loads((s / f).read_text())]
    if not pool:
        return "paper-scout 시험 결과가 없습니다. 논문 찾기 단계의 시험을 먼저 하세요"
    (d / "목록.json").write_text(json.dumps([pool[0] | {"id": "D01", "summarize": False}], ensure_ascii=False, indent=1))
    return ""


TEST_PREP |= {"privacy-guard": prep_privacy, "notion-publisher": prep_notion}
NEW_START = re.compile(r"새로 시작: (https://([\w-]+\.)?notion\.(so|site|com)/\S+)( 덮어쓰기 허락)?")


def agents_json():
    """이 폴더의 담당 파일 전부를 --agents JSON으로. 작업공간이 원본 저장소(git) 안에 있으면 Claude Code가 저장소 맨 위의
    .claude/agents(예전 담당)를 이 폴더 것보다 앞세우므로, 대시보드가 띄우는 실행은 늘 이 폴더의 담당 파일로 못 박는다."""
    out = {}
    for f in sorted(AGENTS.glob("*.md")):
        text = f.read_text()
        head = re.match(r"---\n(.*?)\n---\n?", text, re.S)
        meta = front(text)
        skills = re.findall(r"^\s+-\s+(\S+)", re.search(r"^skills:\n((?:\s+-.*\n?)*)", head.group(1) + "\n", re.M).group(1), re.M) \
            if head and re.search(r"^skills:", head.group(1), re.M) else []
        out[f.stem] = {"description": meta.get("description", ""), "prompt": text[head.end():] if head else text,
                       "tools": agent_tools(f.stem), **({"model": meta["model"]} if meta.get("model") else {}), **({"skills": skills} if skills else {})}
    return out


def start_agent_test(name, task="시험"):
    """담당 시험: 이 컴퓨터의 Claude Code를 작업공간에서 머리 없이 띄워 그 담당에게 '시험'(스킬의 할 일 C)을 맡긴다.
    담당 파일의 tools만 쓰고(--tools) 허용한다(dontAsk: 그 밖은 묻지 않고 거절). 진행은 stream-json으로 실행.jsonl에 남는다.
    --agent로 담당을 바로 띄우면 claude.ai 커넥터(Exa·Notion)가 안 보여서, 메인이 Task로 담당을 부르게 한다.
    메인이 subagent_type을 빠뜨리면 일반 에이전트가 대신 돌아 버리므로 지시는 시스템 프롬프트에 못 박는다."""
    if not re.fullmatch(r"[\w-]+", name or "") or not (AGENTS / f"{name}.md").exists() or not (ROOT / f".claude/skills/{name}/SKILL.md").exists():
        return False, "시험할 수 없는 담당입니다"
    if task != "시험" and not (name == "notion-publisher" and NEW_START.fullmatch(task or "")):  # 화면이 맡길 수 있는 일은 이 둘뿐
        return False, "맡길 수 없는 일입니다"
    if (r := AGENT_RUNS.get(name)) and r["proc"].poll() is None:
        return False, "이미 시험 중입니다"
    exe = shutil.which("claude")
    if not exe:
        return False, "claude 명령을 찾을 수 없습니다. 1단계 Claude Code 로그인을 보세요"
    d = TESTS / name
    shutil.rmtree(d, ignore_errors=True)  # 지난 시험의 후보 파일을 다시 쓰지 않게 매번 비우고 시작
    d.mkdir(parents=True)
    if callable(prep := TEST_PREP.get(name)):
        if err := prep(d):
            return False, "시험 준비 실패: " + err
    elif prep:  # 담당이 바깥에 나가지 않게, 시험 재료(PDF 등)는 대시보드가 미리 받아 둔다
        r = subprocess.run(prep, capture_output=True, text=True, cwd=ROOT, timeout=180)
        if r.returncode:
            return False, "시험 준비 실패: " + ((r.stderr or r.stdout).strip().splitlines() or ["?"])[-1]
    tools = ["Task", *agent_tools(name)]
    builtin = sorted({x.split("(")[0] for x in tools if not x.startswith("mcp__")})  # MCP 도구는 --tools가 아니라 허용 목록으로만
    job = "시험: 스킬 {name}의 시험 할 일을 해라" if task == "시험" else f"{task} — 스킬 {name}의 새로 시작 할 일을 하고 이어서 시험까지 해라"
    system = (f"너는 대시보드가 띄운 담당 실행기다. CLAUDE.md의 처음 열었을 때 절차와 설정 점검은 하지 않는다. "
              f'할 일은 하나: Task 도구를 subagent_type "{name}", prompt "{job.format(name=name)}"로 정확히 한 번, '
              f"백그라운드 없이 부르고, 담당의 보고를 그대로 전한다. 다른 도구는 쓰지 않는다.")
    with (d / "실행.jsonl").open("w") as f:
        proc = subprocess.Popen([exe, "-p", "--model", "sonnet", "--no-session-persistence", "--permission-mode", "dontAsk",
                                 "--append-system-prompt", system, "--agents", json.dumps(agents_json(), ensure_ascii=False),
                                 "--tools", ",".join(builtin), "--allowedTools", ",".join(tools),
                                 "--output-format", "stream-json", "--verbose"],
                                stdin=subprocess.PIPE, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT, text=True,
                                env=os.environ | {"DAILY_PAPER_TEST": "1"})  # 루프 훅은 시험 실행을 그날 판정으로 막지 않는다
    proc.stdin.write(task)
    proc.stdin.close()
    AGENT_RUNS[name] = {"proc": proc, "started": time.time()}
    return True, "시험을 시작했습니다"


def tool_step(c):
    """stream-json의 도구 호출 하나를 화면에 보일 한 줄로."""
    i = c.get("input") or {}
    what = i.get("command") or i.get("query") or i.get("file_path") or i.get("url") or i.get("description") or ""
    return f"{re.sub(r'^mcp__[^_]+(?:_[^_]+)*?__', '', c.get('name', ''))} {what}"[:160]


def agent_test_status(name):
    d, r = TESTS / name, AGENT_RUNS.get(name)
    p = r and r["proc"]
    steps, report, err, called = read_stream(d / "실행.jsonl")
    wrong = next((f"메인이 {name} 대신 다른 에이전트({a or '일반'})를 불렀습니다. 다시 시험하세요." for a in called if a != name), "")
    return {"running": bool(p and p.poll() is None), "secs": round(time.time() - r["started"]) if r else 0,
            "steps": steps[-40:], "report": report, "error": wrong or err, "result": read_json(d / "결과.json")}


ZAPI = "http://127.0.0.1:23119/api/users/0/"
ZPATH = re.compile(r"collections|items/top|collections/[A-Z0-9]{8}/items/top|items/[A-Z0-9]{8}/children")


def zget(path, q):
    with urllib.request.urlopen(urllib.request.Request(ZAPI + path + "?" + urllib.parse.urlencode(q | {"format": "json"}),
                                                       headers={"User-Agent": "daily-papers/1"}), timeout=10) as r:
        return json.loads(r.read()), int(r.headers.get("Total-Results") or 0)


def zotero(path, params):
    """조테로 로컬 API를 읽기만 한다. 정해진 경로와 검색 칸만 넘기고, 화면에 필요한 칸만 돌려준다."""
    if not ZPATH.fullmatch(path or ""):
        return 400, {"error": "허용하지 않는 경로"}
    q = {k: v for k, v in params.items() if k in ("q", "qmode", "start", "sort", "direction")}
    try:
        if path == "collections":  # 컬렉션은 전부(100개씩 넘겨 받기)
            rows, start, total = [], 0, 1
            while start < total:
                page, total = zget(path, {"limit": 100, "start": start})
                rows, start = rows + page, start + 100
            return 200, {"items": [{"key": c["key"], "name": c["data"]["name"], "parent": c["data"].get("parentCollection") or "",
                                    "n": c.get("meta", {}).get("numItems", 0)} for c in rows], "total": len(rows)}
        rows, total = zget(path, q | {"limit": 50})
    except Exception as e:
        return 502, {"error": str(e)[:200]}
    def item(i):
        d = i["data"]
        return {"key": i["key"], "type": d.get("itemType"), "title": d.get("title") or d.get("filename") or "(제목 없음)",
                "creators": [c.get("lastName") or c.get("name") or "" for c in d.get("creators", [])],
                "date": d.get("date", ""), "pub": d.get("publicationTitle") or d.get("proceedingsTitle") or d.get("bookTitle") or d.get("websiteTitle") or "",
                "doi": d.get("DOI", ""), "url": d.get("url", ""), "abstract": d.get("abstractNote", ""),
                "tags": [t["tag"] for t in d.get("tags", [])], "children": i.get("meta", {}).get("numChildren", 0),
                "contentType": d.get("contentType", "")}
    return 200, {"items": [item(i) for i in rows], "total": total}


def check_config(c):
    """저장 전 검사. 문제가 있으면 이유, 없으면 빈 문자열."""
    if not isinstance(c, dict):
        return "설정은 JSON 객체여야 합니다"
    if not (type(c.get("찾을_편수")) is int and c["찾을_편수"] > 0):
        return "찾을_편수는 1 이상의 정수여야 합니다"
    return ""


def check_scout(s):
    """paper-scout 설정 저장 전 검사. 문제가 있으면 이유, 없으면 빈 문자열."""
    if not isinstance(s, dict):
        return "설정은 JSON 객체여야 합니다"
    if not isinstance(s.get("키워드"), list) or not all(isinstance(k, str) and k.strip() for k in s["키워드"]):
        return "키워드는 빈 칸 없는 글자 목록이어야 합니다"
    if not (type(s.get("기간_일")) is int and 1 <= s["기간_일"] <= 365):
        return "기간_일은 1~365 사이 정수여야 합니다"
    if not (type(s.get("키워드당_후보")) is int and 1 <= s["키워드당_후보"] <= 200):
        return "키워드당_후보는 1~200 사이 정수여야 합니다"
    return ""


def check_zotero(z):
    """zotero-keeper 설정 저장 전 검사."""
    if not isinstance(z, dict) or type(z.get("사용")) is not bool:
        return "사용은 true 또는 false여야 합니다"
    if not isinstance(z.get("컬렉션"), str) or not z["컬렉션"].strip():
        return "컬렉션 이름을 적어 주세요"
    return ""


def check_reader(r):
    """paper-reader 설정 저장 전 검사. 요약할_편수는 찾을_편수 이하."""
    n = (read_json(CFG_FILE, {}) or {}).get("찾을_편수", 0)
    if not isinstance(r, dict) or type(r.get("사용")) is not bool:
        return "사용은 true 또는 false여야 합니다"
    if not (type(r.get("요약할_편수")) is int and 0 < r["요약할_편수"] <= n):
        return f"요약할_편수는 1 이상, 찾을_편수({n}) 이하의 정수여야 합니다"
    return ""


AGENT_CFG = {"scout": (SCOUT_FILE, check_scout), "zotero": (ZOTERO_FILE, check_zotero), "reader": (READER_FILE, check_reader)}  # 화면에서 고치는 담당 설정


def save(kind, name, text):
    """화면에서 온 저장 요청. (성공 여부, 알림 글)."""
    if kind == "config":
        try:
            c = json.loads(text)
        except ValueError as e:
            return False, f"JSON이 깨졌습니다: {e}"
        if err := check_config(c):
            return False, err
        CFG_FILE.write_text(json.dumps(c, ensure_ascii=False, indent=2) + "\n")
        CHECKS.pop("에이전트", None)  # 설정이 바뀌었으니 다시 점검하게
        return True, "설정/매일논문.json 저장"
    if kind in AGENT_CFG:
        f, check = AGENT_CFG[kind]
        try:
            s = json.loads(text)
        except ValueError as e:
            return False, f"JSON이 깨졌습니다: {e}"
        if err := check(s):
            return False, err
        f.write_text(json.dumps(s, ensure_ascii=False, indent=2) + "\n")
        CHECKS.pop("에이전트", None), CHECKS.pop("찾기", None), CHECKS.pop("조테로", None), CHECKS.pop("요약", None)
        return True, f"설정/{f.name} 저장 — 바뀐 설정은 시험을 다시 해야 통과로 칩니다"
    if kind == "info":
        INFO_FILE.write_text(text)
        CHECKS.pop("에이전트", None)
        return True, "설정/연구자_정보.md 저장"
    if kind == "agent":
        f = AGENTS / f"{name}.md"
        if not re.fullmatch(r"[\w-]+", name or "") or not f.exists():
            return False, "없는 담당 에이전트입니다"
        if front(text).get("name") != name:
            return False, f"머리말(--- 사이)에 'name: {name}'이 있어야 합니다"
        f.write_text(text)
        CHECKS.pop("에이전트", None)
        return True, f"{f.name} 저장 — 담당 에이전트는 Claude Code 새 세션부터 반영됩니다"
    return False, "고칠 수 없는 파일입니다"


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def local(self):
        # 다른 사이트가 이 서버로 요청을 보내는 것(DNS 리바인딩) 막기
        return self.headers.get("Host", "").split(":")[0] in ("127.0.0.1", "localhost")

    def do_GET(self):
        if not self.local():
            return self.reply(403, {"error": "로컬에서만"})
        if self.path.startswith("/api/zotero?"):
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
            return self.reply(*zotero(q.pop("path", ""), q))
        if self.path == "/api/run":
            return self.reply(200, run_status())
        if self.path == "/api/files":
            return self.reply(200, {"files": file_list(), "readonly": (ROOT / ".git").exists()})
        if self.path.startswith("/api/file?"):
            return self.reply(*file_get(dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query)).get("path", "")))
        if self.path.startswith("/api/agent/test?"):
            name = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query)).get("name", "")
            return self.reply(200, agent_test_status(name) if re.fullmatch(r"[\w-]+", name) else {"error": "이름"})
        if self.path == "/":
            return self.reply(200, PAGE.encode(), "text/html; charset=utf-8")
        if self.path == "/api/state":
            return self.reply(200, state())
        self.reply(404, {"error": "없음"})

    def do_POST(self):
        # JSON이 아닌 요청은 받지 않는다: 다른 사이트의 폼 전송은 JSON을 못 보낸다(CORS 사전 확인에 걸림)
        if not self.local() or not self.headers.get("Content-Type", "").startswith("application/json"):
            return self.reply(403, {"error": "로컬 JSON 요청만"})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/api/save":
            if (ROOT / ".git").exists():  # 공개 저장소에는 개인 값을 쓰지 않는다
                return self.reply(403, {"ok": False, "msg": "원본 저장소라 저장하지 않습니다. 작업공간 폴더에서 대시보드를 여세요"})
            ok, msg = (file_save(str(body.get("name") or ""), body.get("text", ""), body.get("mtime")) if body.get("kind") == "file"
                       else save(body.get("kind"), body.get("name"), body.get("text", "")))
            return self.reply(200 if ok else 400, {"ok": ok, "msg": msg})
        if self.path == "/api/run":
            if (ROOT / ".git").exists():
                return self.reply(403, {"ok": False, "msg": "원본 저장소에서는 실행하지 않습니다. 작업공간 폴더에서 대시보드를 여세요"})
            ok, msg = start_run(extra=True)
            return self.reply(200 if ok else 409, {"ok": ok, "msg": msg})
        if self.path == "/api/agent/test":
            if (ROOT / ".git").exists():
                return self.reply(403, {"ok": False, "msg": "원본 저장소에서는 시험하지 않습니다. 작업공간 폴더에서 대시보드를 여세요"})
            ok, msg = start_agent_test(str(body.get("name", "")), str(body.get("task") or "시험"))
            return self.reply(200 if ok else 409, {"ok": ok, "msg": msg})
        if self.path == "/api/claude":
            return self.reply(200, claude_now(refresh=True))
        if self.path == "/api/help":
            return self.reply(200, help_answer(str(body.get("step", ""))[:40], str(body.get("detail", "")), str(body.get("question", ""))[:1000]))
        if self.path == "/api/schedule":
            if (ROOT / ".git").exists():
                return self.reply(403, {"ok": False, "msg": "원본 저장소에서는 예약하지 않습니다. 작업공간 폴더에서 대시보드를 여세요"})
            ok, msg = schedule_set(str(body.get("at") or ""))
            return self.reply(200 if ok else 400, {"ok": ok, "msg": msg})
        if self.path == "/api/check":
            return self.reply(200, run_check(body.get("mode") if body.get("mode") in SECTION_MODES else "에이전트"))
        if self.path == "/api/workspace":
            ok, msg = make_workspace()
            self.reply(200 if ok else 400, {"ok": ok, "msg": msg})
            if ok:
                threading.Timer(0.5, reopen_in, (pathlib.Path(msg), self.server.server_address[1])).start()
            return
        self.reply(404, {"error": "없음"})

    def log_message(self, *a):
        pass


PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>매일 논문 관리</title>
<style>
:root{
 --bg:#f6f5f2;--surface:#fff;--surface2:#f2f0ec;--line:#e7e4de;--line2:#d7d3cb;
 --text:#1d1c1a;--text2:#5d5951;--text3:#8f8a80;
 --accent:#9b2226;--accent-bg:#f7ebea;
 --ok:#24744a;--ok-bg:#e6f2ea;--warn:#946200;--warn-bg:#fbf1da;--bad:#b42318;--bad-bg:#fcebe9;
 --r:12px;--shadow:0 1px 2px rgba(28,24,18,.05),0 0 0 1px var(--line);
 --sans:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Pretendard","Segoe UI",sans-serif;
 --mono:ui-monospace,"SF Mono",Menlo,monospace}
@media (prefers-color-scheme:dark){:root{
 --bg:#121110;--surface:#1b1a18;--surface2:#232220;--line:#2d2b28;--line2:#3b3935;
 --text:#ecebe7;--text2:#b4b0a7;--text3:#837f77;
 --accent:#e8806f;--accent-bg:#3a201c;
 --ok:#71c595;--ok-bg:#15291d;--warn:#e3b452;--warn-bg:#2e2512;--bad:#f2897b;--bad-bg:#351a18;
 --shadow:0 0 0 1px var(--line)}}
*{box-sizing:border-box}[hidden]{display:none!important}
html,body{margin:0;background:var(--bg);color:var(--text);font:14.5px/1.55 var(--sans);-webkit-font-smoothing:antialiased}
a{color:inherit}
button{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.app{display:grid;grid-template-columns:236px minmax(0,1fr);min-height:100vh}
aside{position:sticky;top:0;height:100vh;overflow-y:auto;padding:22px 14px;border-right:1px solid var(--line);display:flex;flex-direction:column;gap:22px}
.brand{display:flex;gap:10px;align-items:center;padding:0 8px}
.mark{width:34px;height:34px;border-radius:9px;background:var(--text);color:var(--bg);display:grid;place-items:center;font:700 15px Georgia,serif;letter-spacing:-.02em}
.brand b{display:block;font-size:15px;letter-spacing:-.01em}.brand small{color:var(--text3);font-size:12px}
nav{display:flex;flex-direction:column;gap:2px}
nav button{display:flex;align-items:center;gap:10px;border:0;background:none;padding:8px 10px;border-radius:8px;color:var(--text2);font-weight:500;cursor:pointer;text-align:left;white-space:nowrap}
nav button:hover{background:var(--surface2);color:var(--text)}
nav button[aria-selected=true]{background:var(--surface);color:var(--text);box-shadow:var(--shadow);font-weight:600}
nav svg{width:17px;height:17px;flex:none}
.subh{font-size:13px;margin:16px 0 8px;color:var(--text2)}.subh:first-of-type{margin-top:0}
.navtoggle{display:flex;justify-content:space-between;align-items:center;width:100%;border:0;background:none;padding:0 10px 4px;font-size:11px;font-weight:700;letter-spacing:.06em;color:var(--text3);cursor:pointer}
.navtoggle:hover{color:var(--text)}.navcount{font-variant-numeric:tabular-nums}
.helpcard{margin-top:14px;border-left:3px solid var(--accent)}
.failbox{margin:0 0 10px;max-height:180px;overflow:auto;color:var(--bad)}
.answer{margin-top:12px;background:var(--surface2);border-radius:9px;padding:12px 14px}
.answer .ab code{font:12.5px var(--mono);background:var(--surface);border-radius:4px;padding:1px 5px}
.answer .ah{font-size:12px;font-weight:600;color:var(--text3);margin-bottom:6px}.answer .ab{white-space:pre-wrap;font-size:13.5px;line-height:1.65}
.opt{margin-left:auto;font-size:10.5px;color:var(--text3);border:1px solid var(--line);border-radius:5px;padding:0 5px}
.navsub{font-size:11px;font-weight:600;color:var(--text3);padding:8px 10px 2px 14px}nav button.sub{margin-left:10px;width:calc(100% - 10px)}
.navh{font-size:11px;font-weight:700;letter-spacing:.06em;color:var(--text3);padding:16px 10px 4px}.navh:first-child{padding-top:0}
.num{width:20px;height:20px;border-radius:50%;display:grid;place-items:center;font-size:11px;font-weight:700;background:var(--surface2);color:var(--text2);flex:none}
.num.ok{background:var(--ok-bg);color:var(--ok)}nav button.locked .num{background:none;font-size:11px}nav button.locked{color:var(--text3)}nav button.locked .num{opacity:.55}
.kick{font-size:12px;font-weight:600;color:var(--accent);margin-bottom:4px}
.stepnav{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-top:22px;padding-top:18px;border-top:1px solid var(--line)}
.nxwrap{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-left:auto}.nxhint{color:var(--text3);font-size:12.5px}
.lockcard{text-align:center;padding:40px 20px}.lockico{font-size:28px;margin-bottom:8px}
.lirow{width:100%;border:0;background:none;text-align:left;cursor:pointer;font:inherit;color:inherit}.lirow:hover .t{text-decoration:underline}
.banner a{color:inherit;font-weight:700}
.side-foot{margin-top:auto;padding:0 8px;font-size:12px;color:var(--text3)}
.side-foot a{display:inline-flex;gap:6px;align-items:center;color:var(--text2);text-decoration:none;font-weight:500}
.side-foot a:hover{color:var(--text)}
main{padding:34px 44px 120px;max-width:1040px;width:100%}
.head{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;margin-bottom:24px;flex-wrap:wrap}
.head h1{margin:0;font-size:24px;letter-spacing:-.02em}
.head p{margin:4px 0 0;color:var(--text2)}
.banner{background:var(--warn-bg);color:var(--warn);border-radius:10px;padding:10px 14px;margin-bottom:18px;font-weight:500}
.grid{display:grid;gap:14px}.g4{grid-template-columns:repeat(4,minmax(0,1fr))}.g2{grid-template-columns:repeat(2,minmax(0,1fr))}
.card{background:var(--surface);border-radius:var(--r);box-shadow:var(--shadow);padding:20px}
.card h2{margin:0;font-size:15px;letter-spacing:-.01em}
.card .desc{margin:3px 0 0;color:var(--text3);font-size:13px}
.card-h{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:16px}
.stat .k{font-size:12.5px;color:var(--text3);font-weight:500}
.stat .v{font-size:22px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:650;letter-spacing:-.02em;margin-top:6px;font-variant-numeric:tabular-nums}
.stat .s{font-size:12.5px;color:var(--text2);margin-top:2px}
.badge{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:3px 9px;border-radius:99px;background:var(--surface2);color:var(--text2);white-space:nowrap}
.badge::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.badge.ok{background:var(--ok-bg);color:var(--ok)}.badge.warn{background:var(--warn-bg);color:var(--warn)}.badge.bad{background:var(--bad-bg);color:var(--bad)}
.badge.plain::before{display:none}
.list{display:flex;flex-direction:column}
.li{display:flex;align-items:center;gap:12px;padding:11px 0;border-top:1px solid var(--line)}
.li:first-child{border-top:0;padding-top:0}.li .grow{flex:1;min-width:0}
.li .t{font-weight:550}.li .m{color:var(--text3);font-size:13px}
.ico{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;flex:none;font-size:12px;font-weight:700}
.ico.ok{background:var(--ok-bg);color:var(--ok)}.ico.bad{background:var(--bad-bg);color:var(--bad)}.ico.warn{background:var(--warn-bg);color:var(--warn)}
/* 폼 */
.sec{display:grid;grid-template-columns:220px minmax(0,1fr);gap:24px;padding:22px 0;border-top:1px solid var(--line)}
.sec:first-of-type{border-top:0;padding-top:4px}
.sec>div{min-width:0}.sec h3{margin:0;font-size:14.5px}.sec .desc{margin:4px 0 0;color:var(--text3);font-size:13px}
.f{margin-bottom:14px}.f:last-child{margin-bottom:0}
.f label{display:block;font-size:13px;font-weight:600;margin-bottom:6px;color:var(--text)}
.f .help{font-size:12.5px;color:var(--text3);margin-top:5px}
input,textarea,select{width:100%;font:inherit;font-size:14px;color:var(--text);background:var(--surface);border:1px solid var(--line2);border-radius:8px;padding:8px 11px;transition:border-color .15s,box-shadow .15s}
input:focus,textarea:focus{outline:0;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-bg)}
.fgrid{display:grid;grid-template-columns:minmax(220px,290px) minmax(0,1fr);gap:14px;align-items:start}
.fgrid .flist{max-height:calc(100vh - 170px);overflow:auto}.fgrid .li{cursor:pointer;text-align:left;width:100%;background:none;border:0;font:inherit;color:inherit}
.fgrid .li.on{background:var(--accent-bg)}.fpath{font:12px var(--mono);color:var(--text2);word-break:break-all}
.fedit textarea{width:100%;min-height:calc(100vh - 330px)}
@media (max-width:860px){.fgrid{grid-template-columns:1fr}.fgrid .flist{max-height:none}}
textarea{font-family:var(--mono);font-size:13px;line-height:1.6;min-height:110px;resize:vertical}
.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.chips{display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:6px;border:1px solid var(--line2);border-radius:8px;background:var(--surface);cursor:text;min-height:42px}
.chips:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-bg)}
.chip{display:inline-flex;align-items:center;gap:4px;background:var(--surface2);border-radius:6px;padding:3px 4px 3px 9px;font-size:13px;font-weight:500}
.chip button{border:0;background:none;cursor:pointer;color:var(--text3);width:20px;height:20px;border-radius:4px;line-height:1;font-size:15px}
.chip button:hover{background:var(--line);color:var(--text)}
.chips input{flex:1;min-width:160px;border:0;box-shadow:none;padding:4px 6px;background:none}
.seg{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;background:var(--surface2);padding:4px;border-radius:10px}
.seg label{position:relative;margin:0;cursor:pointer;border-radius:7px;padding:9px 10px;text-align:center;font-weight:550;color:var(--text2);font-size:13px;line-height:1.3}
.seg label small{display:block;font-weight:400;color:var(--text3);font-size:11.5px;margin-top:2px}
.seg input{position:absolute;inset:0;width:auto;opacity:0;pointer-events:none}
.seg label:has(input:checked){background:var(--surface);color:var(--text);box-shadow:var(--shadow)}
.seg label:has(input:focus-visible){outline:2px solid var(--accent)}
.result{margin-top:12px;border-radius:9px;padding:11px 13px;font-size:13.5px;display:flex;gap:10px;align-items:flex-start}
.mini{background:var(--surface2);border-radius:9px;padding:10px 13px;font-size:12.5px;line-height:1.55;color:var(--text2);margin-bottom:14px}
.mini p{margin:0 0 4px}.mini p:last-child{margin:0}.mini b{color:var(--text)}
.sug{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.sug button{border:1px dashed var(--line2);background:none;border-radius:6px;padding:3px 9px;font-size:12.5px;color:var(--text2);cursor:pointer}
.sug button:hover{border-style:solid;color:var(--text)}
.chk{display:flex;gap:8px;align-items:center;margin-top:12px;font-size:13px;color:var(--text2);cursor:pointer}
.chk input{width:auto;margin:0}.savenote{color:var(--warn);font-size:12.5px;font-weight:600}
.zwrap{display:grid;grid-template-columns:230px minmax(0,1fr);gap:16px;align-items:start}
.zside{position:sticky;top:20px;display:flex;flex-direction:column;gap:2px;max-height:calc(100vh - 140px);overflow:auto}
.zc{display:flex;justify-content:space-between;gap:8px;width:100%;border:0;background:none;border-radius:7px;padding:7px 10px;text-align:left;font-size:13.5px;color:var(--text2);cursor:pointer}
.zc:hover{background:var(--surface2);color:var(--text)}.zc[aria-current=true]{background:var(--surface);box-shadow:var(--shadow);color:var(--text);font-weight:600}
.zc small{color:var(--text3);font-variant-numeric:tabular-nums}
.zcount{color:var(--text3);font-size:12.5px;margin:10px 0 2px}
.zitem{padding:14px 0;border-top:1px solid var(--line)}.zitem:first-of-type{border-top:0}
.zitem h3{margin:0;font-size:15px;line-height:1.4;letter-spacing:-.01em}.zmeta{color:var(--text3);font-size:12.5px;margin-top:3px}
.zitem .tools{margin-top:8px}.zlinks{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:8px;font-size:12.5px}
.zlinks a,.linkbtn{color:var(--text2);text-decoration:underline;text-underline-offset:3px;text-decoration-color:var(--line2)}
.linkbtn{border:0;background:none;padding:0;font-size:12.5px;cursor:pointer}
.zabs{margin:8px 0 0;color:var(--text2);font-size:13px;line-height:1.6}.zchild{font-size:12.5px;margin-top:6px}
@media (max-width:760px){.zwrap{grid-template-columns:1fr}.zside{position:static;max-height:none;flex-direction:row;flex-wrap:wrap}.zc{width:auto}}
.guide{margin-top:12px;border:1px solid var(--line);border-radius:10px;padding:16px 18px;background:var(--surface)}
.guide h4{margin:0 0 4px;font-size:14px}.guide .why{color:var(--text2);font-size:13px;margin:0 0 12px}
.diag{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px}
.guide ol{margin:0;padding:0;list-style:none;counter-reset:g}
.guide li{counter-increment:g;position:relative;padding:0 0 14px 34px}
.guide li::before{content:counter(g);position:absolute;left:0;top:0;width:22px;height:22px;border-radius:50%;background:var(--text);color:var(--bg);display:grid;place-items:center;font-size:12px;font-weight:700}
.guide li b{display:block;font-size:13.5px;margin-bottom:2px}.guide li p{margin:0;color:var(--text2);font-size:13px}
.cmd{display:flex;align-items:center;gap:8px;margin-top:7px;background:var(--surface2);border-radius:8px;padding:6px 6px 6px 12px}
.cmd code{flex:1;min-width:0;font:13px var(--mono);overflow-x:auto;white-space:nowrap}
.cmd button{border:0;border-radius:6px;background:var(--surface);box-shadow:inset 0 0 0 1px var(--line2);padding:4px 10px;font-size:12px;font-weight:600;cursor:pointer}
.guide .foot{display:flex;gap:8px;flex-wrap:wrap;align-items:center;border-top:1px solid var(--line);padding-top:14px;margin-top:2px}
.guide .foot span{color:var(--text3);font-size:12.5px}
.result.ok{background:var(--ok-bg);color:var(--ok)}.result.bad{background:var(--bad-bg);color:var(--bad)}.result.wait{background:var(--surface2);color:var(--text2)}
.result .sub{color:var(--text2);font-size:12.5px;margin-top:2px;word-break:break-all}
.btn{display:inline-flex;align-items:center;gap:7px;border:0;border-radius:8px;padding:8px 14px;font-weight:600;font-size:13.5px;cursor:pointer;background:var(--text);color:var(--bg);transition:opacity .15s}
.btn:hover{opacity:.88}.btn:disabled{opacity:.45;cursor:default}
.btn.ghost{background:var(--surface);color:var(--text);box-shadow:inset 0 0 0 1px var(--line2)}
.btn.ghost:hover{background:var(--surface2);opacity:1}
.btn.primary{background:var(--accent);color:var(--bg);padding:10px 18px;font-size:14.5px}
.todo{background:var(--accent-bg);border:2px solid var(--accent);border-radius:var(--r);padding:16px 20px;margin-bottom:16px}
.todo-h{font-weight:700;color:var(--accent);margin-bottom:10px}
.todo ol{list-style:none;margin:0 0 14px;padding:0;display:grid;gap:7px}
.todo li{display:flex;gap:9px;align-items:center;color:var(--text2)}.todo li.cur{color:var(--text);font-weight:700}.todo li.dn{color:var(--ok)}
.tnum{width:22px;height:22px;border-radius:50%;display:inline-grid;place-items:center;font-size:12px;background:var(--surface);flex:none}
.todo li.cur .tnum{background:var(--accent);color:var(--bg)}.todo li.dn .tnum{background:var(--ok-bg);color:var(--ok)}
.card.focus{box-shadow:0 0 0 2px var(--accent),var(--shadow)}
@keyframes flash{0%{box-shadow:0 0 0 7px var(--accent)}100%{box-shadow:0 0 0 2px var(--accent),var(--shadow)}}
.card.flash{animation:flash 1.2s ease-out}
.agentfold{margin-bottom:14px}.agentfold>summary{cursor:pointer;font-size:13px;color:var(--text2);padding:4px 2px}.agentfold[open]>summary{margin-bottom:8px}
.savebar{position:sticky;bottom:16px;margin-top:20px;display:flex;align-items:center;justify-content:space-between;gap:12px;background:var(--surface);box-shadow:0 8px 24px rgba(20,16,10,.1),0 0 0 1px var(--line);border-radius:12px;padding:10px 10px 10px 16px}
.savebar span{color:var(--text3);font-size:13px}.savebar.dirty span{color:var(--warn);font-weight:600}
.tools{display:flex;flex-wrap:wrap;gap:5px;margin-top:12px}
.tool{font:12px var(--mono);background:var(--surface2);color:var(--text2);border-radius:5px;padding:2px 7px}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{font-size:12px;font-weight:600;color:var(--text3);text-align:left;padding:0 10px 8px}
td{padding:10px;border-top:1px solid var(--line);vertical-align:top}
td:first-child,th:first-child{padding-left:0}td:last-child,th:last-child{padding-right:0}
td a{text-decoration:none;font-weight:550}td a:hover{text-decoration:underline}
.err{color:var(--text3);font-size:12px;margin-top:2px}
.metrics{display:flex;flex-wrap:wrap;gap:6px 18px;color:var(--text2);font-size:13px;margin:-6px 0 14px}
.metrics b{color:var(--text);font-variant-numeric:tabular-nums}
details{margin-top:14px}summary{cursor:pointer;color:var(--text2);font-weight:550;font-size:13px}
pre{white-space:pre-wrap;word-break:break-word;background:var(--surface2);border-radius:8px;padding:12px;font:12.5px/1.6 var(--mono);margin:10px 0 0}
.empty{text-align:center;padding:48px 20px;color:var(--text3)}
.row-actions{display:flex;gap:8px;flex-wrap:wrap}
#toast{position:fixed;bottom:22px;left:50%;transform:translate(-50%,20px);opacity:0;transition:all .2s;background:var(--text);color:var(--bg);padding:10px 16px;border-radius:10px;font-weight:550;pointer-events:none;box-shadow:0 8px 24px rgba(0,0,0,.18);max-width:calc(100vw - 32px)}
#toast.on{opacity:1;transform:translate(-50%,0)}
.spin{width:14px;height:14px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:s .7s linear infinite;flex:none;margin-top:2px}
@keyframes s{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation-duration:2s!important}}
@media (max-width:1100px){.g4{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:980px){.sec{grid-template-columns:1fr;gap:12px}}
@media (max-width:760px){
 .app{grid-template-columns:minmax(0,1fr)}
 aside{position:sticky;z-index:5;height:auto;flex-direction:row;align-items:center;gap:12px;padding:10px 16px;border-right:0;border-bottom:1px solid var(--line);background:var(--bg);overflow-x:auto}
 .brand div,.side-foot,.navh,.navsub{display:none}.brand{padding:0}
 nav{flex-direction:row}nav button{padding:7px 10px}nav svg{display:none}
 main{padding:22px 16px 110px}.g2,.two{grid-template-columns:1fr}
 table thead{display:none}table,tbody,tr,td{display:block;width:100%}tr{padding:10px 0;border-top:1px solid var(--line)}td{border:0;padding:2px 0}}
</style></head><body>
<div class="app"><aside>
 <div class="brand"><span class="mark">DP</span><div><b>매일 논문</b><small>The Daily Paper 관리</small></div></div>
 <nav role="tablist" aria-label="메뉴"></nav>
 <div class="side-foot" id="foot"></div>
</aside><main id="main"></main></div>
<div id="toast" role="status" aria-live="polite"></div>
<script>
const ICONS={
 '현황':'<path d="M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z"/>',
 '실행 기록':'<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
 '담당 에이전트':'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
 '파일':'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h5"/>',
 'DB 합치기':'<circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M6 21V9a9 9 0 0 0 9 9"/>',
 '조테로':'<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>'};
const icon=n=>{const s=document.createElement('span');s.innerHTML=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[n]}</svg>`;return s.firstChild};
let S,cur=null,dirty=false;
const $=s=>document.querySelector(s);
const el=(t,a={},...kids)=>{const e=document.createElement(t);for(const[k,v]of Object.entries(a))k in e?e[k]=v:e.setAttribute(k,v);e.append(...kids.filter(k=>k!==null&&k!==false&&k!==undefined));return e};
const toast=m=>{const t=$('#toast');t.textContent=m;t.classList.add('on');clearTimeout(t._h);t._h=setTimeout(()=>t.classList.remove('on'),3200)};
const post=(u,b)=>fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}).then(r=>r.json());
async function save(kind,text,name){const r=await post('/api/save',{kind,name,text});toast((r.ok?'저장했습니다 · ':'저장 못 함 · ')+r.msg);if(r.ok){dirty=false;await load()}return r.ok}
const badge=(cls,txt)=>el('span',{className:'badge '+cls},txt);
const card=(title,desc,...kids)=>el('section',{className:'card'},el('div',{className:'card-h'},el('div',{},el('h2',{},title),desc?el('p',{className:'desc'},desc):null)),...kids);
const WD=['일','월','화','수','목','금','토'];
const longDate=d=>{const x=new Date(d+'T00:00:00');return `${x.getMonth()+1}월 ${x.getDate()}일 ${WD[x.getDay()]}요일`};
function dayStatus(d){return d.notion?['ok','노션 완료']:d.stopped?['bad','루프 멈춤']:d.fails.length?['bad','판정 실패 '+d.fails.length]:['warn','노션 미업로드']}
const toolName=t=>t.replace(/^mcp__.*?__(?=[^_])/,'');  // mcp__claude_ai_Exa__web_search_exa → web_search_exa

// 메뉴는 이야기 순서: 처음 설정(단계마다 앞 단계가 끝나야 열림) → 매일 쓰기 → 번외
const STEPS=[
 {k:'Claude Code 로그인',d:'먼저 이 컴퓨터의 Claude Code에 로그인합니다. 모든 담당 에이전트가 Claude Code에서 일합니다. 다음 단계부터 막히면 여기서 Claude에게 바로 물어볼 수 있습니다.',done:()=>!!(S.checks.claude&&S.checks.claude.ok),
  fail:()=>''},
 {k:'기본 점검',d:'파이썬·작업공간 폴더·판정 훅처럼 모든 담당이 함께 쓰는 것을 확인합니다.',done:()=>!!(S.checks.기본&&S.checks.기본.ok),
  fail:()=>badLines(S.checks.기본&&S.checks.기본.out)},
 {k:'논문 찾기',agent:'paper-scout',d:'paper-scout가 OpenAlex·Exa에서 찾을 영어 키워드를 정하고, 시험 검색으로 실제로 찾아지는지 확인합니다.',done:()=>testOk('paper-scout',S.scout),
  fail:()=>!S.scout.키워드.length?'검색 키워드가 하나도 없습니다.':testWhy('paper-scout',S.scout)},
 {k:'조테로 저장',agent:'zotero-keeper',optional:true,d:'선택 단계. zotero-keeper가 그날 고른 논문을 조테로 컬렉션에 저장합니다. 쓰지 않으려면 "사용 안 함"으로 두고 넘어가면 됩니다.',
  done:()=>!S.zotero.사용||testOk('zotero-keeper',S.zotero),fail:()=>testWhy('zotero-keeper',S.zotero)},
 {k:'요약',agent:'paper-reader',optional:true,d:'선택 단계. paper-reader가 PDF를 받은 논문을 정해진 양식으로 요약하고 판정 기준으로 점검합니다. 쓰지 않으려면 "사용 안 함"으로 두면 노션에는 초록만 올라갑니다.',
  done:()=>!S.reader.사용||testOk('paper-reader',S.reader),fail:()=>testWhy('paper-reader',S.reader)},
 {k:'넣으면 안 되는 자료',agent:'privacy-guard',d:'노션에 올리기 전에 privacy-guard가 점검할 자료 종류를 정하고, 시험으로 실제 결과는 통과시키고 가짜 민감 자료는 막는지 확인합니다.',done:()=>infoFilled()&&testOk('privacy-guard',{}),
  fail:()=>!infoFilled()?'설정/연구자_정보.md의 "이 폴더에 넣으면 안 되는 자료" 칸이 비어 있습니다.':testWhy('privacy-guard',{})},
 {k:'노션 올리기',agent:'notion-publisher',d:'필수 단계. notion-publisher가 논문을 쌓을 노션 페이지를 꾸미고(페이지 하나만 주면 아카이브와 표지를 만듭니다), 시험으로 실제 연결을 확인합니다.',
  done:()=>!!S.notion.notion_db_url&&testOk('notion-publisher',S.notion),
  fail:()=>!S.notion.notion_db_url?'아직 노션 페이지를 정하지 않았습니다. 아래에 페이지 주소를 넣고 "새로 시작"을 누르세요.':testWhy('notion-publisher',S.notion)},
 {k:'마무리 점검',d:'모든 담당의 설정을 한 번에 확인합니다. 통과하면 매일 논문을 시작할 수 있습니다.',done:()=>!!(S.checks.에이전트&&S.checks.에이전트.ok),
  fail:()=>badLines(S.checks.에이전트&&S.checks.에이전트.out)}];
const unset=n=>S.agents.some(a=>a.name===n&&a.unset);
const AGENT_GROUP='에이전트 설정 및 점검';  // 처음 설정 안의 묶음: agent가 있는 단계(담당 순서)
// 담당 시험: 통과했고, 시험한 뒤 그 담당의 설정(키워드)이 바뀌지 않았어야 끝
// keys: 시험 결과에 같이 적힌 설정 칸(paper-scout는 키워드, zotero-keeper는 컬렉션). 바뀌면 다시 시험
const FRESH_KEYS={'paper-scout':['키워드'],'zotero-keeper':['컬렉션'],'paper-reader':[],'privacy-guard':[],'notion-publisher':['notion_url','notion_db_url']};
const infoFilled=()=>{const m=S.info.match(NOGO);return !!(m&&m[1].trim())};
// 시험 카드에 담당마다 붙이는 한 줄: 밖에 실제로 쓰는 담당은 무엇을 쓰는지 알린다
const TEST_NOTE={'zotero-keeper':"조테로에 '시험' 태그를 붙인 논문 한 편을 실제로 저장합니다(지워도 됩니다).",
 'notion-publisher':"노션 아카이브에 '[시험]'으로 시작하는 줄 한 편을 실제로 올립니다(지워도 됩니다). 표지는 바꾸지 않습니다.",
 'privacy-guard':'앞 담당의 실제 결과는 통과시키고, 일부러 넣은 가짜 민감 자료는 막는지 봅니다.'};
const testFresh=(n,cfg)=>{const r=S.tests[n];return !!r&&(FRESH_KEYS[n]||[]).every(k=>JSON.stringify(r[k])===JSON.stringify(cfg[k]))};
const testOk=(n,cfg)=>!!(S.tests[n]&&S.tests[n].통과)&&testFresh(n,cfg);
const testWhy=(n,cfg)=>{const r=S.tests[n];return !r?`아직 ${n} 시험을 하지 않았습니다. 아래 "시험 실행"을 누르세요.`:!testFresh(n,cfg)?'설정이 시험 뒤에 바뀌었습니다. 다시 시험하세요.'
 :!r.통과?'시험 실패:\n'+(r.항목||[]).filter(x=>!x.통과&&x.필수!==false).map(x=>`${x.이름}: ${x.설명||''}`).join('\n')+(r.제안?'\n제안: '+r.제안:''):''};
const badLines=out=>(out||'').split('\n').filter((l,i,a)=>/^(❌|⛔)/.test(l.trim())||(/^\s*→/.test(l)&&/^❌/.test((a[i-1]||'').trim()))).join('\n');
const DAILY=['현황','실행 기록','조테로'],EXTRA=['파일','담당 에이전트','DB 합치기'],ALWAYS_OPEN=['파일'];  // 파일은 처음 설정 중에도 연다(스킬을 고치며 설정)
const stepIdx=k=>STEPS.findIndex(s=>s.k===k);
const lockedBy=k=>{const i=stepIdx(k);const s=i<0?null:STEPS.slice(0,i).find(s=>!s.done());return s?s.k:null};
const nextTodo=()=>(STEPS.find(s=>!s.done())||{}).k;  // 처음으로 안 끝난 단계. 그 뒤 단계는 모두 잠긴다
const saveCfg=patch=>save('config',JSON.stringify({...S.config,...patch}));
const mark=()=>{dirty=true};
const inp=(id,val,type='text',ph='')=>el('input',{id,type,value:val??'',placeholder:ph,oninput:mark});
const f=(lab,ctl,help)=>el('div',{className:'f'},el('label',{htmlFor:ctl.id||''},lab),ctl,help?el('div',{className:'help'},help):null);
const saveRow=(fn,label='저장')=>el('div',{className:'row-actions',style:'margin-top:16px'},el('button',{className:'btn',onclick:fn},label));

// 설정점검 결과(✅/❌/⚠️ 줄)를 체크리스트로
function checkList(out){const rows=[];
 (out||'').split('\n').forEach(line=>{const t=line.trim();if(!t)return;
  if(t.startsWith('→')&&rows.length){rows[rows.length-1].fix=t.slice(1).trim();return}
  const st=t.startsWith('✅')?'ok':t.startsWith('❌')?'bad':t.startsWith('⚠')?'warn':t.startsWith('⛔')?'bad':null;
  rows.push({st,text:st?t.replace(/^(✅|❌|⚠️?|⛔)\s*/,''):t})});
 return el('div',{className:'list'},...rows.map(x=>x.st?el('div',{className:'li'},el('span',{className:'ico '+x.st},x.st==='ok'?'✓':'!'),
  el('div',{className:'grow'},el('div',{className:'t'},x.text),x.fix?el('div',{className:'m'},x.fix):null)):el('div',{className:'li'},el('div',{className:'grow m'},x.text))))}
// Claude 답의 **굵게**와 `코드`만 살린다(나머지는 글자 그대로, HTML로 해석하지 않음)
const mdLite=t=>t.split(/(\*\*[^*]+\*\*|`[^`]+`)/).map(x=>x.startsWith('**')&&x.endsWith('**')?el('b',{},x.slice(2,-2)):x.startsWith('`')&&x.endsWith('`')&&x.length>1?el('code',{},x.slice(1,-1)):x);
// 처음 설정에서 막히면 실패 내용을 이 컴퓨터의 Claude Code에 보내 고치는 방법을 묻는다
function helpCard(step,detail){const q=el('textarea',{rows:2,placeholder:'더 궁금한 점이 있으면 적어 주세요(선택)'}),ans=el('div');
 const ask=el('button',{className:'btn',type:'button',onclick:async()=>{ask.disabled=true;
  ans.replaceChildren(el('div',{className:'result wait'},el('span',{className:'spin'}),el('div',{},'Claude가 읽고 답하는 중… (10~40초)')));
  const r=await post('/api/help',{step,detail,question:q.value.trim()}).catch(e=>({ok:false,error:String(e)}));ask.disabled=false;
  ans.replaceChildren(r.ok?el('div',{className:'answer'},el('div',{className:'ah'},`Claude의 답 · ${r.secs}초`),el('div',{className:'ab'},...mdLite(r.answer)))
   :el('div',{className:'result bad'},el('span',{},'!'),el('div',{},el('div',{},r.hint||'Claude에게 묻지 못했습니다. 1단계 Claude Code 로그인을 확인하세요.'),el('div',{className:'sub'},r.error||''))))}},'Claude에게 물어보기');
 return el('section',{className:'card helpcard'},el('div',{className:'card-h'},el('div',{},el('h2',{},'막혔나요? Claude에게 도움 받기'),
   el('p',{className:'desc'},'아래 실패 내용을 이 컴퓨터의 Claude Code에 보내 고치는 방법을 묻습니다. Claude는 파일을 고치지 않고 방법만 알려 줍니다.'))),
  el('pre',{className:'failbox'},detail||'(실패 내용 없음)'),q,el('div',{className:'row-actions',style:'margin-top:10px'},ask),ans)}

function checkCard(mode,title,auto){const box=el('div'),btn=el('button',{className:'btn ghost',type:'button'},'다시 확인');
 const run=async()=>{btn.disabled=true;box.replaceChildren(el('div',{className:'result wait'},el('span',{className:'spin'}),'확인 중…'));
  await post('/api/check',{mode});await load()};
 btn.onclick=run;const r=S.checks[mode||'에이전트'];
 if(r)box.replaceChildren(checkList(r.out));else if(auto)queueMicrotask(run);
 return card(title,r?`${r.at}에 확인`:'',box,el('div',{className:'row-actions',style:'margin-top:14px'},btn))}

const waitBox=t=>el('div',{className:'result wait'},el('span',{className:'spin'}),el('div',{},t));
const badBox=t=>el('div',{className:'result bad'},el('span',{},'!'),el('div',{},t));

// 원본 저장소에서 열렸을 때: 누르면 workspace/를 만들고(이 클릭이 승인) 대시보드가 그쪽으로 다시 뜬다
function wsCard(){const box=el('div'),btn=el('button',{className:'btn',type:'button'},'작업공간 만들기');
 btn.onclick=async()=>{btn.disabled=true;box.replaceChildren(waitBox('작업공간을 만드는 중…'));
  const r=await post('/api/workspace',{}).catch(()=>({ok:false,msg:'대시보드에 연결하지 못했습니다'}));
  if(!r.ok){btn.disabled=false;return box.replaceChildren(badBox(r.msg))}
  box.replaceChildren(waitBox(`만들었습니다 · ${r.msg} 쪽으로 대시보드를 다시 여는 중…`));
  for(let i=0;i<40;i++){await new Promise(f=>setTimeout(f,500));
   const s=await fetch('/api/state').then(x=>x.json()).catch(()=>null);if(s&&!s.readonly)return location.reload()}
  box.replaceChildren(badBox('다시 열리지 않았습니다. 터미널에서 run.sh(Windows는 run.bat)를 다시 실행하세요.'))};
 return card('작업공간 만들기',`지금은 원본 저장소(${S.root})에서 열려 있어 설정을 저장할 수 없습니다.`,
  el('div',{className:'mini'},el('p',{},'누르면 이 저장소 안에 workspace/ 폴더를 만들고 파일을 복사합니다(.git과 매일논문 결과는 빼고). 키워드·노션 주소 같은 내 설정은 그 폴더에만 저장되고, .gitignore에 들어 있어 git에 올라가지 않습니다.'),
   el('p',{},'만든 뒤에는 대시보드가 작업공간 쪽으로 저절로 다시 열립니다. 다음부터는 run.sh(Windows는 run.bat)가 작업공간을 바로 엽니다.')),
  box,el('div',{className:'row-actions',style:'margin-top:14px'},btn))}

// 담당 에이전트 카드(이름·모델·도구·커넥터 상태, 파일 편집)
function agentCard(a){const ta=el('textarea',{value:a.text,rows:18});const ed=el('div',{hidden:true},ta,
  el('div',{className:'row-actions',style:'margin-top:10px'},el('button',{className:'btn',onclick:()=>save('agent',ta.value,a.name)},'저장'),el('button',{className:'btn ghost',onclick:()=>{ta.value=a.text;ed.hidden=true}},'취소')));
 return el('section',{className:'card'},el('div',{className:'card-h'},el('div',{},el('h2',{},a.name),el('p',{className:'desc'},(a.description||'').split(/(?<=다\.)\s/)[0])),
   el('div',{style:'display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end'},badge('plain',a.model||'기본 모델'),a.unset?badge('warn','커넥터 빈칸'):badge('ok','연결됨'))),
  el('div',{className:'tools'},...(a.tools||'').split(',').map(t=>el('span',{className:'tool',title:t.trim()},toolName(t.trim())))),
  el('div',{style:'margin-top:14px'},el('button',{className:'btn ghost',onclick:()=>{ed.hidden=!ed.hidden}},'파일 편집')),ed)}
const fillTask=uns=>claudeTask('설정해 줘',`빈칸(${uns.map(a=>a.name).join(', ')})을 그 세션의 노션·Exa 커넥터 이름으로 채웁니다. 커넥터가 없으면 claude.ai → 설정 → 커넥터에서 먼저 연결하라고 안내합니다.`);
// 처음 설정의 담당 단계: 맨 위에 그 담당 카드(빈칸이면 채우는 방법도)
const withAgent=(n,kids)=>{const a=S.agents.find(x=>x.name===n);if(!a)return kids;
 return [...(a.unset?[fillTask([a]),el('div',{style:'height:14px'})]:[]),
  el('details',{className:'agentfold'},el('summary',{},`담당 정보 보기 · ${a.name} (모델·도구·파일 편집)`),agentCard(a)),...kids]};
// 처음 설정 단계마다 맨 위의 '지금 할 일': [할 일, 끝났나, 그 일을 하는 카드의 제목(일부)]. 지금 할 것 하나만 눈에 띄게
const TODOS={
 'Claude Code 로그인':()=>[['Claude Code에 로그인되어 있는지 확인',!!(S.checks.claude&&S.checks.claude.ok),'Claude Code']],
 '기본 점검':()=>[['아래 점검 결과에 ❌가 없는지 확인',!!(S.checks.기본&&S.checks.기본.ok),'모든 담당이 함께 쓰는 것']],
 '논문 찾기':()=>[['검색 키워드를 넣고 저장',S.scout.키워드.length>0,'paper-scout 설정'],['시험 실행을 눌러 통과 확인',testOk('paper-scout',S.scout),'paper-scout 시험']],
 '조테로 저장':()=>[['조테로를 쓸지 정하기 (안 쓰면 그대로 다음 단계)',true,'zotero-keeper 설정'],...(S.zotero.사용?[['시험 실행을 눌러 통과 확인',testOk('zotero-keeper',S.zotero),'zotero-keeper 시험']]:[])],
 '요약':()=>[['요약을 쓸지 정하기 (안 쓰면 그대로 다음 단계)',true,'paper-reader 설정'],...(S.reader.사용?[['시험 실행을 눌러 통과 확인',testOk('paper-reader',S.reader),'paper-reader 시험']]:[])],
 '넣으면 안 되는 자료':()=>[['넣으면 안 되는 자료를 적고 저장',infoFilled(),'넣으면 안 되는 자료'],['시험 실행을 눌러 통과 확인',testOk('privacy-guard',{}),'privacy-guard 시험']],
 '노션 올리기':()=>[['노션 페이지 주소를 넣고 "새로 시작"',!!S.notion.notion_db_url,'새로 시작'],['시험 실행을 눌러 통과 확인',testOk('notion-publisher',S.notion),'notion-publisher 시험']],
 '마무리 점검':()=>[['아래 확인 결과에 ❌가 없는지 확인',!!(S.checks.에이전트&&S.checks.에이전트.ok),'모든 설정']]};
function todoCard(k,nx){const items=(TODOS[k]||(()=>[]))(),cur=items.findIndex(x=>!x[1]);
 const jump=h=>{const c=[...$('#main').querySelectorAll('section.card')].find(c=>((c.querySelector('h2')||{}).textContent||'').includes(h));
  if(c){c.scrollIntoView({behavior:'smooth',block:'start'});c.classList.remove('flash');void c.offsetWidth;c.classList.add('flash')}};
 return el('section',{className:'todo'},el('div',{className:'todo-h'},'지금 할 일'),
  el('ol',{},...items.map(([t,d],j)=>el('li',{className:d?'dn':j===cur?'cur':''},el('span',{className:'tnum'},d?'✓':String(j+1)),t))),
  cur<0?el('button',{className:'btn primary',onclick:()=>{if(nx==='현황')SETUP_OPEN=false;go(nx)}},`다 했습니다 · 다음: ${nx} →`)
   :el('button',{className:'btn primary',onclick:()=>jump(items[cur][2])},`${items[cur][0]} ↓`))}
// 담당 시험 카드: 대시보드가 이 컴퓨터의 Claude Code를 작업공간에서 띄워 그 담당에게 '시험'을 맡긴다.
// 담당 파일의 tools만 허용하고, 진행(도구 호출)과 담당의 보고, 담당이 쓴 결과.json을 보여 준다
const TESTPOLL={};
function testCard(name,fresh){const box=el('div'),btn=el('button',{className:'btn primary',type:'button'},'▶ 시험 실행');let was=false;
 const row=x=>el('div',{className:'li'},el('span',{className:'ico '+(x.통과?'ok':x.필수===false?'warn':'bad')},x.통과?'✓':'!'),
  el('div',{className:'grow'},el('div',{className:'t'},x.이름+(x.필수===false?' (선택)':'')),x.설명?el('div',{className:'m'},x.설명):null));
 const show=r=>{const res=r.result;btn.disabled=r.running;
  box.replaceChildren(...[r.running?waitBox(`${name}가 시험하는 중… ${r.secs}초 (보통 1~3분)`):'',
   res?el('div',{},el('div',{className:'result '+(res.통과?'ok':'bad')},el('span',{},res.통과?'✓':'!'),el('div',{},res.통과?'시험 통과':'시험 실패',el('div',{className:'sub'},res.시각||''))),
    el('div',{className:'list',style:'margin-top:10px'},...(res.항목||[]).map(row))):'',
   res&&!fresh?el('div',{className:'nxhint'},'설정이 시험 뒤에 바뀌었습니다. 다시 시험하세요.'):'',
   res&&res.제안?el('div',{className:'mini',style:'margin-top:10px'},el('p',{},'💡 '+res.제안)):'',
   res&&(res.제목||[]).length?el('details',{open:!res.통과,style:'margin-top:10px'},el('summary',{},`찾은 제목 ${res.제목.length}개 · 거름 ${res.제목.filter(x=>x.관계없음).length}`),
    el('table',{},el('thead',{},el('tr',{},...['키워드','출처','제목','거르기'].map(h=>el('th',{},h)))),el('tbody',{},...res.제목.map(x=>el('tr',{},el('td',{},x.키워드||''),el('td',{},x.출처||''),
     el('td',{},x.제목||''),el('td',{},x.관계없음?el('div',{},badge('bad','거름'),x.이유?el('div',{className:'m'},x.이유):null):badge('ok','남김'))))))):'',
   (r.steps||[]).length?el('details',{style:'margin-top:10px'},el('summary',{},`진행 ${r.steps.length}단계`),el('pre',{className:'failbox'},r.steps.join('\n'))):'',
   !r.running&&r.report?el('details',{open:!res,style:'margin-top:10px'},el('summary',{},'담당의 보고'),el('div',{className:'answer'},el('div',{className:'ab'},...mdLite(r.report)))):'',
   !r.running&&!res&&r.error?badBox(r.error):''].filter(Boolean));
  if(r.running){clearTimeout(TESTPOLL[name]);TESTPOLL[name]=setTimeout(poll,2000)}else if(was)load();was=r.running};
 const poll=async()=>{if(box.isConnected||!was)show(await fetch('/api/agent/test?name='+encodeURIComponent(name)).then(r=>r.json()))};
 btn.onclick=async()=>{btn.disabled=true;const r=await post('/api/agent/test',{name});if(!r.ok){toast(r.msg);btn.disabled=false;return}was=true;poll()};
 queueMicrotask(poll);
 const c=card(`${name} 시험`,`이 컴퓨터의 Claude Code로 ${name}를 불러 실제로 해 봅니다. ${TEST_NOTE[name]||''} 기록은 매일논문/시험/${name}/에 남고 그날 논문에는 섞이지 않습니다.`,
  el('div',{className:'row-actions',style:'margin-bottom:4px'},btn),box);
 if(!(S.tests[name]&&S.tests[name].통과&&fresh))c.classList.add('focus');  // 아직 통과 못 한 시험은 테두리로 눈에 띄게
 return c}
// 파일 메뉴: 위치·설명 목록과 편집기. 담당·스킬·규칙 글(.md)만 고칠 수 있고, 저장 전 원래 내용은 매일논문/파일백업/에 남는다
let FILESEL=null;
function filesPage(){const list=el('div',{className:'list'}),ed=el('div',{className:'fedit'});
 const open=async path=>{if(dirty&&!confirm('저장하지 않은 변경이 있습니다. 다른 파일을 열까요?'))return;dirty=false;FILESEL=path;
  [...list.querySelectorAll('.li')].forEach(b=>b.classList.toggle('on',b.dataset.path===path));
  ed.replaceChildren(waitBox('여는 중…'));const f=await fetch('/api/file?path='+encodeURIComponent(path)).then(r=>r.json());
  if(f.error)return ed.replaceChildren(badBox(f.error));
  const ro=!f.editable||S.readonly,ta=el('textarea',{value:f.text,readOnly:ro,spellcheck:false,oninput:mark});
  const saveBtn=el('button',{className:'btn',disabled:ro,onclick:async()=>{saveBtn.disabled=true;
   const r=await post('/api/save',{kind:'file',name:f.path,text:ta.value,mtime:f.mtime}).catch(e=>({ok:false,msg:String(e)}));
   toast((r.ok?'저장했습니다 · ':'저장 못 함 · ')+r.msg);saveBtn.disabled=false;if(r.ok){dirty=false;open(f.path)}}},'저장');
  ed.replaceChildren(card(f.path,f.desc,
   el('div',{style:'display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px'},badge('plain',f.group),badge(ro?'plain':'ok',!f.editable?'읽기만':S.readonly?'원본 저장소라 읽기만':'고칠 수 있음'),badge('plain',`${(f.size/1024).toFixed(1)} KB`)),
   ta,ro?'':el('div',{className:'row-actions',style:'margin-top:10px'},saveBtn,el('button',{className:'btn ghost',onclick:()=>{dirty=false;open(f.path)}},'되돌리기'),
    el('span',{className:'nxhint'},f.path.endsWith('SKILL.md')||f.path.startsWith('.claude/agents/')?"머리말(--- 사이)의 name은 그대로 두세요":''))))};
 fetch('/api/files').then(r=>r.json()).then(({files})=>{let g='';
  list.replaceChildren(...files.flatMap(f=>{const b=el('button',{className:'li'+(f.path===FILESEL?' on':''),onclick:()=>open(f.path)},
     el('div',{className:'grow'},el('div',{className:'t'},f.path.split('/').slice(f.path.endsWith('/SKILL.md')?-2:-1).join('/'),f.editable?'':el('small',{className:'opt'},'읽기')),el('div',{className:'fpath'},f.path),el('div',{className:'m'},f.desc)));
    b.dataset.path=f.path;const h=f.group!==g?[el('h3',{className:'subh',style:'margin:12px 8px 4px'},g=f.group)]:[];return [...h,b]}));
  open(FILESEL&&files.some(f=>f.path===FILESEL)?FILESEL:files[0].path)});
 return [el('div',{className:'fgrid'},card('파일','위치와 설명. 눌러서 열기',el('div',{className:'flist'},list)),ed)]}
const PAGES={
 'Claude Code 로그인':{r(){const d=S.checks.claude||{},again=el('button',{className:'btn ghost',type:'button',onclick:async()=>{again.disabled=true;await post('/api/claude',{});await load()}},'다시 확인');
  return [card('이 컴퓨터의 Claude Code',d.at?`${d.at}에 확인`:'',
   el('div',{className:'list'},
    el('div',{className:'li'},el('span',{className:'ico '+(d.path?'ok':'bad')},d.path?'✓':'!'),el('div',{className:'grow'},el('div',{className:'t'},d.path?'설치됨':'설치 안 됨'),el('div',{className:'m'},d.path?(d.version||d.path):'claude 명령을 찾지 못했습니다'))),
    el('div',{className:'li'},el('span',{className:'ico '+(d.ok?'ok':'bad')},d.ok?'✓':'!'),el('div',{className:'grow'},el('div',{className:'t'},d.ok?'로그인됨':'로그인 안 됨'),el('div',{className:'m'},d.ok?(d.account||''):'claude auth login으로 로그인합니다')))),
   d.ok?'':guide({diag:d},async()=>{await post('/api/claude',{});await load()}),
   el('div',{className:'row-actions',style:'margin-top:14px'},again))]}},
 '기본 점검':{r(){return [S.readonly?wsCard():'',checkCard('기본','모든 담당이 함께 쓰는 것',false),
  el('div',{className:'mini',style:'margin-top:14px'},el('p',{},'노션·Exa 커넥터는 이 화면에서 확인할 수 없습니다. claude.ai → 설정 → 커넥터에서 연결하고, 그 커넥터를 쓰는 담당 단계(논문 찾기·노션 올리기)에서 이어서 확인합니다.'))]}},
 '조테로 저장':{r(){const z=S.zotero,on=el('input',{type:'checkbox',id:'zon',checked:z.사용,onchange:mark,style:'width:auto;margin:0;flex:none'});
  return withAgent('zotero-keeper',[card('zotero-keeper 설정','설정/zotero-keeper.json · 이 컴퓨터의 조테로 7 앱에만 저장합니다(밖으로 나가는 것 없음).',
   el('div',{className:'f'},el('label',{htmlFor:'zon',style:'display:flex;gap:8px;align-items:center'},on,'조테로에 저장하기'),el('div',{className:'help'},'끄면 논문은 "조테로 미저장(사용 안 함)"으로 남고, 고르기·PDF·요약·노션은 그대로 합니다.')),
   f('컬렉션',inp('zc',z.컬렉션,'text','자동수집'),'조테로 왼쪽 "내 라이브러리"에 미리 만들어 둔 컬렉션 이름'),
   saveRow(()=>save('zotero',JSON.stringify({...z,사용:on.checked,컬렉션:$('#zc').value.trim()})))),
   el('div',{style:'height:14px'}),z.사용?testCard('zotero-keeper',testFresh('zotero-keeper',z))
    :el('div',{className:'result ok'},el('span',{},'✓'),el('div',{},'조테로를 쓰지 않습니다. 다음 단계로 넘어가세요.'))])}},
 '노션 올리기':{r(){return withAgent('notion-publisher',[card('지금 쓰는 노션','설정/notion-publisher.json · 새로 시작하면 notion-publisher가 씁니다.',notionNow(S.notion)),
  el('div',{style:'height:14px'}),startCard(),el('div',{style:'height:14px'}),S.notion.notion_db_url?testCard('notion-publisher',testFresh('notion-publisher',S.notion))
   :el('div',{className:'empty'},'새로 시작하면 이어서 시험까지 합니다.')])}},
 '논문 찾기':{r(){const c=S.config,s=S.scout,kws=[...s.키워드];
  const box=chipBox(kws,'kw',kws.length?'키워드 더하기…':'예: mobile game player churn',mark);
  return withAgent('paper-scout',[card('paper-scout 설정','설정/paper-scout.json · OpenAlex·Exa 검색에 쓰입니다. 바깥으로 나가니 미공개 내용은 넣지 마세요.',
   el('div',{className:'f'},el('label',{htmlFor:'kw'},'키워드'),box,el('div',{className:'help'},'Enter로 추가. 분야를 좁히는 낱말을 붙이면 다른 분야 논문이 덜 섞입니다(예: churn → mobile game player churn).')),
   el('div',{className:'two'},f('기간(일)',inp('sd',s.기간_일,'number'),'며칠 안에 나온 논문만 찾나'),f('키워드당 후보',inp('sk',s.키워드당_후보,'number'),'키워드마다 OpenAlex·Exa에서 받을 후보 수')),
   f('찾을 편수',inp('n',c.찾을_편수,'number'),'하루에 받을 논문 편수. paper-scout는 PDF 있는 관련 논문이 이만큼 모이면 검색을 멈춥니다'),
   saveRow(async()=>{box.flush();if(await save('scout',JSON.stringify({...s,키워드:kws,기간_일:+$('#sd').value,키워드당_후보:+$('#sk').value})))saveCfg({찾을_편수:+$('#n').value})})),
   el('div',{style:'height:14px'}),testCard('paper-scout',testFresh('paper-scout',s))])}},
 '요약':{r(){
  const rd=S.reader,ron=el('input',{type:'checkbox',id:'ron',checked:rd.사용,onchange:mark,style:'width:auto;margin:0;flex:none'});
  return withAgent('paper-reader',[card('paper-reader 설정','설정/paper-reader.json · 요약 양식은 스킬 paper-reader(.claude/skills/paper-reader/SKILL.md)에 있습니다.',
   el('div',{className:'f'},el('label',{htmlFor:'ron',style:'display:flex;gap:8px;align-items:center'},ron,'요약하기'),el('div',{className:'help'},'끄면 요약하지 않고 노션에는 초록만 올라갑니다(PDF는 그대로 받습니다).')),
   f('요약할 편수',inp('rm',rd.요약할_편수,'number'),`PDF를 받은 논문만 요약합니다. 찾을 편수(${S.config.찾을_편수}) 이하`),
   saveRow(()=>save('reader',JSON.stringify({...rd,사용:ron.checked,요약할_편수:+$('#rm').value})))),
   el('div',{style:'height:14px'}),rd.사용?testCard('paper-reader',true)
    :el('div',{className:'result ok'},el('span',{},'✓'),el('div',{},'요약하지 않습니다. 다음 단계로 넘어가세요.'))])}},
 '넣으면 안 되는 자료':{r(){return withAgent('privacy-guard',[privacyCard(),el('div',{style:'height:14px'}),testCard('privacy-guard',true)])}},
 '파일':{t:'파일',d:'이 폴더의 담당·스킬·설정·스크립트 파일이 어디에 있고 무엇을 하는지 봅니다. 담당·스킬·규칙 글은 여기서 고쳐 저장할 수 있습니다.',r(){return filesPage()}},
 '담당 에이전트':{r(){const uns=S.agents.filter(a=>a.unset);
  return [uns.length?fillTask(uns):'',el('div',{className:'grid g2',style:uns.length?'margin-top:14px':''},...S.agents.map(agentCard))]}},
 '마무리 점검':{r(){const r=S.checks.에이전트;
  return [checkCard(null,'모든 설정',true),
   r&&r.ok?el('div',{className:'result ok',style:'margin-top:14px'},el('span',{},'✓'),el('div',{},el('div',{},'준비가 끝났습니다. 이제 매일 논문을 받을 수 있습니다.'),
     el('div',{className:'sub'},'현황에서 "지금 논문 찾기"를 누르거나 매일 예약 시각을 정하세요.'))):'']}},

 '현황':{t:'현황',d:'오늘 받은 논문과 최근 호를 한눈에 봅니다.',r(){
  const c=S.config,D=S.days,last=D[0],all=D.flatMap(d=>d.papers),z=all.filter(p=>p.zotero_saved).length;
  const stat=(k,v,s)=>el('div',{className:'card stat'},el('div',{className:'k'},k),el('div',{className:'v'},v),el('div',{className:'s'},s));
  const ls=last?dayStatus(last):null,todo=nextTodo(),doneN=todo?stepIdx(todo):STEPS.length;
  const tiles=el('div',{className:'grid g4'},
   stat('최근 호',last?longDate(last.day).replace(/ \S+요일$/,''):'—',ls?badge(ls[0],ls[1]):'아직 실행 전'),
   stat('누적 논문',String(all.length),`${D.length}일 동안`),
   stat('조테로 저장',all.length?Math.round(z/all.length*100)+'%':'—',`${z} / ${all.length}편`),
   stat('매일 예약',S.schedule||'꺼짐',S.schedule?'그 시각에 Mac이 켜져 있어야 합니다':'아래에서 시각을 정하세요'));
  const progress=card('처음 설정',todo?`${doneN}/${STEPS.length} 단계 끝 · 다음: ${todo}`:'모든 단계를 마쳤습니다',el('div',{className:'list'},...STEPS.map((s,i)=>{const lk=lockedBy(s.k),dn=!lk&&s.done();
    return el('button',{className:'li lirow',onclick:()=>go(s.k)},el('span',{className:'ico '+(dn?'ok':lk?'':'warn')},dn?'✓':String(i+1)),el('div',{className:'grow t'},s.k),dn?'':badge(lk?'plain':'warn',lk?'잠김':'할 차례'))})));
  const recent=card('최근 실행','최근 5일',D.length?el('div',{className:'list'},...D.slice(0,5).map(d=>{const [cl,tx]=dayStatus(d);
    return el('div',{className:'li'},el('div',{className:'grow'},el('div',{className:'t'},longDate(d.day)),el('div',{className:'m'},`${d.papers.length}편 · 요약 ${d.papers.filter(p=>p.summarize).length} · 조테로 ${d.papers.filter(p=>p.zotero_saved).length}`)),badge(cl,tx))})):el('div',{className:'empty'},'아직 실행 기록이 없습니다.'));
  return [todo?el('div',{className:'banner'},`처음 설정이 아직 끝나지 않았습니다(${doneN}/${STEPS.length}). `,el('a',{href:'#',onclick:e=>{e.preventDefault();go(todo)}},`다음 단계: ${todo} →`)):'',
   runCard(),el('div',{style:'height:14px'}),scheduleCard(),el('div',{style:'height:14px'}),tiles,el('div',{className:'grid g2',style:'margin-top:14px'},progress,recent)]}},

 '실행 기록':{t:'실행 기록',d:'날짜마다 조테로 저장, 요약, 판정, 노션 업로드 결과.',r(){
  if(!S.days.length)return [el('div',{className:'card empty'},'아직 실행 기록이 없습니다. 작업공간 세션에서 "오늘 논문 찾아 줘"로 첫 호를 만들어 보세요.')];
  return S.days.map(d=>{const [cl,tx]=dayStatus(d),z=d.papers.filter(p=>p.zotero_saved).length,s=d.papers.filter(p=>p.summarize).length;
   return el('section',{className:'card',style:'margin-bottom:14px'},
    el('div',{className:'card-h'},el('div',{},el('h2',{},longDate(d.day)),el('p',{className:'desc'},d.day)),badge(cl,tx)),
    el('div',{className:'metrics'},...[['찾음',d.papers.length],['조테로',z],['요약',s],['판정 회차',d.rounds]].map(([k,v])=>el('span',{},k+' ',el('b',{},String(v)))),
     el('span',{},'다이제스트 ',el('b',{},d.digest?'있음':'없음'))),
    el('table',{},el('thead',{},el('tr',{},...['','제목','키워드','조테로','요약','노션'].map(h=>el('th',{},h)))),
     el('tbody',{},...d.papers.map(p=>el('tr',{},el('td',{className:'m',style:'color:var(--text3);width:42px'},p.id),
      el('td',{},el('a',{href:p.url,target:'_blank',rel:'noopener'},p.title)),el('td',{style:'color:var(--text2)'},p.keyword||''),
      el('td',{},p.zotero_saved?badge('ok','저장'):el('div',{},badge('bad','미저장'),p.zotero_error?el('div',{className:'err'},p.zotero_error):null)),
      el('td',{},p.summarize?(p.has_md?badge('ok','완료'):badge('bad','파일 없음')):badge('plain','—')),
      el('td',{},d.sent.includes(p.id)||(d.notion&&!d.sent.length)?badge('ok','올림'):badge('plain','아직')))))),
    d.notion?el('p',{className:'desc',style:'margin-top:12px'},'노션: ',/^https?:/.test(d.notion)?el('a',{href:d.notion,target:'_blank',rel:'noopener'},'표지 열기 ↗'):d.notion):null,
    d.stopped?el('p',{className:'desc',style:'color:var(--bad)'},'멈춤 이유: '+d.stopped):null,
    d.fails.length?el('details',{},el('summary',{},`판정 실패 ${d.fails.length}개 보기`),el('pre',{},d.fails.join('\n'))):null)})}},

 '조테로':{t:'조테로',d:'조테로 보관함을 둘러봅니다. 읽기만 하고 고치지 않습니다.',r(){
  const side=el('div',{className:'zside'}),list=el('div'),q=el('input',{type:'search',placeholder:'제목·저자·연도로 찾기',value:Z.q,ariaLabel:'조테로 검색',style:'flex:1;width:auto;min-width:0'});
  const fail=e=>list.replaceChildren(el('div',{className:'guide'},el('h4',{},'조테로에 연결하지 못했습니다'),el('p',{className:'why'},String(e.message||e)),
   el('ol',{},step('조테로 앱 켜기','조테로 7 데스크톱 앱이 켜져 있어야 읽을 수 있습니다.'),
    step('다른 앱과 통신 허용','조테로 설정 → 고급 → "이 컴퓨터의 다른 응용 프로그램이 Zotero와 통신하도록 허용"을 켭니다.')),
   el('div',{className:'foot'},el('button',{className:'btn',onclick:()=>{Z.colls=null;render()}},'다시 시도'))));
  const items=async(reset)=>{if(reset){Z.items=[];list.replaceChildren(el('div',{className:'result wait'},el('span',{className:'spin'}),'불러오는 중…'))}
   try{const r=await zfetch(Z.coll?`collections/${Z.coll}/items/top`:'items/top',{q:Z.q,start:Z.items.length,sort:'dateAdded',direction:'desc'});
    Z.items=Z.items.concat(r.items);Z.total=r.total;drawItems()}catch(e){fail(e)}};
  const drawItems=()=>list.replaceChildren(el('div',{className:'zcount'},`${Z.total}편`+(Z.q?` · "${Z.q}" 검색`:'')+(Z.items.length<Z.total?` · ${Z.items.length}편 표시`:'')),
   ...(Z.items.length?Z.items.map(zItem):[el('div',{className:'empty'},'비어 있습니다.')]),
   Z.items.length<Z.total?el('div',{style:'text-align:center;margin-top:14px'},el('button',{className:'btn ghost',onclick:()=>items(false)},'더 보기')):'');
  const drawSide=()=>{const kids=p=>Z.colls.filter(c=>c.parent===p).sort((a,b)=>a.name.localeCompare(b.name,'ko'));
   const row=(key,name,n,depth)=>el('button',{className:'zc',ariaCurrent:String(Z.coll===key),style:`padding-left:${10+depth*14}px`,onclick:()=>{Z.coll=key;drawSide();items(true)}},el('span',{},name),n===null?'':el('small',{},String(n)));
   const tree=(p,depth)=>kids(p).flatMap(c=>[row(c.key,c.name,c.n,depth),...tree(c.key,depth+1)]);
   side.replaceChildren(row('','전체 보관함',null,0),...tree('',0))};
  q.onkeydown=e=>{if(e.key==='Enter'&&!e.isComposing){Z.q=q.value.trim();items(true)}};
  (async()=>{try{if(!Z.colls)Z.colls=(await zfetch('collections')).items;drawSide();
   if(Z.coll===null)Z.coll=(Z.colls.find(c=>c.name==='자동수집')||{key:''}).key;drawSide();items(true)}catch(e){fail(e)}})();
  return [el('div',{className:'zwrap'},el('div',{},side),el('section',{className:'card'},el('div',{className:'row-actions',style:'margin-bottom:6px'},q,
    el('button',{className:'btn ghost',onclick:()=>{Z.q=q.value.trim();items(true)}},'찾기')),list))]}},

 'DB 합치기':{t:'DB 합치기',d:'번외 기능 · 전에 논문을 모으던 노션 데이터베이스를 지금 아카이브로 합칩니다.',r(){
  const src=el('input',{id:'msrc',type:'url',placeholder:'https://www.notion.so/…'}),dst=el('input',{id:'mdst',type:'url',value:S.config.notion_db_url||'',placeholder:'https://www.notion.so/…'});
  const out=el('div');
  const make=()=>{const s=src.value.trim(),d=dst.value.trim();
   const bad=!isNotion(s)?'소스 주소가 노션 데이터베이스 주소가 아닙니다':!isNotion(d)?'타겟 주소가 노션 데이터베이스 주소가 아닙니다':s===d?'소스와 타겟이 같습니다':'';
   out.replaceChildren(bad?el('div',{className:'result bad'},el('span',{},'!'),el('div',{},bad)):claudeTask(`노션 DB 합치기: 소스 ${s} → 타겟 ${d}`,
    '옮길 편수, 중복으로 건너뛸 편수, 칸 대응을 먼저 보여 주고 "진행"을 물어봅니다. 그때 진행이라고 답하세요.'))};
  return [card('어떻게 합치나요',null,el('div',{className:'mini'},
    el('p',{},'소스의 논문을 타겟으로 ',el('b',{},'복사'),'합니다. 소스 데이터베이스는 읽기만 하고 고치거나 지우지 않습니다.'),
    el('p',{},'이름과 종류가 같은 칸끼리 옮기고, 타겟에 없는 칸은 버립니다. 원문 주소나 제목이 같은 논문은 중복으로 보고 건너뜁니다.'),
    el('p',{},'본문은 옮기지 않고, 새 줄 맨 위에 원래 페이지 링크를 남깁니다.')),
   el('div',{className:'f'},el('label',{htmlFor:'msrc'},'소스 데이터베이스 주소'),src,el('div',{className:'help'},'예전에 쓰던 데이터베이스. 노션에서 데이터베이스를 열고 ··· → 링크 복사')),
   el('div',{className:'f'},el('label',{htmlFor:'mdst'},'타겟 데이터베이스 주소'),dst,el('div',{className:'help'},S.config.notion_db_url?'지금 쓰는 논문 아카이브로 채워 두었습니다':'지금 아카이브가 없습니다. 먼저 설정 → 노션에서 새로 시작하세요')),
   el('div',{className:'row-actions'},el('button',{className:'btn',onclick:make},'Claude에게 보낼 문장 만들기')),out)]}}};

// Claude Code 연결 실패 때 갈래별 해결 안내
const cmd=(c,where='터미널')=>el('div',{className:'cmd'},el('code',{},c),el('button',{type:'button',onclick:()=>navigator.clipboard.writeText(c).then(()=>toast(`복사했습니다 · ${where}에 붙여넣으세요`),()=>toast('복사 못 함 · 직접 선택해 복사하세요'))},'복사'));
const step=(t,p,...c)=>el('li',{},el('b',{},t),p?el('p',{},p):null,...c);
const TERM=()=>step('터미널 열기','⌘ + Space로 Spotlight를 열고 "터미널"을 입력해 엽니다. Claude 앱의 Terminal 패널을 써도 됩니다.');
const LOGIN=()=>[step('로그인하기','아래 명령을 터미널에 붙여넣고 Enter. 브라우저가 열리면 Claude 계정으로 로그인하고 승인을 누릅니다. 터미널에 "Login successful"이 나오면 끝입니다.',cmd('claude auth login')),
 step('로그인됐는지 보기','"loggedIn": true와 내 계정이 보이면 됩니다.',cmd('claude auth status'))];
const GUIDES={
 install:['Claude Code가 이 컴퓨터에 없습니다','대시보드가 claude 명령을 찾지 못했습니다. 설치하고 로그인하면 됩니다.',()=>[TERM(),
  step('Claude Code 설치','Homebrew가 있으면 첫 줄, 없으면 둘째 줄(Node.js 필요). 자세한 방법은 docs.claude.com의 Claude Code 설치 안내를 보세요.',cmd('brew install --cask claude-code'),cmd('npm install -g @anthropic-ai/claude-code')),...LOGIN(),
  step('대시보드 다시 켜기','설치 직후에는 대시보드가 새 명령을 못 볼 수 있습니다. 대시보드 터미널에서 Ctrl+C로 끄고 다시 켭니다.',cmd('python3 scripts/대시보드.py'))]],
 login:['Claude Code 로그인이 필요합니다','로그인이 끊겼거나 만료됐습니다. Claude 데스크톱 앱 로그인과 claude 명령 로그인은 따로라서, 앱이 되더라도 여기는 다시 로그인해야 할 수 있습니다.',()=>[TERM(),...LOGIN()]],
 limit:['사용 한도에 걸렸습니다','Claude 요금제의 사용량을 다 썼거나 서버가 붐빕니다. 잠시 기다린 뒤 다시 확인하세요.',()=>[
  step('남은 사용량 보기','claude.ai → 설정 → 사용량에서 언제 다시 쓸 수 있는지 확인합니다.')]],
 model:['모델 이름을 확인하세요','적은 모델을 Claude Code가 모릅니다.',()=>[
  step('담당 파일의 model 줄 고치기','담당 에이전트 화면에서 파일을 열어 model을 sonnet, opus, haiku 중 하나로 적습니다.')]],
 network:['인터넷 연결을 확인하세요','Claude 서버에 닿지 못했습니다.',()=>[
  step('연결 확인','와이파이·VPN·회사 방화벽을 확인합니다. 아래 명령이 응답하면 연결은 괜찮습니다.',cmd('claude -p "안녕"'))]],
 other:['직접 한 번 실행해 보세요','원인을 자동으로 가리지 못했습니다. 터미널에서 직접 실행하면 더 자세한 메시지가 나옵니다.',()=>[TERM(),
  step('직접 물어보기','응답이 오면 Claude Code는 정상입니다. 오류가 나오면 그 문장을 Claude에게 보여 주세요.',cmd('claude -p "안녕"')),...LOGIN()]]};
function guide(r,retry){const d=r.diag,[title,why,steps]=GUIDES[d.case]||GUIDES.other;
 const chips=[d.path?badge('ok','설치됨 '+(d.version||'').split(' ')[0]):badge('bad','설치 안 됨'),
  d.loggedIn===true?badge('ok','로그인 '+(d.account||'')):d.loggedIn===false?badge('bad','로그인 안 됨'):d.path?badge('warn','로그인 상태 모름'):null];
 const again=el('button',{className:'btn',type:'button',onclick:retry},'다시 확인');
 return el('div',{className:'guide'},el('h4',{},title),el('p',{className:'why'},why),el('div',{className:'diag'},...chips),
  el('ol',{},...steps()),el('div',{className:'foot'},again,el('span',{},'다 했으면 다시 확인을 누르세요. Claude Code는 10~30초 걸릴 수 있습니다.')))}

// 칩 입력: Enter·쉼표로 추가, ×나 빈 칸 Backspace로 지움(한글 조합 중 Enter는 무시)
function chipBox(list,id,ph,onchange){const inp=el('input',{id,placeholder:ph,ariaLabel:ph});const box=el('div',{className:'chips',onclick:()=>inp.focus()});
 const draw=()=>box.replaceChildren(...list.map((k,i)=>el('span',{className:'chip'},k,el('button',{type:'button',ariaLabel:k+' 지우기',onclick:e=>{e.stopPropagation();list.splice(i,1);onchange();draw();inp.focus()}},'×'))),inp);
 box.add=v=>{v=(v??inp.value).replace(/,$/,'').trim();if(v&&!list.includes(v)){list.push(v);onchange()}inp.value='';draw()};
 box.flush=()=>{if(inp.value.trim())box.add()};
 inp.onkeydown=e=>{if(e.isComposing)return;if(e.key==='Enter'||e.key===','){e.preventDefault();box.add()}else if(e.key==='Backspace'&&!inp.value&&list.length){list.pop();onchange();draw()}};
 inp.onblur=box.flush;draw();return box}

// 넣으면 안 되는 자료: 설정/연구자_정보.md의 한 줄을 칩으로 고친다
const NOGO=/^- 이 폴더에 넣으면 안 되는 자료:[ \t]*(.*)$/m;
const NOGO_SUG=['미공개 실험 원자료','심사 중인 원고','피험자 개인정보','비밀유지계약(NDA) 자료','기업·기관에서 받은 비공개 데이터','동료의 미발표 연구','연구비 제안서·심사 자료'];
function privacyCard(){const m=S.info.match(NOGO);let items=m?m[1].split(',').map(x=>x.trim()).filter(Boolean):[];
 const unknownAtStart=items.length===1&&items[0]==='모름';if(unknownAtStart)items=[];
 const note=el('span',{className:'savenote'},'');const changed=()=>{note.textContent='저장하지 않은 변경';drawSug()};
 const box=chipBox(items,'nogo','자료 종류를 적고 Enter',changed);
 const sug=el('div',{className:'sug'});const drawSug=()=>sug.replaceChildren(...NOGO_SUG.filter(x=>!items.some(i=>i.startsWith(x))).map(x=>el('button',{type:'button',onclick:()=>box.add(x)},'+ '+x)));
 const unk=el('input',{type:'checkbox',id:'nogo-unk',checked:unknownAtStart,onchange:()=>{box.hidden=sug.hidden=unk.checked;changed()}});
 box.hidden=sug.hidden=unknownAtStart;drawSug();
 const doSave=()=>{box.flush();if(!unk.checked&&!items.length)return toast('하나 이상 넣거나 "아직 모름"을 고르세요');
  const line='- 이 폴더에 넣으면 안 되는 자료: '+(unk.checked?'모름':items.join(', '));
  save('info',m?S.info.replace(NOGO,()=>line):S.info.trimEnd()+'\n\n'+line+'\n')};
 return card('넣으면 안 되는 자료','설정/연구자_정보.md',
  el('div',{className:'mini'},
   el('p',{},'노션에 올리기 직전 privacy-guard가 요약·다이제스트에 이런 자료가 섞였는지 봅니다. 걸리면 올리지 않고 멈춥니다.'),
   el('p',{},'연구실·기관 규정상 밖으로 나가면 안 되는 자료의 ',el('b',{},'종류'),'를 적습니다. 파일 이름이 아니라 "NDA 자료"처럼.'),
   el('p',{},'모르면 "아직 모름" — 그래도 전화번호·이메일 같은 개인정보와 "Confidential" 같은 공개 전 표시는 늘 점검합니다. 여기 적은 내용은 검색 키워드에 넣지 마세요(키워드는 밖으로 나갑니다).')),
  box,sug,el('label',{className:'chk'},unk,'연구실 규정을 아직 몰라요 ("모름")'),
  el('div',{className:'row-actions',style:'margin-top:14px;align-items:center'},el('button',{className:'btn ghost',onclick:doSave},'저장'),note))}

// 노션은 Claude 세션의 노션 커넥터로만 고칠 수 있다: 보낼 문장을 만들어 준다
const isNotion=u=>/^https:\/\/([\w-]+\.)?notion\.(so|site|com)\/\S+$/.test(u);
function claudeTask(phrase,ask){return el('div',{className:'guide'},el('h4',{},'Claude에게 맡기기'),
 el('p',{className:'why'},'노션은 Claude Code 세션의 노션 커넥터로 고칩니다. 아래 순서대로 하면 Claude가 처리합니다.'),
 el('ol',{},step('작업공간 세션 열기','Claude 앱 Code 탭에서 이 폴더로 세션을 엽니다(이미 열려 있으면 그 세션).',cmd(S.root,'Code 탭 폴더 선택')),
  step('이 문장 보내기','복사해서 그대로 보냅니다.',cmd(phrase,'Claude 대화창')),
  step('물어보면 답하기',ask),
  step('대시보드 새로고침','끝나면 이 화면을 새로고침해 결과를 확인합니다.')))}
function notionNow(c){c=c||{};const row=(k,v,ok)=>el('div',{className:'li'},el('span',{className:'ico '+(ok?'ok':'warn')},ok?'✓':'!'),el('div',{className:'grow'},el('div',{className:'t'},k),el('div',{className:'m'},v)));
 return el('div',{className:'list',style:'margin-bottom:16px'},
  row('표지 페이지',c.notion_url?el('a',{href:c.notion_url,target:'_blank',rel:'noopener'},'노션에서 열기 ↗'):'아직 없음',!!c.notion_url),
  row('논문 아카이브',c.notion_db_url?el('a',{href:c.notion_db_url,target:'_blank',rel:'noopener'},'노션에서 열기 ↗'):'아직 없음 — 새로 시작하면 만들어집니다',!!c.notion_db_url))}
// 노션 새로 시작: 대시보드가 Claude Code로 notion-publisher에게 '새로 시작: {주소}'를 맡긴다(아카이브·표지를 만들고 이어서 시험)
function startCard(){const u=el('input',{id:'np',type:'url',placeholder:'https://www.notion.so/… (빈 페이지 권장)',style:'flex:1;width:auto;min-width:0'}),out=el('div');
 const ow=el('input',{type:'checkbox',id:'now',style:'width:auto;margin:0;flex:none'});
 const btn=el('button',{className:'btn',type:'button',onclick:async()=>{const v=u.value.trim();
  if(!isNotion(v))return out.replaceChildren(badBox('노션 페이지 주소를 넣어 주세요. 노션에서 페이지 오른쪽 위 ··· → 링크 복사'));
  btn.disabled=true;const r=await post('/api/agent/test',{name:'notion-publisher',task:`새로 시작: ${v}`+(ow.checked?' 덮어쓰기 허락':'')}).catch(e=>({ok:false,msg:String(e)}));
  btn.disabled=false;if(!r.ok)return out.replaceChildren(badBox(r.msg));toast('notion-publisher가 노션을 꾸미기 시작했습니다');await load()}},'새로 시작');
 return card(S.notion.notion_url?'다른 페이지로 새로 시작':'노션 새로 시작','빈 페이지를 하나 만들고 오른쪽 위 ··· → 링크 복사. notion-publisher가 그 안에 논문 아카이브(11칸)와 창간 준비호 표지를 만들고, 이어서 시험까지 합니다. 전에 쓰던 페이지는 그대로 남습니다.',
  el('div',{className:'row-actions'},u,btn),
  el('label',{htmlFor:'now',style:'display:flex;gap:8px;align-items:center;margin-top:10px'},ow,'페이지에 다른 내용이 있어도 표지로 덮어써도 됩니다'),
  el('div',{className:'help'},'Notion 커넥터(claude.ai → 설정 → 커넥터)가 이 페이지에 접근할 수 있어야 합니다.'),out)}

// 조테로 탐색: 서버가 조테로 로컬 API를 읽어 필요한 칸만 넘겨 준다
const Z={coll:null,q:'',items:[],total:0,colls:null};
const zfetch=(path,params={})=>fetch('/api/zotero?'+new URLSearchParams({path,...params})).then(async r=>{const j=await r.json();if(!r.ok)throw new Error(j.error||('HTTP '+r.status));return j});
const httpLink=(u,t)=>/^https?:\/\//.test(u)?el('a',{href:u,target:'_blank',rel:'noopener'},t):null;
function zItem(i){const kids=el('div');const year=(i.date.match(/\d{4}/)||[''])[0];
 const who=i.creators.length>3?i.creators.slice(0,3).join(', ')+' 외':i.creators.join(', ');
 const att=i.children?el('button',{className:'linkbtn',onclick:async()=>{kids.replaceChildren('불러오는 중…');
   try{const r=await zfetch(`items/${i.key}/children`);kids.replaceChildren(...r.items.map(c=>el('div',{className:'zchild'},
    c.contentType==='application/pdf'?el('a',{href:`zotero://open-pdf/library/items/${c.key}`},'📄 '+c.title):el('span',{},(c.type==='note'?'📝 메모':'📎 ')+(c.type==='note'?'':c.title)))))}catch(e){kids.replaceChildren(String(e.message))}}},`첨부 ${i.children}개`):null;
 return el('article',{className:'zitem'},el('h3',{},i.title),el('div',{className:'zmeta'},[who,year,i.pub].filter(Boolean).join(' · ')),
  i.tags.length?el('div',{className:'tools'},...i.tags.slice(0,8).map(t=>el('span',{className:'tool'},t))):null,
  el('div',{className:'zlinks'},el('a',{href:`zotero://select/library/items/${i.key}`},'조테로에서 열기'),
   i.doi?httpLink('https://doi.org/'+i.doi,'DOI'):null,httpLink(i.url,'원문'),att),
  i.abstract?el('details',{},el('summary',{},'초록'),el('p',{className:'zabs'},i.abstract)):null,kids)}

// 지금 논문 찾기: 대시보드가 Claude Code로 스킬 daily-paper를 돌려 설정 편수만큼 더 받는다. 진행은 2초마다 읽어 보여 준다
let RUNPOLL=null;
function runCard(){const c=S.config,t=S.days.find(d=>d.day===S.today),got=t?t.papers.length:0;
 const box=el('div'),todo=nextTodo(),btn=el('button',{className:'btn',disabled:!!todo,onclick:async()=>{const r=await post('/api/run',{});if(!r.ok)toast(r.msg);pollRun(box,btn)}},`지금 ${c.찾을_편수}편 더 찾기`);
 fetch('/api/run').then(r=>r.json()).then(r=>{if(r.running)pollRun(box,btn);else if(r.report||r.steps.length)showRun(box,btn,r)});
 return card('지금 논문 찾기',`오늘 ${got}편 받음 · 설정 ${c.찾을_편수}편`,
  el('div',{className:'mini'},el('p',{},'예약 실행은 오늘 설정 편수를 이미 채웠으면 건너뛰고, 모자라면 그만큼만 받습니다.'),
   el('p',{},`이 버튼은 언제든 ${c.찾을_편수}편을 더 받습니다. 이 컴퓨터의 Claude Code가 스킬 daily-paper 순서대로 담당에게 맡깁니다(찾기 → 조테로 → 요약 → 판정 → 점검 → 노션). 5~15분 걸리고, 노션에는 새로 받은 논문만 올립니다.`)),
  el('div',{className:'row-actions',style:'align-items:center'},btn,todo?el('span',{className:'nxhint'},`처음 설정을 끝내면 누를 수 있습니다(다음: ${todo})`):''),box)}
function showRun(box,btn,r){btn.disabled=r.running||!!nextTodo();const last=(r.steps||[]).slice(-1)[0]||'',bad=!r.running&&(r.code||/실패(?!\s*0\s*개)|미업로드|중단/.test(r.report||''));
 box.replaceChildren(r.running?el('div',{className:'result wait'},el('span',{className:'spin'}),el('div',{},`실행 중 · ${Math.floor(r.secs/60)}분 ${r.secs%60}초`,el('div',{className:'sub'},last))):
   el('div',{className:'result '+(bad?'bad':'ok')},el('span',{},bad?'!':'✓'),el('div',{},bad?'끝났지만 확인이 필요합니다':'끝났습니다',el('div',{className:'sub'},(r.agents||[]).length?'부른 담당: '+[...new Set(r.agents)].join(' → '):''))),
  r.report?el('div',{className:'answer'},el('div',{className:'ah'},'Claude의 보고'),el('div',{className:'ab'},...mdLite(r.report))):'',
  (r.steps||[]).length?el('details',{},el('summary',{},`진행 ${r.steps.length}단계`),el('pre',{className:'failbox'},r.steps.join('\n'))):'',
  r.error?badBox(r.error):'')}
async function pollRun(box,btn){clearTimeout(RUNPOLL);const r=await fetch('/api/run').then(r=>r.json());showRun(box,btn,r);
 if(r.running)RUNPOLL=setTimeout(()=>pollRun(box,btn),2000);else if(cur==='현황')load()}
// 매일 예약: 대시보드가 Mac(launchd)에 '대시보드.py 매일실행'을 등록한다
function scheduleCard(){const at=el('input',{type:'time',value:S.schedule||'08:00',style:'width:auto'}),todo=nextTodo();
 const set=v=>async()=>{const r=await post('/api/schedule',{at:v});toast(r.msg);if(r.ok)await load()};
 return card('매일 예약',S.schedule?`매일 ${S.schedule}에 돕니다`:'꺼져 있습니다',
  el('div',{className:'row-actions',style:'align-items:center'},at,el('button',{className:'btn',disabled:!!todo,onclick:()=>set(at.value)()},S.schedule?'시각 바꾸기':'예약 켜기'),
   S.schedule?el('button',{className:'btn ghost',onclick:set('')},'예약 끄기'):'',todo?el('span',{className:'nxhint'},'처음 설정을 끝내면 켤 수 있습니다'):''),
  el('div',{className:'help'},'그 시각에 Mac이 켜져 있고 로그인돼 있어야 합니다. 기록은 매일논문/예약실행.log와 실행 기록 화면에 남습니다.'))}

function go(t){if(dirty&&t!==cur&&!confirm('저장하지 않은 변경이 있습니다. 떠날까요?'))return;dirty=false;cur=t;render();scrollTo(0,0)}
let SETUP_OPEN=null;  // 처음 설정 묶음: 다 끝나면 접고, 눌러서 다시 펼 수 있다
function render(){
 const tab=(t,...label)=>el('button',{role:'tab',ariaSelected:String(t===cur),onclick:()=>go(t)},...label);
 const todo=nextTodo(),doneN=todo?stepIdx(todo):STEPS.length;if(SETUP_OPEN===null||todo)SETUP_OPEN=SETUP_OPEN||!!todo;
 const daily=t=>{const lk=todo&&!ALWAYS_OPEN.includes(t),b=tab(t,lk?el('span',{className:'num'},'🔒'):icon(t),t);if(lk)b.classList.add('locked');return b};
 $('nav').replaceChildren(el('button',{className:'navtoggle',ariaExpanded:String(SETUP_OPEN),onclick:()=>{SETUP_OPEN=!SETUP_OPEN||!!todo;render()}},
   el('span',{},(SETUP_OPEN?'▾ ':'▸ ')+'처음 설정'),todo?el('span',{className:'navcount'},`${doneN}/${STEPS.length}`):badge('ok','완료')),
  ...(SETUP_OPEN?STEPS.flatMap((s,i)=>{const lk=lockedBy(s.k),dn=!lk&&s.done(),b=tab(s.k,el('span',{className:'num'+(dn?' ok':'')},lk?'🔒':dn?'✓':String(i+1)),s.k,s.optional?el('small',{className:'opt'},'선택'):'');if(lk)b.classList.add('locked');
   if(s.agent)b.classList.add('sub');return s.agent&&!(STEPS[i-1]||{}).agent?[el('div',{className:'navsub'},AGENT_GROUP),b]:[b]}):[]),
  el('div',{className:'navh'},'매일 쓰기'),...DAILY.map(daily),
  el('div',{className:'navh'},'번외'),...EXTRA.map(daily));
 $('#foot').replaceChildren(el('span',{},S.schedule?`매일 ${S.schedule} 예약`:'예약 꺼짐'));
 const i=stepIdx(cur),p=PAGES[cur],lk=lockedBy(cur);let head,body;
 if(i>=0){const s=STEPS[i],nx=i<STEPS.length-1?STEPS[i+1].k:'현황';
  head=el('div',{className:'head'},el('div',{},el('div',{className:'kick'},`처음 설정 · ${s.agent?AGENT_GROUP+' · '+s.agent+(s.optional?' (선택)':'')+' · ':''}${i+1}/${STEPS.length}단계`),el('h1',{},s.k),el('p',{},s.d)),s.done()&&!lk?badge('ok','끝'):'');
  body=lk?[el('div',{className:'card lockcard'},el('div',{className:'lockico'},'🔒'),el('h2',{},`먼저 '${lk}' 단계를 끝내야 합니다`),
    el('p',{className:'desc'},'앞 단계가 끝나면 이 단계가 열립니다.'),el('div',{className:'row-actions',style:'justify-content:center;margin-top:14px'},el('button',{className:'btn',onclick:()=>go(lk)},`${lk} 단계로 가기`)))]:p.r();
  if(!lk)body.unshift(todoCard(s.k,nx));
  const fd=!lk&&!s.done()&&i>0?s.fail():'';if(fd)body.push(helpCard(s.k,fd));  // 1단계(로그인)는 Claude에게 물을 수 없으니 고정 안내만
  body.push(el('div',{className:'stepnav'},i>0?el('button',{className:'btn ghost',onclick:()=>go(STEPS[i-1].k)},'← '+STEPS[i-1].k):el('span'),
   el('div',{className:'nxwrap'},s.done()||lk?'':el('span',{className:'nxhint'},'이 단계를 끝내면 다음 단계가 열립니다'),
    el('button',{className:s.done()&&!lk?'btn primary':'btn',disabled:!s.done()||!!lk,onclick:()=>{if(i===STEPS.length-1)SETUP_OPEN=false;go(nx)}},i<STEPS.length-1?`다음: ${nx} →`:'매일 쓰기 시작: 현황 →'))))}
 else{head=el('div',{className:'head'},el('div',{},el('h1',{},p.t),el('p',{},p.d)));
  body=todo&&!ALWAYS_OPEN.includes(cur)?[el('div',{className:'card lockcard'},el('div',{className:'lockico'},'🔒'),el('h2',{},'처음 설정을 먼저 끝내세요'),
    el('p',{className:'desc'},`${doneN}/${STEPS.length}단계를 마쳤습니다. 모두 마치면 매일 쓰기 메뉴가 열립니다.`),
    el('div',{className:'row-actions',style:'justify-content:center;margin-top:14px'},el('button',{className:'btn',onclick:()=>go(todo)},`다음 단계: ${todo}`)))]:p.r()}
 $('#main').replaceChildren(S.readonly?el('div',{className:'banner'},'원본 저장소에서 열렸습니다. 보기만 되고 저장은 되지 않습니다 — 처음 설정 → 기본 점검에서 "작업공간 만들기"를 누르세요.'):'',head,...body)}
async function load(){S=await fetch('/api/state').then(r=>r.json());if(cur===null)cur=nextTodo()||'현황';render()}
addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue=''}});
load();
</script></body></html>"""


def selftest():
    assert check_config({"키워드": ["a"], "찾을_편수": 2, "요약할_편수": 2}) == ""
    assert check_config({"찾을_편수": 0}) and check_reader({"사용": True, "요약할_편수": 0}) and check_reader({"사용": "y", "요약할_편수": 1})
    assert check_scout({"키워드": ["a"], "기간_일": 30, "키워드당_후보": 10}) == ""
    assert check_scout({"키워드": [""], "기간_일": 30, "키워드당_후보": 10}) and check_scout({"키워드": ["a"], "기간_일": 0, "키워드당_후보": 10})
    assert check_scout({"키워드": ["a"], "기간_일": 30, "키워드당_후보": True})
    assert agent_tools("paper-scout")[:2] == ["Read", "Glob"] and any(x.startswith("Bash(") and x.endswith(")") for x in agent_tools("paper-scout"))
    assert tool_step({"name": "mcp__claude_ai_Exa__web_search_exa", "input": {"query": "q"}}) == "web_search_exa q"
    assert tool_step({"name": "Bash", "input": {"command": "ls"}}) == "Bash ls"
    assert check_zotero(ZOTERO_DEFAULT) == "" and check_zotero({"사용": 1, "컬렉션": "a"}) and check_zotero({"사용": False, "컬렉션": " "})
    assert check_config({"키워드": ["a"], "찾을_편수": True, "요약할_편수": 1})
    assert not schedule_set("25:00")[0] and not schedule_set("8:00")[0]  # 형식이 틀리면 launchd를 건드리지 않는다
    assert any(x.startswith("Bash(python3 .claude/skills/paper-scout") for x in daily_cmd()[daily_cmd().index("--allowedTools") + 1].split(","))
    assert not save("agent", "../CLAUDE", "x")[0] and not save("other", "", "x")[0]
    assert not save("config", "", "{깨짐")[0]
    assert hint("API Error: 401 OAuth access token has been revoked", "claude-code").startswith("터미널")
    assert zotero("../../etc", {})[0] == 400 and zotero("items/abc", {})[0] == 400
    assert ZPATH.fullmatch("collections/ABCD1234/items/top") and not ZPATH.fullmatch("items/top/../x")
    assert NEW_START.fullmatch("새로 시작: https://www.notion.so/x-0123 덮어쓰기 허락") and not NEW_START.fullmatch("새로 시작: https://evil.com/x")
    assert not start_agent_test("notion-publisher", "아무 일")[0] and not start_agent_test("../x")[0]
    assert claude_case("", False, None) == "install"
    assert claude_case("API Error: 401 OAuth access token has been revoked", True, True) == "login"
    assert claude_case("", True, False) == "login"
    assert claude_case("Claude AI usage limit reached", True, True) == "limit"
    assert claude_case("model: claude-xyz not found", True, True) == "model"
    assert claude_case("getaddrinfo ENOTFOUND api.anthropic.com", True, True) == "network"
    assert front("---\nname: a\nmodel: sonnet\n---\n본문") == {"name": "a", "model": "sonnet"}
    aj = agents_json()
    assert aj["paper-scout"]["skills"] == ["paper-scout"] and aj["paper-scout"]["model"] == "sonnet" and "Glob" in aj["paper-scout"]["tools"]
    assert not aj["paper-scout"]["prompt"].startswith("---") and "역할" in aj["paper-scout"]["prompt"]
    fl = {x["path"]: x for x in file_list()}
    assert fl[".claude/skills/paper-scout/SKILL.md"]["editable"] and not fl["scripts/대시보드.py"]["editable"] and fl["CLAUDE.md"]["desc"]
    assert file_get("../../etc/passwd")[0] == 404 and file_get(".claude/agents/../../x")[0] == 404
    assert not file_save("scripts/대시보드.py", "x", None)[0] and not file_save(".claude/skills/paper-scout/SKILL.md", "---\nname: 다른\n---", None)[0]
    assert not file_save("CLAUDE.md", "x", 1)[0]  # 열어 둔 뒤 바뀜(mtime 다름)
    print("자체시험 통과")


if __name__ == "__main__":
    if sys.argv[1:] == ["자체시험"]:
        selftest()
    elif sys.argv[1:2] == ["매일실행"]:  # 예약(launchd)이 부른다: 스킬 daily-paper를 끝까지 돌리고 끝난다
        ok, msg = start_run(extra=sys.argv[2:] == ["추가"])
        print(msg)
        sys.exit(RUN["proc"].wait() if ok else 1)
    else:
        port = int(sys.argv[1]) if len(sys.argv) > 1 else 9008
        url = f"http://127.0.0.1:{port}"
        print(f"대시보드: {url}  (끄기: Ctrl+C)")
        if not os.environ.pop("DASH_REOPEN", None):  # 작업공간으로 바꿔 띄울 때는 열려 있던 창이 다시 읽는다
            webbrowser.open(url)
        ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
