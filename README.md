# Superstream Python Kafka package

- Superstream Python package is a replacement for [confluent-kafka](https://github.com/confluentinc/confluent-kafka-python) package.
- Your app can only use one of the packages at a time. Adding both to the same app will cause the Superstream package to be ignored.
- To use the Superstream package in your app, it must be the sole package in use.

## Installation
### Step 1: Package installation

**Using pip**

    $ pip install superstream-confluent-kafka

**NOTE:** You must install `librdkafka` and its dependencies using
          the repositories below.

**Install `librdkafka` on Mac OS**
```bash
# Install librdkafka from homebrew
brew install librdkafka

# Add the following paths if needed
export C_INCLUDE_PATH="/opt/homebrew/include"
export LIBRARY_PATH="/opt/homebrew/lib"
```

**Install `librdkafka` on RedHat, CentOS, Fedora, etc**
```bash
#
# Perform these steps as the root user (e.g., in a 'sudo bash' shell)
#

# Install build tools if needed.
yum install -y python3 python3-pip python3-devel gcc make

# Install the latest version of librdkafka:
rpm --import https://packages.confluent.io/rpm/7.0/archive.key

echo '
[Confluent-Clients]
name=Confluent Clients repository
baseurl=https://packages.confluent.io/clients/rpm/centos/$releasever/$basearch
gpgcheck=1
gpgkey=https://packages.confluent.io/clients/rpm/archive.key
enabled=1' > /etc/yum.repos.d/confluent.repo

yum install -y librdkafka-devel
```

**Install `librdkafka` on Debian or Ubuntu**
```bash
#
# Perform these steps as the root user (e.g., in a 'sudo bash' shell)
#

# Install build tools.

apt install -y software-properties-common lsb-release gcc make python3 python3-pip python3-dev

# Install the latest version of librdkafka:

wget -qO - https://packages.confluent.io/deb/7.0/archive.key | apt-key add -

add-apt-repository "deb https://packages.confluent.io/clients/deb $(lsb_release -cs) main"

apt update

apt install -y librdkafka-dev
```

### Step 2: Configuration

To fully utilize the Superstream package's capabilities, it is essential to set the environment variables provided in the table below before initializing the package. 
The Superstream package will function as a standard confluent-kafka package in the following scenarios:
- When a required environment variable is not configured
- If Superstream becomes unresponsive

**A required env var/s to set**
| Environment Variable                | Default          | Example  | Required  | Description                                                                                           |
|-------------------------------------|------------------|-----------|-----------|-------------------------------------------------------------------------------------------------------|
| `SUPERSTREAM_HOST`                  | -                | engine.superstream.org.com       | Yes       | Specify the host URL of the Superstream service to connect to the appropriate Superstream environment. |

**Optional env var/s for enhanced capabilities**

| Environment Variable                | Default          | Example  | Required  | Description                                                                                           |
|-------------------------------------|------------------|-----------|-----------|-------------------------------------------------------------------------------------------------------|
| `SUPERSTREAM_TOKEN`                 | -                | 096cc4891d91034272fbc3dae2a53ad4       | No        | This authentication token is required when the engine is configured to work with local authentication, to securely access the Superstream services. |
| `SUPERSTREAM_TAGS`                  | -     | {"config":"dev","owner":"bi_app"}       | No        | Set this variable to tag the client. This value of this variable should be a valid JSON string.            |
| `SUPERSTREAM_DEBUG`                 | False            | True       | No        | Set this variable to true to enable Superstream logs. By default, there will not be any Superstream related logs. |
| `SUPERSTREAM_RESPONSE_TIMEOUT`       | 3000            | Yes       | No        | Set this variable to specify a timeout in milliseconds to wait for the Superstream service response.         |

### Step 3: Validation


### Basic Producer Example

```python
from confluent_kafka import Producer

p = Producer({'bootstrap.servers': 'mybroker1,mybroker2'})

def delivery_report(err, msg):
    """ Called once for each message produced to indicate delivery result.
        Triggered by poll() or flush(). """
    if err is not None:
        print('Message delivery failed: {}'.format(err))
    else:
        print('Message delivered to {} [{}]'.format(msg.topic(), msg.partition()))

for data in some_data_source:
    # Trigger any available delivery report callbacks from previous produce() calls
    p.poll(0)

    # Asynchronously produce a message. The delivery report callback will
    # be triggered from the call to poll() above, or flush() below, when the
    # message has been successfully delivered or failed permanently.
    p.produce('mytopic', data.encode('utf-8'), callback=delivery_report)

# Wait for any outstanding messages to be delivered and delivery report
# callbacks to be triggered.
p.flush()
```

For a discussion on the poll based producer API, refer to the
[Integrating Apache Kafka With Python Asyncio Web Applications](https://www.confluent.io/blog/kafka-python-asyncio-integration/)
blog post.


### Basic Consumer Example

```python
from confluent_kafka import Consumer

c = Consumer({
    'bootstrap.servers': 'mybroker',
    'group.id': 'mygroup',
    'auto.offset.reset': 'earliest'
})

c.subscribe(['mytopic'])

while True:
    msg = c.poll(1.0)

    if msg is None:
        continue
    if msg.error():
        print("Consumer error: {}".format(msg.error()))
        continue

    print('Received message: {}'.format(msg.value().decode('utf-8')))

c.close()
```

## Developer Notes

Instructions on building and testing confluent-kafka-python can be found [here](DEVELOPER.md).


## Confluent Cloud

For a step-by-step guide on using the Python client with Confluent Cloud see [Getting Started with Apache Kafka and Python](https://developer.confluent.io/get-started/python/) on [Confluent Developer](https://developer.confluent.io/). 
