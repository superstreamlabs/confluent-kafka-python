
pipeline {

    agent {
        docker {
            label 'memphis-jenkins-big-fleet,'
            image 'python:3.11.9'
            args '-u root'
        }
    }

    environment {
            HOME           = '/tmp'
            TOKEN          = credentials('maven-central-token')
            GPG_PASSPHRASE = credentials('gpg-key-passphrase')
            SLACK_CHANNEL  = '#jenkins-events'
    }

    stages {
        stage('Prepare Environment') {
            steps {
              sh """
                apt update -y
                apt install -y wget software-properties-common lsb-release gcc make python3 python3-pip python3-dev libsasl2-modules-gssapi-mit krb5-user

              """            
              sh """
                wget https://github.com/confluentinc/librdkafka/archive/refs/tags/v2.5.0.tar.gz
                tar -xvzf v2.5.0.tar.gz
                cd v2.5.0.tar.gz
                cd librdkafka-2.5.0/ 
                ./configure
                make
                make install
              """
              sh """
                python3 -m pip install --no-binary confluent-kafka confluent-kafka
                python3 -c 'import confluent_kafka; print(confluent_kafka.version())'
              """
            }
        }        
        // stage('Beta Release') {
        //     when {
        //         branch '*-beta'
        //     }            
        //     steps {
        //         script {
        //             sh 'git config --global --add safe.directory $(pwd)'
        //             env.GIT_AUTHOR = sh(script: 'git log -1 --pretty=%an', returnStdout: true).trim()
        //             env.COMMIT_MESSAGE = sh(script: 'git log -1 --pretty=%B', returnStdout: true).trim()
        //             def triggerCause = currentBuild.getBuildCauses().find { it._class == 'hudson.model.Cause$UserIdCause' }
        //             env.TRIGGERED_BY = triggerCause ? triggerCause.userId : 'Commit'
        //         }                
        //         script {
        //             def version = readFile('version-beta.conf').trim()
        //             env.versionTag = version
        //             echo "Using version from version-beta.conf: ${env.versionTag}"               
        //         }
        //         sh """
        //           sed -i -r "s/superstream-confluent-kafka/superstream-confluent-kafka-beta/g" setup.py
        //         """ 
        //         sh "sed -i \"s/version='[0-9]\\+\\.[0-9]\\+\\.[0-9]\\+'/version='${versionTag}'/g\" setup.py"
        //         sh """               
        //            python3 setup.py sdist
        //         """
        //         withCredentials([usernamePassword(credentialsId: 'python_sdk', usernameVariable: 'USR', passwordVariable: 'PSW')]) {
        //                 sh 'twine upload -u $USR -p $PSW dist/*'
        //             }                                                 
        //     }
        // }
        // stage('Prod Release') {
        //     when {
        //         branch '3.5.1'
        //     }            
        //     steps {
        //         script {
        //             def version = readFile('version.conf').trim()
        //             env.versionTag = version
        //             echo "Using version from version.conf: ${env.versionTag}"
        //             setupGPG()     
        //             publishClients() 
        //             uploadBundleAndCheckStatus()                                              
        //         }
        //     }
        // }
        // stage('Create Release'){
        //     when {
        //         branch '3.5.1'
        //     }       
        //     steps {               
        //         sh """
        //             curl -L https://github.com/cli/cli/releases/download/v2.40.0/gh_2.40.0_linux_amd64.tar.gz -o gh.tar.gz 
        //             tar -xvf gh.tar.gz
        //             mv gh_2.40.0_linux_amd64/bin/gh /usr/local/bin 
        //             rm -rf gh_2.40.0_linux_amd64 gh.tar.gz
        //         """
        //         withCredentials([sshUserPrivateKey(keyFileVariable:'check',credentialsId: 'main-github')]) {
        //         sh """
        //         GIT_SSH_COMMAND='ssh -i $check -o StrictHostKeyChecking=no' git config --global user.email "jenkins@memphis.dev"
        //         GIT_SSH_COMMAND='ssh -i $check -o StrictHostKeyChecking=no' git config --global user.name "Jenkins"                
        //         GIT_SSH_COMMAND='ssh -i $check -o StrictHostKeyChecking=no' git tag -a $versionTag -m "$versionTag"
        //         GIT_SSH_COMMAND='ssh -i $check -o StrictHostKeyChecking=no' git push origin $versionTag
        //         """
        //         }                
        //         withCredentials([string(credentialsId: 'gh_token', variable: 'GH_TOKEN')]) {
        //         sh """
        //         gh release create $versionTag /tmp/kafka-clients/kafka-client-${env.versionTag}.tar.gz --generate-notes
        //         """
        //         }                
        //     }
        // }                              
    }
    post {
        always {
            cleanWs()
        }
        // success {
        //     sendSlackNotification('SUCCESS')
        // }
        // failure {
        //     sendSlackNotification('FAILURE')
        // }
    }    
}

// SlackSend Function
def sendSlackNotification(String jobResult) {
    def jobUrl = env.BUILD_URL
    def messageDetail = env.COMMIT_MESSAGE ? "Commit/PR by ${env.GIT_AUTHOR}:\n${env.COMMIT_MESSAGE}" : "No commit message available."
    def projectName = env.JOB_NAME

    slackSend (
        channel: "${env.SLACK_CHANNEL}",
        color: jobResult == 'SUCCESS' ? 'good' : 'danger',
        message: """\
*:rocket: Jenkins Build Notification :rocket:*

*Project:* `${projectName}`
*Build Number:* `#${env.BUILD_NUMBER}`
*Status:* ${jobResult == 'SUCCESS' ? ':white_check_mark: *Success*' : ':x: *Failure*'}

:information_source: ${messageDetail}
Triggered by: ${env.TRIGGERED_BY}
:link: *Build URL:* <${jobUrl}|View Build Details>
"""
    )
}