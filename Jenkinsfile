pipeline {
    agent any

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Install Dependencies') {
            steps {
                bat 'pip install -r requirements.txt'
            }
        }

        stage('Run Tests') {
            steps {
                bat 'pytest tests/ -v'
            }
        }

        stage('Build Docker Image') {
            steps {
                bat 'docker build -t cloud-expense-tracker:%BUILD_NUMBER% .'
            }
        }

        stage('Push to Docker Hub') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'dockerhub-creds', usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASS')]) {
                    bat 'docker login -u %DOCKER_USER% -p %DOCKER_PASS%'
                    bat 'docker tag cloud-expense-tracker:%BUILD_NUMBER% %DOCKER_USER%/cloud-expense-tracker:latest'
                    bat 'docker push %DOCKER_USER%/cloud-expense-tracker:latest'
                }
            }
        }
    }

    post {
        success {
            echo 'Pipeline Successful!'
        }
        failure {
            echo 'Pipeline Failed!'
        }
    }
}