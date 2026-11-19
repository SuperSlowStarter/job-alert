"""미디어DB(mediadb.co.kr) 채용공고 감시기.

목록 전체를 읽어 새 공고 중 키워드(OAP, 모션그래픽 등)가 들어간 것을
ntfy 푸시로 보냅니다. 로그인이 필요 없으므로 계정 정보를 다루지 않습니다.

환경변수
  NTFY_TOPIC   ntfy 토픽 이름 (필수, 비밀처럼 취급: 아는 사람은 누구나 구독 가능)
  NTFY_SERVER  기본 https://ntfy.sh
  KEYWORDS     쉼표로 구분한 키워드 (기본값은 아래 DEFAULT_KEYWORDS)
  DRY_RUN=1    알림을 보내지 않고 결과만 출력
"""
from __future__ import annotations

import base64
import html
import http.client
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = "https://www.mediadb.co.kr/member/recruit/"
ROOT = Path(__file__).resolve().parent
SEEN_FILE = ROOT / "seen.json"
STATUS_FILE = ROOT / "status.json"
NET_FAIL_LIMIT = 3  # 연속 접속 실패가 이 횟수에 닿을 때만 실패 처리(메일 발송)
MATCHES_FILE = ROOT / "docs" / "matches.json"
KST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (job-alert personal bot)"
MAX_PAGES = 10
PAGE_SIZE = 20

DEFAULT_KEYWORDS = [
    "OAP",
    "모션그래픽",   # 띄어쓰기 변형(모션 그래픽)도 자동 매칭
    "모션디자인",
    "motion graphic",
    "motion design",
    "애프터이펙트",  # 애프터 이펙트도 매칭
    "After Effects",
]


def keywords() -> list[str]:
    env = os.environ.get("KEYWORDS", "").strip()
    return [k.strip() for k in env.split(",") if k.strip()] if env else DEFAULT_KEYWORDS


def kw_pattern(kw: str) -> re.Pattern:
    # 영문 키워드는 다른 영단어 속에 묻힌 경우(예: SOAP)를 제외
    if re.fullmatch(r"[A-Za-z ]+", kw):
        body = r"\s*".join(re.escape(w) for w in kw.split())
        return re.compile(rf"(?<![A-Za-z]){body}", re.I)
    # 한글 키워드는 글자 사이 띄어쓰기를 허용 (모션그래픽 = 모션 그래픽)
    return re.compile(r"\s*".join(re.escape(ch) for ch in kw.replace(" ", "")), re.I)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for wait in (10, 30, None):  # 일시적 접속 오류는 재시도
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", errors="replace")
        except (OSError, http.client.HTTPException) as e:
            if wait is None:
                raise
            print(f"  접속 실패({e}), {wait}초 후 재시도")
            time.sleep(wait)


def clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
LINK_RE = re.compile(r"<a href='\./view\.php\?mod=view&encData=([^']+)'>(.*?)</a>", re.S)
UID_RE = re.compile(r"name='uid\[\d+\]' value='(\d+)'")
P_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.S)
TD_RE = re.compile(r"<td>(.*?)</td>", re.S)


def parse_list(page_html: str) -> list[dict]:
    jobs = []
    for row in ROW_RE.findall(page_html):
        link = LINK_RE.search(row)
        uid = UID_RE.search(row)
        if not link or not uid:
            continue
        ps = [clean(p) for p in P_RE.findall(row)]
        tds = [clean(t) for t in TD_RE.findall(row)]
        category = next((p.split(":", 1)[1].strip() for p in ps if p.startswith("직무/직종")), "")
        jobs.append({
            "uid": uid.group(1),
            "title": clean(link.group(2)),
            "summary": ps[0] if ps else "",
            "category": category,
            "deadline": tds[2] if len(tds) > 2 else "",
            "url": BASE + "view.php?mod=view&encData=" + link.group(1),
        })
    return jobs


def list_all() -> list[dict]:
    jobs: dict[str, dict] = {}
    for page in range(MAX_PAGES):
        start = page * PAGE_SIZE
        enc = base64.b64encode(f"start={start}".encode()).decode()
        url = BASE + "main.php" + (f"?encData={enc}" if start else "")
        found = parse_list(fetch(url))
        new = [j for j in found if j["uid"] not in jobs]
        for j in new:
            jobs[j["uid"]] = j
        if not new:
            break
        time.sleep(1)
    return list(jobs.values())


def detail_text(url: str) -> str:
    page = fetch(url)
    i = page.find("공고제목")
    return clean(page[i:] if i >= 0 else page)


def notify(job: dict, hits: list[str]) -> None:
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        raise SystemExit("NTFY_TOPIC 환경변수가 없습니다.")
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    payload = {
        "topic": topic,
        "title": job["title"][:120],
        "message": f"{job['category']} · 마감 {job['deadline']}\n{job['summary']}\n키워드: {', '.join(hits)}",
        "click": job["url"],
        "tags": ["briefcase"],
        "priority": 4,
    }
    req = urllib.request.Request(
        server, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": UA}, method="POST",
    )
    urllib.request.urlopen(req, timeout=30).read()


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    dry = os.environ.get("DRY_RUN") == "1"
    pats = {k: kw_pattern(k) for k in keywords()}
    seen: list[str] = load(SEEN_FILE, [])
    seen_set = set(seen)
    matches: list[dict] = load(MATCHES_FILE, [])

    status = load(STATUS_FILE, {"net_fail": 0})
    try:
        jobs = list_all()
    except (OSError, http.client.HTTPException) as e:
        status["net_fail"] = status.get("net_fail", 0) + 1
        print(f"사이트 접속 실패 {status['net_fail']}회 연속: {e}")
        if not dry:
            save(STATUS_FILE, status)
        return 1 if status["net_fail"] >= NET_FAIL_LIMIT else 0
    status["net_fail"] = 0
    if not dry:
        save(STATUS_FILE, status)
    if not jobs:
        # 접속은 되는데 공고를 못 읽음 = 사이트 구조 변경 → 실패로 끝내서 GitHub이 메일로 알려줌
        print("공고를 하나도 읽지 못했습니다. 사이트 구조 변경을 확인하세요.")
        return 1
    print(f"목록 {len(jobs)}건, 새 공고 {sum(j['uid'] not in seen_set for j in jobs)}건")

    for job in jobs:
        if job["uid"] in seen_set:
            continue
        text = f"{job['title']} {job['category']}"
        try:
            text += " " + detail_text(job["url"])
        except Exception as e:  # 상세가 실패해도 제목/직종으로는 판단
            print(f"  상세 실패 {job['uid']}: {e}")
        time.sleep(0.7)
        hits = [k for k, p in pats.items() if p.search(text)]
        if hits:
            print(f"  ★ {job['title']}  ({', '.join(hits)})")
            if not dry:
                try:
                    notify(job, hits)
                except (OSError, http.client.HTTPException) as e:
                    print(f"  알림 전송 실패, 다음 실행에서 재시도: {e}")
                    continue  # seen에 넣지 않아 다음에 다시 시도
            job["keywords"] = hits
            job["found_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
            matches.insert(0, job)
        if not dry:
            seen.append(job["uid"])
            seen_set.add(job["uid"])

    if not dry:
        save(SEEN_FILE, seen[-3000:])
        save(MATCHES_FILE, matches[:300])
    return 0


if __name__ == "__main__":
    sys.exit(main())
