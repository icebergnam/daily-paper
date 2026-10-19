"""매일 논문 설정이 끝났는지 점검한다. 고치지 않고 읽기만 한다.

사용: python3 scripts/설정점검.py        Claude Code로 쓸 때
      python3 scripts/설정점검.py 단독   Claude Code 없이 쓸 때(LLM·노션 연결은 매일논문_단독.py 점검)
노션·Exa 커넥터는 이 스크립트로 확인할 수 없다. Claude에게 "설정해 줘"라고 하면 연결까지 확인한다(설치와설정.html).
"""
import json, pathlib, platform, shutil, sys, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
ZOTERO = "http://127.0.0.1:23119/connector/"
results = []
SOLO = sys.argv[1:] == ["단독"]


def check(name, ok, fix=""):
    results.append(ok)
    print(("✅ " if ok else "❌ ") + name + ("" if ok else f"\n   → {fix}"))


def get(url, data=None):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "daily-papers/1"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()


# 1. 파이썬
check(f"파이썬 {platform.python_version()}", sys.version_info >= (3, 9), "python3 3.9 이상을 설치하세요 (python.org).")

# 2. 연구자 정보
info = (ROOT / "설정/연구자_정보.md").read_text()
blank = [line for line in info.splitlines() if line.startswith("- ") and line.rstrip().endswith(":")]
check("연구자 정보", not blank, "Claude에게 '시작'이라고 보내면 묻고 채웁니다.")

# 3. 매일 논문 설정
cfg = json.loads((ROOT / "설정/매일논문.json").read_text())
check(f"키워드 {cfg['키워드']}", bool(cfg["키워드"]), '설정/매일논문.json의 "키워드"에 영어 키워드를 1개 이상 적으세요.')
check(f"찾을_편수 {cfg['찾을_편수']} · 요약할_편수 {cfg['요약할_편수']}",
      isinstance(cfg["찾을_편수"], int) and isinstance(cfg["요약할_편수"], int) and 0 < cfg["요약할_편수"] <= cfg["찾을_편수"],
      "두 값은 숫자이고, 요약할_편수는 찾을_편수 이하여야 합니다.")
if not SOLO:
    check("notion_db_url", bool(cfg.get("notion_db_url")), "Claude에게 '설정해 줘'라고 보내세요(노션 표지 만들기).")

# 4. OpenAlex
try:
    json.loads(get("https://api.openalex.org/works?search=test&per-page=1"))
    check("OpenAlex 접속", True)
except Exception as e:
    check("OpenAlex 접속", False, f"인터넷 연결을 확인하세요. 429면 1분 뒤 다시 하세요. ({e})")

# 5. 조테로
try:
    get(ZOTERO + "ping")
    check("조테로 데스크톱 앱 켜짐", True)
    names = [t["name"] for t in json.loads(get(ZOTERO + "getSelectedCollection", b"{}"))["targets"]]
    check("조테로 '자동수집' 컬렉션", "자동수집" in names, "조테로 왼쪽 목록에서 '내 라이브러리' 오른쪽 클릭 → 새 컬렉션 → 이름 '자동수집'.")
except Exception:
    check("조테로 데스크톱 앱 켜짐", False, "조테로 7 데스크톱 앱을 켜 두세요. 설정 → 고급 → '다른 앱과 통신 허용'이 켜져 있어야 합니다.")

if not SOLO:  # Claude Code 전용 점검
    # 6. 담당 파일의 커넥터 이름
    holes = [f.name for f in (ROOT / ".claude/agents").glob("*.md") if "_ID__" in f.read_text()]
    check("담당 파일의 커넥터 이름", not holes, f"{', '.join(holes)}에 빈칸이 남았습니다. Claude에게 '설정해 줘'라고 보내세요.")

    # 7. 노션 표지 틀
    front = (ROOT / ".claude/skills/daily-paper-format/references/앞면_틀.md").read_text()
    check("노션 표지 틀의 아카이브 주소", "{아카이브_" not in front, "Claude에게 '설정해 줘'라고 보내세요.")

    # 8. 판정 루프 훅
    settings = (ROOT / ".claude/settings.json").read_text() if (ROOT / ".claude/settings.json").exists() else ""
    check("판정 루프 훅 등록", "매일논문_루프.py" in settings and (ROOT / "scripts/매일논문_판정.py").exists(),
          ".claude/settings.json의 hooks에 매일논문_루프.py가 있어야 합니다. 압축을 새로 풀어 덮어쓰세요.")

# 9. Mac 알림 (없어도 실행은 됨)
print(("✅ " if shutil.which("osascript") else "⚠️  ") + "Mac 알림" + ("" if shutil.which("osascript") else " 없음: Mac이 아니면 마지막 알림만 안 뜹니다."))

print(f"\n{sum(results)}/{len(results)} 통과" + (" — 설정 완료!" if all(results) else ""))
