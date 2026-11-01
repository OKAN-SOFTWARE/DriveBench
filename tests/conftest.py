import pytest
from drivebench.runtime import JAR, SimulatorProcess


@pytest.fixture(scope="session")
def simulator():
    if not JAR.is_file():
        pytest.fail("Build Java first: mvn -f simulator/pom.xml verify")
    with SimulatorProcess() as process:
        yield process
