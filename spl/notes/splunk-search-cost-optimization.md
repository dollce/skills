# Splunk 필드 추출과 CIM 정규화의 검색 성능 최적화

조사 기준일: 2026년 11월 4일. SPL1과 Splunk Enterprise 9.4 및 10.x, CIM 6.4 공식 문서 기준. 목표는 검색 시간과 CPU·메모리·디스크·전송 부하 감소다. 운영 환경에서 측정한 성능 수치는 포함하지 않는다.

**권장 구조는 `검색 범위 제한 → 필요한 입력 필드 유지 → 필터용 최소 추출·정규화 → 필터 → 출력용 추출·CIM 정규화 → 집계`다. 배열은 원소를 먼저 줄이고, 개별 행이 필요할 때만 펼친다.** “모든 필드 추출 후 모든 CIM 필드 생성”을 고정된 전처리 단계로 만들지 말고, 각 필드를 실제로 사용하는 단계에 맞춰 계산한다. 이 구성은 공식 필터 조기 적용 원칙을 사용자의 추출·정규화 목적에 적용한 설계 권고다. [검색 최적화](https://help.splunk.com/en/splunk-enterprise/search/search-manual/9.0/optimizing-searches/quick-tips-for-optimization)

CIM의 필드 이름과 의미를 일반 SPL에서 사용할 수 있으며, 아래 구성은 datamodel 검색이나 `tstats`를 사용하지 않는다. 다만 일부 CIM 필드로 출력하는 것과 전체 CIM 호환성을 갖추는 것은 구분한다. [CIM 정규화](https://help.splunk.com/en/splunk-enterprise/common-information-model/6.4/using-the-common-information-model/use-the-cim-to-normalize-data-at-search-time)

**명령의 역할과 배치**

| 명령 | 실제 역할 | 권장 배치 |
|---|---|---|
| `fields` | 필드 보존·제거. 자체 파서가 아니다. | 처음에는 후속 계산에 필요한 입력을 남기고, 큰 중간 필드는 마지막 사용 직후 제거 |
| `spath` / `rex` | JSON/XML 경로 또는 정규식 기반 추출 | 필터에 쓰는 필드는 먼저, 결과 표시용 필드는 필터 뒤 |
| `eval` | 값 계산·변환·정규화 | 필터에 필요한 계산만 먼저. 나머지는 생존 이벤트에 적용 |
| `where` / `search` | 이벤트 필터 | 조건에 필요한 값이 준비되는 즉시 |
| `mvfilter` / `mvfind` / `mvcount` | 다중 값의 원소 필터·존재 확인·개수 계산 | 목적을 충족하면 `mvexpand` 없이 사용 |
| `mvexpand` | 배열 원소별 행 생성 | 부모 이벤트와 원소를 걸러내고 행 크기를 줄인 뒤, 필요한 경우 한 번 |
| `stats` | 집계 및 행 축소 | 결과에 필요한 추출·필터 이후. 집계 후 가능한 부가 작업은 그 뒤 |

`fields`가 추출 대상과 후속 처리량을 줄이는 데 도움을 줄 수는 있지만, 원문에서 읽을 이벤트 수까지 줄인다고 해석하지 않는다. `fields src dest`만으로는 내부 필드 `_raw`가 제거되지 않는다. 원문이 더 필요하지 않을 때 `fields - _raw`로 명시적으로 제거한다. [fields](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/9.4/search-commands/fields)

**단일 JSON 이벤트 예시**

다음 JSON의 `deny/drop/block`이 해당 제품에서 모두 네트워크 차단을 뜻한다고 확인한 상황이다. JSON 경로, 인덱스, sourcetype은 실제 데이터에 맞게 바꾼다. 예시 필드는 모두 단일 값이다.

```json
{
  "action": "DENY",
  "src_ip": "203.0.113.10",
  "dest_ip": "198.51.100.20",
  "dest_port": "443",
  "protocol": "TCP"
}
```

```spl
index=network sourcetype=vendor_firewall_json earliest=-1h latest=now
| fields _time host sourcetype _raw
| spath input=_raw path=action output=q_action
| eval q_action=lower(trim(q_action))
| where in(q_action, "deny", "drop", "block")
| spath input=_raw path=src_ip output=src
| spath input=_raw path=dest_ip output=dest
| spath input=_raw path=dest_port output=q_dest_port
| spath input=_raw path=protocol output=q_transport
| eval action="blocked",
       dest_port=tonumber(q_dest_port),
       transport=lower(trim(q_transport))
| fields _time host sourcetype src dest dest_port transport action
| fields - _raw
```

필터 판정에는 `q_action`만 필요하므로 IP·포트·프로토콜 추출은 그 뒤에 둔다. 앞선 조건을 통과한 값들의 의미가 차단으로 확정되었으므로 `action="blocked"`를 설정한다. 다른 제품에서는 같은 문자열의 의미나 매핑 대상 목록이 다를 수 있다. Network Traffic의 `action` 권장 규약에는 `allowed/blocked/teardown`이 있고, 포트는 숫자, `transport`는 소문자 프로토콜이다. [Network Traffic 필드 정의](https://help.splunk.com/en/splunk-enterprise/common-information-model/6.4/data-models/network-traffic)

이 예시는 **CIM 필드 형태의 이벤트 출력**이다. 집계가 필요하면 이어서 `stats count by src dest dest_port action` 등을 적용한다. 다만 그룹 키가 없는 이벤트가 집계에서 사라질 수 있으므로, 누락률을 먼저 확인한다. 원문 조사까지 필요하면 `_raw` 제거를 생략한다.

이미 TA나 `KV_MODE=json`이 필요한 값을 정확히 추출한다면 해당 필드를 재사용하고 중복 `spath`를 생략한다. 그 경우 첫 `fields`에도 사용할 기존 필드를 포함해야 한다. 위처럼 원문에서 다시 추출하는 구성을 모든 소스에 일괄 적용하지 않는다. [spath의 자동 추출 대안](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/9.4/search-commands/spath)

**필터와 CIM 정규화의 순서 결정**

| 상황 | 구성 |
|---|---|
| 원본 값의 조건이 원하는 CIM 조건과 동등함 | 원본 필드 추출 → 원본 값 필터 → 생존 이벤트 정규화 |
| 조건이 여러 원본 필드의 `coalesce`, 단위 변환, lookup 결과에 의존함 | 그 조건에 필요한 최소 정규화 → 필터 → 나머지 정규화 |
| 정규화된 값으로 그룹화·중복 판단·결합해야 함 | 해당 정규화를 그 연산보다 먼저 수행 |
| 배열의 모든 자식이 공유하는 부모 필드의 계산·lookup | 불필요한 부모 이벤트를 제거한 뒤, `mvexpand` 전에 한 번 수행 |
| 설명·표시 이름만 추가함 | 가능하면 `stats` 뒤에서 추가 |
| 전체 정규화 이벤트를 반환해야 함 | 의도한 대상 전체에 필요한 정규화를 수행. 성능만을 위해 임의의 이벤트 필터를 추가하지 않음 |

예를 들어 `src=coalesce(client_ip, remote_ip)`로 정의한다면 `client_ip=대상IP`만 먼저 필터링하는 것은 동등하지 않다. `client_ip`가 없는 이벤트에서 `remote_ip`가 대상일 수 있기 때문이다. 같은 의미를 가진 필드인지와 우선순위를 먼저 정해야 한다. 빈 문자열도 건너뛰려면 다음처럼 명시한다. [coalesce와 nullif](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/9.4/evaluation-functions/comparison-and-conditional-functions)

```spl
| eval src=coalesce(nullif(trim(client_ip),""),nullif(trim(remote_ip),""))
| where src="203.0.113.10"
```

단순 이름 변경은 `rename` 또는 field alias로, 값·자료형·우선순위 변경은 `eval`이나 lookup으로 표현한다. 짧은 고정 매핑은 `case()`, 제품별로 자주 바뀌는 매핑은 관리 가능한 lookup이 적합하다는 설계 판단이다. 어느 쪽이 항상 빠르다고 단정하지 않는다. lookup 출력은 필요한 필드만 요청하고, 단순 표시값이면 집계 뒤로 미룬다. 단, 필터나 그룹 의미를 결정하는 lookup은 먼저 필요하다. [lookup 최적화](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/9.2/search-commands/lookup)

**JSON 배열은 원소와 필드의 관계를 유지한다**

아래처럼 하나의 원본 이벤트에 연결 객체들이 담긴 경우를 가정한다.

```json
{
  "records": [
    {"action":"deny","src_ip":"203.0.113.10","dest_ip":"198.51.100.20","dest_port":443},
    {"action":"allow","src_ip":"203.0.113.11","dest_ip":"198.51.100.21","dest_port":80}
  ]
}
```

객체를 통째로 다중 값 필드에 담고, 차단 원소만 남긴 다음 한 번 펼친다. `json_extract`는 SPL1 9.4 문서에 있는 함수이며 운영 버전 지원을 확인한다. `mvfilter(json_extract(...))` 방식은 Splunk Security Content에서도 사용한다. [JSON 함수](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/9.4/evaluation-functions/json-functions), [Splunk의 객체 필터 예시](https://research.splunk.com/endpoint/13435b55-afd8-46d4-9045-7d5457f430a5/)

```spl
index=network sourcetype=vendor_firewall_batch earliest=-1h latest=now
| fields _time host sourcetype _raw
| spath input=_raw path=records{} output=q_record
| eval q_record=mvfilter(
    in(lower(trim(json_extract(q_record,"action"))),"deny","drop","block")
  )
| where mvcount(q_record)>0
| fields _time host sourcetype q_record
| fields - _raw
| mvexpand q_record
| spath input=q_record path=src_ip output=src
| spath input=q_record path=dest_ip output=dest
| spath input=q_record path=dest_port output=q_dest_port
| eval dest_port=tonumber(q_dest_port), action="blocked"
| fields _time host sourcetype src dest dest_port action
```

이 구성은 부모 이벤트 1개가 아니라 **차단된 연결 객체 1개를 결과 1행으로 정의**한다. 부모의 시간·host가 모든 자식에 적용된다는 전제다. 자식별 시간이나 장비가 있으면 해당 필드를 추출하여 사용한다. 부모 전체를 감사·조사해야 한다면 자식 필터링이나 원문 제거를 그대로 적용하지 않는다. 객체째 추출한 뒤 확장하고 하위 필드를 읽는 패턴은 CIM 공식 문서에도 있다. [CIM의 객체 확장 예시](https://help.splunk.com/en/splunk-enterprise/common-information-model/6.4/using-the-common-information-model/use-the-cim-to-normalize-data-at-search-time)

`records{}.src_ip`, `records{}.dest_ip`를 각각 추출한 뒤 `mvexpand src | mvexpand dest`로 처리하면 모든 조합이 생성되어 원래 연결 관계가 깨질 수 있다. `mvzip`도 두 목록의 길이·순서·NULL 위치와 구분자 충돌이 해결되어야 한다. 객체 배열이라면 객체를 유지하는 방식을 우선한다. 이는 행 확장 동작에서 도출되는 데이터 보존 원칙이다. [mvexpand](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/9.4/search-commands/mvexpand)

원소 필터는 공짜가 아니다. 각 객체의 action을 읽는 비용이 추가된다. 대부분의 원소를 제거하고 이후 처리할 필드가 많을수록 이득을 기대할 수 있지만, 거의 모두 통과하는 작은 배열이면 바로 확장하는 편과 실측 비교한다.

부모 이벤트 공통 필드의 변환·lookup은 살아남은 부모에 대해 확장 전에 처리하면 자식마다 같은 계산을 반복하지 않아도 된다. 반대로 자식 객체의 IP·포트는 각 객체를 기준으로 처리해야 한다. `json_extract`를 지원하지 않는 버전에서는 객체를 한 번 펼친 직후 action만 추출·필터하고, 남은 객체의 상세 필드를 추출하는 구성을 비교한다.

**mvexpand가 아예 필요 없는 경우**

위 배열 검색에서 `where mvcount(q_record)>0`까지 실행한 뒤, 목적에 따라 다음 중 하나로 끝낼 수 있다.

| 목적 | 이어 붙일 SPL | 집계 단위 |
|---|---|---|
| 차단 객체를 포함한 원본 이벤트 수 | `stats count AS matching_parent_events` | 부모 이벤트 |
| 차단된 연결 객체 총수 | `eval n=mvcount(q_record) | stats sum(n) AS blocked_connections` | 배열 객체 |
| 객체별 IP·포트 조건, 행별 출력 | 필요한 필드만 남긴 뒤 `mvexpand q_record` | 배열 객체 |

단순 MV 문자열의 포함 여부는 `mvfind`, 값 제한은 `mvfilter`, 원소 수는 `mvcount`로 처리할 수 있다. `mvfind`는 정규식이므로 정확한 값 일치는 앵커와 이스케이프를 고려한다. 배열 객체 간 관계가 필요한 조건은 독립된 필드 목록에 각각 적용하지 말고 같은 객체 안에서 평가한다. [Multivalue 함수](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/9.4/evaluation-functions/multivalue-eval-functions)

`mvexpand` 메모리는 대략 입력 행 크기·한 청크의 행 수·다중 값 개수에 영향을 받는다. 공식 기본 메모리 제한은 500 MB이며 청크가 한도를 넘으면 잘리고 경고가 발생할 수 있다. 따라서 불필요한 큰 원문을 제거하고 원소 수를 줄이는 것이 우선이다. `limit=`로 원소를 잘라낸 결과는 전체 결과와 다르다. 운영 설정 상향을 첫 해법으로 삼지 않는다. [mvexpand 메모리 제한](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/9.4/search-commands/mvexpand)

**spath과 rex 선택 시 확인할 점**

- JSON/XML은 구조를 해석하는 `spath`를 기본으로 삼는다. 경로 없는 `spath`는 전체 자동 추출이며 기본 `extraction_cutoff=5000` 제한이 있다. 명시 경로와 `output`으로 필요한 값을 지정한다. 긴·깨진 JSON에서 추출 성공률을 확인한다. [spath](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/9.4/search-commands/spath), [extraction_cutoff 설정](https://help.splunk.com/en/data-management/splunk-enterprise-admin-manual/10.2/configuration-file-reference/10.2.6-configuration-file-reference/limits.conf)
- 필요한 경로가 많다면 **명시 경로 여러 번과 전체 추출 한 번 중 무엇이 빠른지는 측정해야 한다.** 명시 경로가 항상 빠르다는 공식 보장은 없다. 초기 필터로 얼마나 줄어드는지가 선택 기준이다.
- 원문 전체에 반복 `rex`를 적용하기보다 필요한 패턴만 추출한다. 안정적인 텍스트 형식에서 여러 필드가 항상 함께 필요하다면 하나의 정규식으로 묶는 안도 비교한다. 필터 뒤에서만 필요한 필드는 분리할 가치가 있다. JSON을 단순 정규식으로 대체하면 escaping·중첩·키 순서 변화로 결과가 달라질 수 있다. [rex](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/9.4/search-commands/rex)
- `eval`을 한 줄로 합치는 것 자체를 주요 최적화로 보지 않는다. 처리할 행 수와 계산 내용이 중요하다. SPL의 쉼표로 연결한 eval 식은 왼쪽부터 평가되므로 의존 관계에 맞춰 작성한다. [eval](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/10.6/search-commands/eval)

**자동 추출 설정과 명시적 SPL은 별도로 본다**

반복 검색에서는 검증한 search-time 추출·FIELDALIAS·calculated field·lookup을 sourcetype별 TA/앱에 관리하면 일관성을 높일 수 있다. 설정으로 옮긴다고 파싱 CPU 비용이 없어지는 것은 아니다.

자동 search-time 처리의 핵심 순서는 `EXTRACT → REPORT → KV → FIELDALIAS → EVAL-* → LOOKUP → eventtype → tags`다. 버전·권한에 따른 field filter 같은 선행 처리는 별도다. 같은 props stanza의 `EVAL-*`는 서로의 계산 결과에 의존하도록 연결할 수 없으며, 뒤에 실행되는 lookup 결과도 참조할 수 없다. 이 부분은 명시적 SPL eval 체인과 다르다. [Search-time 처리 순서](https://help.splunk.com/en/splunk-enterprise/manage-knowledge-objects/knowledge-management-manual/9.4/get-started-with-knowledge-objects/the-sequence-of-search-time-operations)

따라서 SPL 맨 앞의 `fields` 하나로 모든 TA 자동 작업을 껐다고 가정하지 않는다. Fast 모드는 불필요한 field discovery를 줄이지만 명시적으로 요구한 search-time 필드는 계속 필요하다. 집계 검색은 Smart에서도 Fast에 준하는 동작을 하므로 모드 변경 효과를 과장하지 않는다. [Search modes](https://help.splunk.com/en/splunk-enterprise/search/search-manual/10.6/use-the-search-app/search-modes)

CIM 정규화 시 `src/dest` 방향, NAT 전후 주소, 포트 자료형, 바이트·시간 단위를 보존한다. 예컨대 수집기 `host`를 실제 네트워크 장비 `dvc`로 무조건 복사하면 안 된다. Network Traffic의 전체 호환성을 목표로 한다면 필드뿐 아니라 해당 이벤트 의미와 `network/communicate` 태그 등도 검증한다. 없는 IP·포트를 0이나 임의 문자열로 채워 정상화된 것처럼 표시하지 않는다. [Network Traffic](https://help.splunk.com/en/splunk-enterprise/common-information-model/6.4/data-models/network-traffic)

**추출 실패를 정상적인 필터 탈락과 분리한다**

단일 JSON 예시에서 `q_action`을 소문자로 만든 직후, `where` 대신 다음을 적용하면 action 추출·매핑 상태를 점검할 수 있다. 허용·종료 값 목록도 실제 제품 규약에 맞춰 완성한다.

```spl
| eval q_action_state=case(
    isnull(q_action) OR q_action="", "missing",
    in(q_action,"deny","drop","block","allow","accept","permit","teardown"), "mapped",
    true(), "unmapped"
  )
| stats count by q_action_state
```

`missing`에는 필드가 없는 정상 형식과 파싱 실패가 함께 들어갈 수 있다. 원문을 확인해 구분한다. 필터 후에만 이 점검을 하면 이미 사라진 실패 이벤트는 볼 수 없다. src·dest·포트도 필터 직후 별도 품질 집계에서 누락률·형변환 실패를 확인한다. 이런 점검용 필드를 CIM 필드 값에 섞지 않는다.

**동일 결과를 유지한 성능 비교**

동일한 절대 시간 구간, 사용자·앱·권한, 검색 모드에서 다음을 비교한다. 완료된 동일 데이터에 A/B를 번갈아 여러 번 실행해 캐시와 동시 부하 영향을 구분하고, 결과의 행 단위와 중복 개수까지 일치하는지 본다. 이 절차는 비교 실험을 위한 권고다.

| 비교안 | 확인할 질문 |
|---|---|
| 전체 spath·정규화 후 필터 vs 필터용 추출 후 나머지 처리 | 초기 필터의 탈락 비율이 충분한가? |
| 명시 경로 여러 번 vs spath 한 번 | 실제 JSON 크기와 필드 수에서 어느 쪽이 빠른가? |
| mvexpand 후 필터 vs 원소 필터 후 mvexpand | 확장 행 수와 메모리가 줄고 객체 대응이 유지되는가? |
| 원문 유지 vs 마지막 사용 뒤 제거 | 큰 원문 복제·전달 부담이 줄어드는가? |
| 확장 후 count vs mvcount 합계 | 같은 단위를 세면서 확장을 없앨 수 있는가? |

Job Inspector의 `runDuration`과 `scanCount`, `command.search.kv`, 각 추출·eval·mvexpand의 입력/출력 수 및 시간, `optimizedSearch`·`remoteSearch`를 확인한다. `scanCount`가 같아도 후속 추출·확장 비용은 줄 수 있다. 명령 시간은 분산 실행 구간이 겹칠 수 있으므로 단순 합산해 경과시간이나 CPU 시간으로 해석하지 않는다. 실제 CPU·메모리 부하는 환경의 모니터링 지표와 함께 본다. [Job Inspector](https://help.splunk.com/en/splunk-enterprise/search/search-manual/9.3/manage-jobs/view-search-job-properties)

`fields`, `eval`, `spath`, `rex`, `where`와 `mvexpand`는 분산 가능한 streaming 처리에 속한다. 반면 앞선 centralized command 때문에 실행 위치가 달라질 수 있다. `sort`·`join`·`transaction` 같은 전체 수집 또는 중앙 처리 비용이 있는 단계를 추출·필터 앞에 습관적으로 두지 않는다. optimizer는 가능한 조건을 이동하므로 문장 순서와 실제 실행 계획이 반드시 같지는 않다. [명령 유형](https://help.splunk.com/en/splunk-enterprise/search/search-manual/9.4/search-overview/types-of-commands), [내장 최적화](https://help.splunk.com/en/splunk-enterprise/search/search-manual/9.4/optimizing-searches/built-in-optimization)

**초기 검색 필터의 보충 원칙**

시간·index·sourcetype을 필요한 범위로 제한하고, 타깃 모두에 존재한다고 검증한 원문 토큰이 있으면 추가한다. search-time 필드를 첫 줄에 쓴다고 indexed field가 되지는 않는다. [필드 검색](https://help.splunk.com/en/splunk-enterprise/search/search-manual/9.4/retrieve-events/use-fields-to-retrieve-events)

- `TERM(IP)`를 일괄 적용하지 않는다. 공식 예에서 `127.0.0.1 - admin`은 찾지만 `ip=127.0.0.1 - user=admin`은 같은 TERM 검색으로 찾지 못한다. 실제 토큰 경계가 다르기 때문이다. [TERM 조건](https://help.splunk.com/en/splunk-enterprise/search/search-manual/9.4/search-primer/use-case-and-term-to-match-phrases)
- `*word*`를 `word`로 바꾸면 부분 문자열과 토큰 검색의 의미가 달라진다. [Wildcards](https://help.splunk.com/en/splunk-enterprise/search/search-manual/9.4/search-primer/wildcards)
- `search`와 `where`는 대소문자·논리 우선순위가 다르므로 기계적으로 교환하지 않는다. `search action!=allow`는 누락 필드를 제외하지만 `NOT action=allow`는 포함한다. 파싱 불완전 환경에서는 이 차이를 보존해야 한다. [search](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/9.4/search-commands/search), [where](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/9.4/search-commands/where)
