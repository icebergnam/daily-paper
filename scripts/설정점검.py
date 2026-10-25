"""매일 논문 설정이 끝났는지 담당 에이전트별로 점검한다. 고치지 않고 읽기만 한다.

사용: python3 scripts/설정점검.py            전부(Claude Code 에이전트로 쓸 때)
      python3 scripts/설정점검.py 기본       기본(파이썬·Claude Code 로그인·작업공간·판정 훅·Mac 알림)만
      python3 scripts/설정점검.py 찾기       paper-scout(키워드·OpenAlex·Exa 커넥터)만
      python3 scripts/설정점검.py 조테로     zotero-keeper(조테로 앱·컬렉션, 사용 안 함이면 건너뜀)만
      python3 scripts/설정점검.py 요약       paper-reader(요약할 편수, 사용 안 함이면 건너뜀)만
      python3 scripts/설정점검.py 노션       privacy-guard·notion-publisher(넣으면 안 되는 자료·노션 아카이브·노션 커넥터)만
      python3 scripts/설정점검.py 설치       설치한 것만(개인 설정은 보지 않음). 작업공간을 만들기 전에 쓴다
노션·Exa 커넥터가 실제로 연결됐는지는 이 스크립트로 확인할 수 없다(담당 파일의 커넥터 이름만 본다). Claude에게 "설정해 줘".
종료 코드: 설정 항목(작업공간·연구자 정보·키워드·편수·노션·커넥터 이름·판정 훅)이 하나라도 빠지면 1 → 매일 논문을 시작하지 않는다.
조테로·OpenAlex 같은 실행 환경만 ❌면 0(알리기만 하고 실행은 한다).
"""
import json, pathlib, platform, shutil, subprocess, sys, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
ZOTERO = "http://127.0.0.1:23119/connector/"
results, missing = [], []
ARG = sys.argv[1] if sys.argv[1:] else ""
INSTALL = ARG == "설치"  # 설치: 개인 설정은 보지 않는다(작업공간을 만들기 전이라 비어 있다)
AGENT = not INSTALL  # 담당 파일·판정 훅


def check(name, ok, fix="", setup=False):
    results.append(ok)
    if setup and not ok:
        missing.append(setup if isinstance(setup, str) else name)  # setup에 글자를 주면 그 이름으로 알린다
    print(("✅ " if ok else "❌ ") + name + ("" if ok else f"\n   → {fix}"))


def get(url, data=None):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "daily-papers/1"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()


def cfg():
    return json.loads((ROOT / "workspace/설정/매일논문.json").read_text())


def holes(agent):
    """담당 파일에 커넥터 이름 빈칸(mcp__NOTION_ID__ 등)이 남았는가."""
    f = ROOT / f".claude/agents/{agent}.md"
    if AGENT and f.exists():
        check(f"{agent} 커넥터 이름", "_ID__" not in f.read_text(),
              f"{f.name}에 커넥터 빈칸이 남았습니다. 이 저장소 세션에서 Claude에게 '설정해 줘'라고 보내세요.", setup=True)


def 기본():
    check(f"파이썬 {platform.python_version()}", sys.version_info >= (3, 9), "python3 3.9 이상을 설치하세요 (python.org).")
    # Claude Code: 모든 담당이 여기서 일한다
    exe, st = shutil.which("claude"), {}
    try:
        st = json.loads(subprocess.run([exe, "auth", "status"], capture_output=True, text=True, timeout=20).stdout) if exe else {}
    except Exception:
        pass
    check("Claude Code 로그인" + (f" ({st.get('email')})" if st.get("loggedIn") else ""), bool(st.get("loggedIn")),
          "터미널에서 claude auth login. 설치가 안 됐으면 brew install --cask claude-code" if exe else
          "Claude Code를 설치하세요: brew install --cask claude-code (또는 npm install -g @anthropic-ai/claude-code)")
    if not INSTALL:
        check("작업공간 폴더(workspace/)", (ROOT / "workspace/설정").is_dir(), "내 설정을 둘 workspace/가 없습니다. 대시보드(python3 scripts/대시보드.py) → 기본 점검에서 '작업공간 만들기'를 누르세요.", setup=True)
        if (ROOT / "workspace/scripts").exists():  # 1.x 작업공간은 저장소 전체 사본이었다. 지금은 쓰지 않는다
            print("⚠️  workspace/에 예전(1.x) 코드 사본이 남아 있습니다 — 이제 쓰지 않습니다. 고친 담당·스킬 글이 있으면 workspace/내사본/.claude/…로 옮기고, 설정/·매일논문/·내사본/ 말고는 지워도 됩니다.")
    if AGENT:
        settings = (ROOT / ".claude/settings.json").read_text() if (ROOT / ".claude/settings.json").exists() else ""
        check("판정 루프 훅 등록", "매일논문_루프.py" in settings and (ROOT / "scripts/매일논문_판정.py").exists(),
              ".claude/settings.json의 hooks에 매일논문_루프.py가 있어야 합니다. 압축을 새로 풀어 덮어쓰세요.", setup=True)
    # Mac 알림은 없어도 실행은 되니 통과 수에 넣지 않는다
    print(("✅ " if shutil.which("osascript") else "⚠️  ") + "Mac 알림" + ("" if shutil.which("osascript") else " 없음: Mac이 아니면 마지막 알림만 안 뜹니다."))


