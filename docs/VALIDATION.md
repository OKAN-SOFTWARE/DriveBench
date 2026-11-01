# Release validation — 0.1.0

Validated on 2026-11-01 in Linux with OpenJDK 17.0.20, Apache Maven 3.9.16, Python 3.12.14, and pytest 9.2.0.

| Check | Observed result |
| --- | --- |
| Maven build and JUnit | 10 tests passed; no failures, errors, or skipped tests; shaded simulator JAR built |
| pytest | 33 tests passed, including a real Java subprocess and TCP integration |
| Standalone regression CLI | Six scenarios passed; 39 assertions passed, zero failed; exit code 0 |
| Browser full-suite execution | Six scenarios passed; 39 assertions passed; 80 trace entries |
| Browser individual thermal scenario | 10 assertions passed; run history retained both executions |
| Browser protocol trace | Timeout error expanded with full correlation ID; subsequent successful reconnect recorded |
| HTTP report exports | JSON download header and payload verified; JUnit XML parsed with six passing testcases |
| Restart and failure reporting | Abandoned run becomes interrupted; incomplete JUnit export contains a failing completion testcase |

The managed browser check used the production dashboard assets and Python/Java components behind a QA-only local routing adapter. The adapter and its temporary runtime are excluded from the source ZIP.

Windows startup commands and batch launcher are provided, but this environment did not execute Windows. The Jenkinsfile's build and test commands were exercised locally; no Jenkins controller/agent was provisioned. Real vehicle hardware and CAN/LIN communication were not tested or implemented.
