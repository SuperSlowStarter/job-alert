# 미디어DB 모션그래픽 · OAP 공고 알림

GitHub Actions가 하루 8번(한국시간 08~22시, 2시간 간격) mediadb.co.kr 채용 목록 전체를 확인합니다.
새 공고의 제목·직종·상세 본문에 키워드가 있으면 아이폰으로 푸시를 보냅니다.

- 로그인 불필요 → **아이디·비밀번호를 어디에도 저장하지 않음**
- 비용 0원, Mac·Apple 개발자 계정 불필요
- 알림을 누르면 해당 공고 페이지가 바로 열림

## 설정 (한 번만, 약 10분)

### 1. 아이폰
1. App Store에서 **ntfy** 앱 설치
2. 앱에서 `+` → 토픽 이름 입력 (예: `motion-jobs-fd9b69e37264ca10`) → 구독
   - 토픽 이름은 비밀번호처럼 다루세요. 이름을 아는 사람은 누구나 구독할 수 있습니다.

### 2. GitHub
1. github.com 가입 → 새 저장소 생성 (예: `job-alert`, **Public**: Pages와 Actions를 무료로 쓰기 위해)
2. 이 폴더에서:
   ```
   git init -b main
   git add .
   git commit -m "init"
   git remote add origin https://github.com/<아이디>/job-alert.git
   git push -u origin main
   ```
3. 저장소 **Settings → Secrets and variables → Actions**
   - **Secrets** 탭 → `NTFY_TOPIC` = 위 토픽 이름
   - (선택) **Variables** 탭 → `KEYWORDS` = `OAP,모션그래픽,모션디자인,motion graphic,애프터이펙트`
4. **Settings → Pages** → Source: `Deploy from a branch`, Branch: `main` / `/docs` → Save
5. **Actions** 탭 → "채용공고 확인" → **Run workflow**로 첫 실행
   - 첫 실행 때는 현재 올라와 있는 매칭 공고가 모두 알림으로 오고, 그다음부터는 새 공고만 옵니다.

### 3. 목록 화면 (선택)
아이폰 Safari에서 `https://<아이디>.github.io/job-alert/` 열기 → 공유 → **홈 화면에 추가**.
지금까지 매칭된 공고를 앱처럼 볼 수 있습니다. 마감된 공고는 흐리게 표시됩니다.

## 로컬 시험
```
$env:DRY_RUN="1"; python check_jobs.py      # 알림 없이 결과만 출력
```

## 파일
- `check_jobs.py` 수집·필터·알림 (파이썬 표준 라이브러리만 사용)
- `.github/workflows/check.yml` 실행 일정
- `seen.json` 이미 확인한 공고 번호 (자동 생성)
- `docs/matches.json`, `docs/index.html` 목록 화면

## 보안 메모
- 이 사이트는 공고 열람에 로그인이 필요 없어서 계정 정보를 쓰지 않습니다.
- 나중에 로그인이 필요해지면 코드에 넣지 말고 GitHub **Secrets**에만 저장하세요(로그에서 자동으로 가려짐).
  다른 사이트와 다른 비밀번호를 쓰세요.
- 사이트에 부담을 주지 않도록 하루 8회, 요청 사이에 대기 시간을 둡니다.