def 찾기():
    if not INSTALL:
        c, s = cfg(), json.loads((ROOT / "workspace/설정/paper-scout.json").read_text())
        check(f"키워드 {s['키워드']}", bool(s["키워드"]), '대시보드 → 논문 찾기에서 영어 키워드를 1개 이상 넣으세요(workspace/설정/paper-scout.json).', setup="키워드")
        check(f"찾을_편수 {c['찾을_편수']}", isinstance(c["찾을_편수"], int) and not isinstance(c["찾을_편수"], bool) and c["찾을_편수"] > 0,
              "찾을_편수는 1 이상의 숫자여야 합니다.", setup="편수")
    try:
        json.loads(get("https://api.openalex.org/works?search=test&per-page=1"))
        check("OpenAlex 접속", True)
    except Exception as e:
        check("OpenAlex 접속", False, f"인터넷 연결을 확인하세요. 429면 1분 뒤 다시 하세요. ({e})")
    holes("paper-scout")


def 조테로():
    zf = ROOT / "workspace/설정/zotero-keeper.json"
    z = json.loads(zf.read_text()) if zf.exists() else {"사용": True, "컬렉션": "자동수집"}
    if not INSTALL and not z.get("사용", True):
        print("➖ 조테로 사용 안 함(workspace/설정/zotero-keeper.json) — 선택 담당이라 건너뜁니다")
        return
    try:
        get(ZOTERO + "ping")
        check("조테로 데스크톱 앱 켜짐", True)
        names = [t["name"] for t in json.loads(get(ZOTERO + "getSelectedCollection", b"{}"))["targets"]]
        check(f"조테로 '{z['컬렉션']}' 컬렉션", z["컬렉션"] in names, f"조테로 왼쪽 목록에서 '내 라이브러리' 오른쪽 클릭 → 새 컬렉션 → 이름 '{z['컬렉션']}'.")
    except Exception:
        check("조테로 데스크톱 앱 켜짐", False, "조테로 7 데스크톱 앱을 켜 두세요. 설정 → 고급 → '다른 앱과 통신 허용'이 켜져 있어야 합니다.")


def 요약():
    if not INSTALL:
        rf = ROOT / "workspace/설정/paper-reader.json"
        r = json.loads(rf.read_text()) if rf.exists() else {"사용": True, "요약할_편수": 2}
        if not r.get("사용", True):
            print("➖ 요약 사용 안 함(workspace/설정/paper-reader.json) — 선택 담당이라 건너뜁니다")
            return
        n, m = cfg()["찾을_편수"], r["요약할_편수"]
        check(f"요약할_편수 {m}", isinstance(m, int) and not isinstance(m, bool) and 0 < m <= (n if isinstance(n, int) else 0),
              "workspace/설정/paper-reader.json의 요약할_편수는 1 이상이고 찾을_편수 이하인 숫자여야 합니다.", setup="편수")


def 노션():
    if not INSTALL:
        info = (ROOT / "workspace/설정/연구자_정보.md").read_text()
        blank = [line for line in info.splitlines() if line.startswith("- ") and line.rstrip().endswith(":")]
        check("넣으면 안 되는 자료(privacy-guard)", not blank, "대시보드 설정 → 넣으면 안 되는 자료를 채우세요. 모르면 '모름'.", setup="연구자 정보")
        nf = ROOT / "workspace/설정/notion-publisher.json"
        check("노션 아카이브(notion_db_url)", bool(json.loads(nf.read_text()).get("notion_db_url") if nf.exists() else ""),
              "대시보드 → 노션 올리기에서 페이지 주소를 넣고 새로 시작하세요(workspace/설정/notion-publisher.json).", setup=True)
    holes("notion-publisher")


# 담당 에이전트 순서: 기본 → 찾기 → 조테로 저장 → 요약 → 노션에 올리기
SECTIONS = {"기본": ("기본", 기본), "찾기": ("찾기 · paper-scout", 찾기), "조테로": ("조테로 · zotero-keeper", 조테로),
            "요약": ("요약 · paper-reader", 요약), "노션": ("노션 · privacy-guard → notion-publisher", 노션)}
if ARG and ARG not in SECTIONS and not INSTALL:
    sys.exit(f"모르는 점검: {ARG} (쓸 수 있는 것: {', '.join(SECTIONS)}, 설치)")
for key, (title, run) in SECTIONS.items():
    if ARG in SECTIONS and ARG != key or INSTALL and key in ("요약", "노션"):  # 설치 점검에서 요약·노션은 볼 것이 없다
        continue
    print(f"[{title}]")
    run()
    print()

done = " — 설치 확인 완료! 노션·Exa 커넥터는 Claude가 세션의 도구 목록으로 확인합니다." if INSTALL else " — 설정 완료!"
print(f"{sum(results)}/{len(results)} 통과" + (done if all(results) else ""))
if missing:
    print("⛔ 설정이 끝나지 않아 매일 논문을 시작하지 않습니다: " + ", ".join(dict.fromkeys(missing)))
sys.exit(1 if missing else 0)
