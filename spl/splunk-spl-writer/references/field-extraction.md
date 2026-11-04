# 필요한 필드 추출과 검색 비용

이 지침은 SPL의 필드 파싱·유지 블록을 설계할 때 사용한다. 실제로 확인한 로그 구조와 사용자의 결과 요구를 기준으로 명령을 선택한다.

## 검색 아키텍처에 맞춘 배치

Splunk의 이벤트 인덱스는 압축 원문과 이를 가리키는 `tsidx`, 메타데이터를 시간별 버킷에 저장한다. 검색 시작 부분의 시간·인덱스·소스 조건과 유효한 토큰으로 읽을 후보를 먼저 줄인다. search-time 필드를 첫 줄에 쓰는 것만으로 indexed field가 되는 것은 아니다. [인덱스와 버킷](https://help.splunk.com/en/data-management/manage-splunk-enterprise-indexers/9.0/indexing-overview/indexes-indexers-and-indexer-clusters), [검색 범위 최적화](https://help.splunk.com/en/splunk-enterprise/search/search-manual/9.0/optimizing-searches/quick-tips-for-optimization)

`fields`는 검색 결과의 필드를 보존·제거한다. 필요한 필드를 일찍 제한하면 후속 필드 처리와 전송량을 줄이는 데 도움이 되지만, 버킷에서 지정한 열만 읽게 하거나 읽을 이벤트 수를 직접 줄이는 명령으로 설명하지 않는다. 자동 추출·optimizer가 이미 수행하는 최적화가 있으므로 `fields` 추가만으로 모든 파싱 작업이 없어지거나 항상 더 빨라진다고 보장하지 않는다.

`fields`, `eval`, `spath`, `rex`, `where`, `mvexpand` 등 분산 가능한 streaming 처리를 인덱서에서 수행할 수 있는 위치에 둔다. 불필요한 `sort`, `join`, `transaction` 등 중앙 처리나 전체 수집 비용이 있는 명령을 그 앞에 배치하지 않는다. 실제 처리 위치는 앞선 명령과 optimizer의 실행 계획에도 영향을 받는다. [명령 처리 유형](https://help.splunk.com/en/splunk-enterprise/search/search-manual/9.4/search-overview/types-of-commands), [내장 최적화](https://help.splunk.com/en/splunk-enterprise/search/search-manual/9.4/optimizing-searches/built-in-optimization)

## 필드 의존 관계와 선택적 추출

1. 최종 출력·필터·그룹 키·후속 블록이 사용하는 필드를 정하고, 이를 만드는 입력을 역으로 확인한다. `_time`, 소스 식별 필드, `_raw`, JSON을 담은 별도 필드 등도 실제 의존 관계에 따라 유지한다.
2. 초기 `fields`에는 필요한 기존 필드와 추출 입력을 포함한다. `fields` 자체는 파서가 아니므로 아직 존재하지 않는 출력 필드만 남기고 입력을 버리지 않는다.
3. 샘플에서 확인한 자동 추출 필드는 재사용한다. 같은 값을 얻기 위해 원문을 중복 파싱하지 않는다. 자동 추출 여부나 TA 설정을 제품명만으로 가정하지 않는다.
4. 필터 판단에 필요한 값만 먼저 추출·계산하고, 해당 필터를 적용한 뒤 출력용 필드를 추출한다. 필터를 옮길 때 누락값, 대소문자, 논리 우선순위와 값 변환의 의미를 보존한다. 뒤에서 정규화한 값이 필요한 조건을 원본 필드 하나의 조건으로 임의 치환하지 않는다.
5. 마지막 사용을 마친 큰 입력과 중간 필드를 제거한다. `_raw`가 더 필요하지 않다면 `fields - _raw`로 명시적으로 제거한다. `fields`의 포함 목록만으로 `_raw`가 제거된다고 가정하지 않으며, 시간 기반 후속 처리가 필요하면 `_time`을 유지한다. [fields](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/9.4/search-commands/fields)

필드 파싱이나 형변환 실패만을 이유로 `where isnum(...)`, `where isnotnull(...)` 같은 추가 제외 조건을 만들지 않는다. 사용자 요청에서 실패 이벤트의 제외를 요구하지 않았다면 행을 보존하고, 해당 값의 누락·변환 실패를 설명한다. 최종 분석에 필요한 명시적인 유효값 조건은 그대로 적용한다.

| 명령 | 선택 기준 |
| --- | --- |
| `fields` | 필요한 필드를 보존·제거한다. 초기 입력 제한과 파싱 블록의 출력 필드 정리에 사용한다. |
| `spath` | JSON/XML에서 필요한 경로를 읽는다. 입력·경로·출력 이름을 명확히 하고, 중첩 구조와 배열 관계를 유지한다. |
| `rex` | 확인된 텍스트 형식에서 필요한 패턴을 추출한다. JSON의 escaping·중첩을 단순 정규식으로 대체하지 않는다. |
| `eval` | 필요한 파생값·자료형 변환을 계산한다. 입력 의존 순서와 기존 필드 덮어쓰기를 확인한다. CIM 의미 매핑은 별도 블록으로 둔다. |
| `mvexpand` | 배열 원소별 행이 결과에 필요할 때 사용한다. 존재 확인·개수 계산만 필요하면 다중값 함수로 해결할 수 있는지 먼저 판단한다. |

경로 없는 `spath`는 자동 전체 추출이다. 필요한 경로가 적으면 `input`, `path`, `output`을 지정해 불필요한 출력을 피한다. 필요한 경로가 많을 때 명시적 추출을 여러 번 수행하는 것이 항상 빠르다고 단정하지 않는다. 긴 원문이나 잘린 샘플에서 경로 지정만으로 모든 추출 제한을 해결한다고 가정하지 않는다. [spath](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/9.4/search-commands/spath)

`eval`은 필요한 계산에만 사용한다. 쉼표로 묶은 식은 왼쪽부터 평가되므로 의존 관계에 맞게 순서를 정한다. 한 줄로 합치는 것 자체를 성능 최적화의 근거로 삼지 않는다. [eval](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/10.6/search-commands/eval)

## 배열의 관계와 행 단위 보존

- 목적이 원본 이벤트 수인지, 배열 원소 수인지, 원소별 출력인지 먼저 정한다. `mvexpand` 뒤의 `count`를 원본 이벤트 수로 취급하지 않는다.
- 가능한 경우 부모 이벤트와 필요한 배열 원소를 먼저 줄이고, 확장할 행의 큰 불필요 필드를 제거한다. 필터는 사용자가 원하는 결과를 그대로 보존할 때만 적용한다.
- 모든 자식이 공유하는 부모 필드의 추출·계산은 가능한 한 `mvexpand` 전에 수행하여 자식마다 같은 처리를 반복하지 않는다. 자식별로 다른 필드는 해당 객체에서 추출한다.
- 객체 배열은 객체 전체를 다중값 필드로 추출한 뒤 그 객체를 펼치고 자식 필드를 읽는다. 예를 들어 `spath input=_raw path=items{} output=item_json` → `mvexpand item_json` → `spath input=item_json path=id output=item_id` 순서로 원소의 관계를 유지한다.
- 같은 배열의 IP·포트 등 자식 필드를 따로 추출한 뒤 각각 `mvexpand`하여 모든 조합을 만들지 않는다. `mvzip`은 위치 기반이므로 누락된 키, 순서, 길이와 구분자 문제가 해결된 경우에만 사용한다.
- 존재 확인·개수·원소 필터링만 필요하면 `mvfind`, `mvcount`, `mvfilter` 등을 검토한다. 객체 내부 여러 필드를 함께 검사하는 조건은 같은 객체 안에서 평가한다. 함수의 NULL 및 반환값 의미를 확인한다.
- `mvexpand`는 행 수와 메모리를 늘린다. `limit=`로 원소를 잘라내는 방식을 완전한 결과를 보존하는 최적화로 제시하지 않는다. 메모리 초과 시 결과가 잘릴 수 있으므로 불필요한 원문 복제와 확장을 줄인다.

근거: [mvexpand](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/9.4/search-commands/mvexpand), [다중값 함수](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/9.4/evaluation-functions/multivalue-eval-functions), [공식 객체 배열 처리 예시](https://help.splunk.com/en/splunk-enterprise/common-information-model/6.4/using-the-common-information-model/use-the-cim-to-normalize-data-at-search-time). 마지막 문서는 객체를 추출·확장하는 처리 방식만 참고하며 CIM 매핑 규칙을 이 파싱 단계에 포함하지 않는다.

## 제공 전 정적 점검

확인한 샘플과 대조하여 입력 필드가 사용 전에 제거되지 않았는지, 경로와 자료형이 맞는지, 배열 원소의 대응과 결과 행 단위가 유지되는지 확인한다. 파싱 블록의 출력에는 후속 블록에서 사용하는 필드가 남아 있어야 한다. 파싱 실패나 필드 누락을 정상적인 필터 탈락으로 가정하지 않는다.

기존 샘플로 판단할 수 없는 부분은 확인된 사실과 구분해 설명한다. 이 점검을 최종 SPL의 실제 실행 검증이나 성능 측정으로 표현하지 않는다.
