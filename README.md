# Skills

직접 만든 에이전트 스킬 중 공개할 스킬을 개발하고 배포하는 저장소입니다.

| 스킬 | 용도 | 상태 |
| --- | --- | --- |
| [Splunk SPL Writer](spl/README.md) | 실제 로그 구조에 맞는 최적화된 SPL 생성·제공 | 프리뷰 — CIM 상세 단계는 후속 개발 |

## 배포본 설치

Codex에서 모든 프로젝트에 사용할 스킬은 GitHub에서 전역 설치합니다. 프로젝트 한 곳에서만 사용하려면 해당 프로젝트에서 `--global`을 빼고 설치합니다.

```sh
npx skills add dollce/skills --skill splunk-spl-writer --agent codex --global
npx skills list --global
```

이미 설치했다면 `npx skills update splunk-spl-writer --global`, 삭제하려면 `npx skills remove splunk-spl-writer --global`을 사용합니다. 필요한 MCP 연결은 스킬별 안내를 참고하세요. [SPL 사용 안내](spl/README.md)

## 배포 전 로컬 테스트

macOS 또는 Linux에서 이 저장소를 열고 다음 명령을 실행합니다. 링크 명령에는 Python 3.9 이상과 Make가 필요합니다.

```sh
make dev-link
make dev-status
```

`make dev-link`는 공개 스킬마다 이 프로젝트의 `.agents/skills/<이름>`에서 소스 디렉터리로 직접 연결합니다. 예를 들어 `.agents/skills/splunk-spl-writer`는 `spl/splunk-spl-writer/`를 가리킵니다. 파일을 편집하면 다음에 스킬을 읽을 때 수정한 내용이 보입니다.

Codex 또는 ChatGPT 데스크톱의 로컬 Codex 작업에서 **이 체크아웃을 작업 폴더로 열고 새 세션**을 시작합니다. 스킬 목록에서 이 체크아웃의 `SKILL.md`를 선택하고 샘플 요청으로 동작을 점검합니다.

다른 프로젝트에서 개발본을 써야 할 때는 `make dev-link-global`로 `~/.agents/skills/`에 연결할 수 있습니다. 같은 이름의 설치본이나 수동 링크가 그 위치에 있으면 명령이 충돌 경로를 출력하고 중단됩니다. 전역 배포본이 있다면 기본값인 `make dev-link`로 이 프로젝트에서 테스트할 수 있습니다.

동명 전역 배포본과 프로젝트 개발본은 Codex 목록에 함께 표시될 수 있습니다. 스킬을 지정하지 않고 **자동 호출**을 시험하려면 테스트 세션에 그 이름의 스킬이 하나만 있는지 확인하세요. 필요하면 위의 `npx skills remove`로 해당 전역 배포본을 먼저 해제하고, 테스트 후 다시 설치합니다.

구조 검증을 처음 실행할 때는 저장소 루트에서 개발 의존성을 준비합니다.

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r spl/requirements-dev.txt
make check
make check-cli
```

`make check`는 SPL 스킬의 메타데이터, 참조 경로, ZIP 재빌드와 개발 링크 동작을 확인합니다. `make check-cli`는 Git이 추적하는 파일과 아직 커밋하지 않은 새 파일을 현재 내용으로 준비하고 Git이 무시하는 새 파일은 제외합니다. 이 상태를 임시 프로젝트에 설치해 모든 스킬의 이름과 디렉터리 안의 파일을 비교하고, 설치본의 Markdown에서 참조하는 로컬 파일도 확인합니다. Node.js 22.20 이상과 Git이 필요하며, 처음 실행할 때는 npm에서 CI와 같은 버전의 CLI를 받습니다.

테스트가 끝나면 아래 명령 하나로 **이 체크아웃이 만든 프로젝트·전역 링크를 모두 해제**합니다. 이름이 바뀌거나 원본이 삭제된 스킬도 정리합니다. 이미 다른 링크나 설치본으로 교체된 경로는 보존합니다. 체크아웃을 이동하거나 삭제할 때도 먼저 실행하세요.

```sh
make dev-unlink
make dev-status
```

PR 검토와 검증을 거쳐 `master`에 병합하면 GitHub 원본으로 배포됩니다. 위의 `npx skills add` 또는 `update`로 배포본을 사용합니다.

## 공개 스킬 추가

설치할 파일을 `<그룹>/<스킬 이름>/SKILL.md`와 같은 디렉터리에 두고, 스킬의 YAML `name`을 디렉터리 이름과 맞춥니다. 새 그룹은 루트 `skills.sh.json`의 `paths`에 등록합니다. 같은 그룹에 스킬을 추가하면 다음 `make dev-link`에서 함께 연결됩니다. 개발 노트와 빌드 도구는 설치할 디렉터리 바깥에 둡니다. [SPL 인수인계 문서](spl/MAINTAINER.md)

라이선스: [MIT](LICENSE).
