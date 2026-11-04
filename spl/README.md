# Splunk SPL Writer

사용자 요청과 실제 로그 구조에 맞는 최적화된 SPL을 만들어 사용자 또는 다른 에이전트에게 제공합니다. `SPL 생성`, `SPL 작성`, `SPL 만들어줘` 등의 요청에 사용합니다.

**현재는 프리뷰입니다.** `splunk-mcp`를 통한 검색 대상 탐색, 좁은 이벤트 샘플 조회, 필드 파싱·유지 지침까지 구현했습니다. 로그 유형·목적에 따른 CIM 카테고리 선택과 필요한 필드만 정규화하는 상세 흐름, 예외 처리 정책은 후속 개발 대상입니다.

## 설치

Node.js 22.20 이상과 Git을 준비하고, 사용할 프로젝트에서 실행합니다.

```sh
npx skills add https://github.com/dollce/skills --skill splunk-spl-writer
```

기본은 프로젝트 설치이며 사용할 에이전트를 선택할 수 있습니다. Codex만 선택하려면 다음과 같이 실행합니다.

```sh
npx skills add https://github.com/dollce/skills --skill splunk-spl-writer --agent codex
```

개인 전역 설치는 `--global`을 추가합니다.

```sh
npx skills add https://github.com/dollce/skills --skill splunk-spl-writer --agent codex --global
```

설치 전에 저장소에서 검색되는 스킬을 확인할 수 있습니다.

```sh
npx skills add https://github.com/dollce/skills --list
```

이 스킬은 **별도로 연결된 `splunk-mcp`**가 필요합니다. 서버, 주소, 인증 정보는 패키지에 포함하지 않습니다. 설치 자체가 Splunk 연결을 설정하거나 검색을 실행하지는 않습니다.

## 목록·업데이트·삭제

프로젝트 설치는 설치했던 프로젝트 디렉터리에서 관리합니다.

```sh
npx skills list
npx skills check splunk-spl-writer --project
npx skills update splunk-spl-writer --project
npx skills remove splunk-spl-writer
```

전역 설치는 범위를 명시합니다.

```sh
npx skills list --global
npx skills check splunk-spl-writer --global
npx skills update splunk-spl-writer --global
npx skills remove splunk-spl-writer --global
```

`check`는 사용 가능한 업데이트가 있으면 종료 코드 1을 반환할 수 있습니다. `update`는 지정한 범위의 해당 스킬을 갱신하며, 직접 편집한 설치본은 갱신 과정에서 덮어써질 수 있습니다. 개발 수정은 설치본 대신 이 저장소에서 수행합니다.

위 삭제 명령은 선택한 범위에서 이 스킬의 모든 에이전트 연결을 정리합니다. 공용 설치 경로가 남지 않도록 `--agent` 필터를 생략했습니다. 다른 스킬이나 반대 범위의 설치는 삭제하지 않습니다.

업데이트 원본은 `dollce/skills`입니다. 기본 브랜치 `master`의 스킬 변경을 CLI가 확인하여 반영하므로 별도 npm 패키지를 배포할 필요가 없습니다. CLI가 생성한 설치 기록을 유지합니다. ZIP을 수동으로 복사한 설치와 로컬 경로 설치는 GitHub 원본을 추적하는 설치와 구분하며, 위 유지보수 명령을 사용하려면 GitHub URL로 설치합니다.

## 저장소 구조

```text
skills.sh.json                         # CLI 검색 위치: ./spl
spl/
  README.md                            # 이 문서
  MAINTAINER.md                        # 다음 세션 인수인계
  LICENSE
  notes/splunk-search-cost-optimization.md
  requirements-dev.txt
  scripts/build_release.py
  scripts/check_release.py
  splunk-spl-writer/                   # CLI가 설치하는 스킬 폴더
    SKILL.md
    LICENSE
    agents/openai.yaml
    references/field-extraction.md
```

설치 대상은 `spl/splunk-spl-writer/`입니다. 개발 문서·조사 노트·패키징 도구는 그 바깥에 두어 설치본에 포함되지 않도록 합니다. 저장소 루트의 `skills.sh.json`은 다른 스킬이 추가되어도 `spl/`을 검색할 수 있게 합니다. 같은 스킬을 여러 경로에 복제하지 않습니다.

## 개발·검증

다른 컴퓨터에서는 저장소를 복제한 뒤 `spl/MAINTAINER.md`부터 읽습니다.

```sh
git clone https://github.com/dollce/skills.git
cd skills
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r spl/requirements-dev.txt
python3 spl/scripts/check_release.py
npx skills add . --list
```

실제 Splunk를 실행하지 않고 스킬 메타데이터·참조 경로·패키징·CLI 검색을 확인합니다. CI에서도 이 검증을 수행하며 CLI 검증 버전은 `skills@1.7.6`으로 고정합니다. CLI 버전을 올릴 때는 검색과 설치·업데이트·삭제 동작을 함께 확인합니다.

ZIP이 필요하면 저장소 루트에서 실행합니다.

```sh
python3 spl/scripts/build_release.py
```

`spl/dist/`에 설치용 프리뷰 ZIP, 개발 인수인계 ZIP, `SHA256SUMS`가 생성됩니다. 생성물은 Git에 포함하지 않습니다. ZIP은 수동 전달용이며 CLI 설치의 필수 요소는 아닙니다.

공식 CLI 문서: [설치·유지보수 명령](https://github.com/vercel-labs/skills/blob/main/docs/commands.md), [스킬 검색과 사용자 지정 경로](https://github.com/vercel-labs/skills/blob/main/docs/creating-skills.md).

라이선스: [MIT](LICENSE).
