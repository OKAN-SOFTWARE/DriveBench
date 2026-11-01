// Agent prerequisites: JDK 17+, Maven 3.9+, Python 3.11+ (python/python3 on PATH).
pipeline {
    agent any
    options {
        disableConcurrentBuilds()
        timeout(time: 15, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timestamps()
    }
    stages {
        stage('Build and test Java') {
            steps {
                dir('reports') { deleteDir() }
                script {
                    if (isUnix()) {
                        sh 'java -version && mvn -B -f simulator/pom.xml clean verify'
                    } else {
                        bat 'java -version && call mvn -B -f simulator/pom.xml clean verify'
                    }
                }
            }
        }
        stage('Prepare Python') {
            steps {
                script {
                    if (isUnix()) {
                        sh 'python3 -m venv .venv && .venv/bin/python -m pip install -r requirements-dev.txt'
                    } else {
                        bat 'python -m venv .venv && .venv\\Scripts\\python -m pip install -r requirements-dev.txt'
                    }
                }
            }
        }
        stage('Python and integration tests') {
            steps {
                script {
                    if (isUnix()) {
                        sh '.venv/bin/python -m pytest --junitxml=reports/pytest.xml'
                    } else {
                        bat '.venv\\Scripts\\python -m pytest --junitxml=reports/pytest.xml'
                    }
                }
            }
        }
        stage('Vehicle regression report') {
            steps {
                script {
                    if (isUnix()) {
                        sh '.venv/bin/python -m drivebench run --no-build --report reports/scenarios.json --junit reports/scenarios.xml'
                    } else {
                        bat '.venv\\Scripts\\python -m drivebench run --no-build --report reports/scenarios.json --junit reports/scenarios.xml'
                    }
                }
            }
        }
    }
    post {
        always {
            junit testResults: 'simulator/target/surefire-reports/TEST-*.xml,reports/pytest.xml,reports/scenarios.xml'
            archiveArtifacts artifacts: 'reports/*.json,reports/*.xml,simulator/target/surefire-reports/*.xml', allowEmptyArchive: true
        }
    }
}
