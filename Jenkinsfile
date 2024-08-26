
pipeline {

    agent {
        // docker {
            label 'memphis-jenkins-big-fleet,'
        //     image 'python:3.11.9'
        //     args '-u root'
        // }
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
               sh "sudo yum install -y epel-release"
            //    sh "sudo yum install -y https://repo.ius.io/ius-release-el7.rpm"
               sh "sudo yum install -y python3.11 python3.11-pip"
               sh "sudo alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1"
               sh "python3 --version"
               sh "sudo yum install -y python3 python3-pip python3-devel gcc make cyrus-sasl-gssapi krb5-workstation"
               sh "sudo rpm --import https://packages.confluent.io/rpm/7.0/archive.key"
                sh '''
                    # Get release version and architecture
                    releasever=$(rpm -E %centos)
                    basearch=$(uname -m)
                    
                    # Write the Confluent repository file with actual values
                    sudo tee /etc/yum.repos.d/confluent.repo <<EOF
                [Confluent-Clients]
                name=Confluent Clients repository
                baseurl=https://packages.confluent.io/clients/rpm/centos/$releasever/$basearch
                gpgcheck=1
                gpgkey=https://packages.confluent.io/clients/rpm/archive.key
                enabled=1
                EOF
                '''
                sh "cat /etc/yum.repos.d/confluent.repo"
                sh "sudo yum install -y librdkafka-devel"
                sh "sudo python3 -m pip install --no-binary confluent-kafka confluent-kafka"
                sh "sudo python3 -c 'import confluent_kafka; print(confluent_kafka.version())'"

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