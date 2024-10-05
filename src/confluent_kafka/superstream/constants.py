import os


class SdkInfo:
    VERSION = "2.4.0.3"
    LANGUAGE = "python"


class NatsValues:
    INFINITE_RECONNECT_ATTEMPTS = -1


class SuperstreamKeys:
    LEARNING_FACTOR = "superstream.learning.factor"
    TAGS = "superstream.tags"
    HOST = "superstream.host"
    TOKEN = "superstream.token"
    REDUCTION_ENABLED = "superstream.reduction.enabled"
    CONNECTION = "superstream.connection"
    INNER_CONSUMER = "superstream.inner.consumer"
    METADATA_TOPIC = "superstream.metadata"


class SuperstreamValues:
    MAX_TIME_WAIT_CAN_START = 60 * 10  # in seconds
    DEFAULT_SUPERSTREAM_TIMEOUT = 3000  # in milliseconds
    OPTIMIZED_CONFIGURATION_KEY = "optimized_configuration"
    INTERNAL_USERNAME = "superstream_internal"

    START_KEY = "start"
    ERROR_KEY = "error"


class SuperstreamSubjects:
    CLIENT_CONFIG_UPDATE = "internal.clientConfigUpdate"
    CLIENT_RECONNECTION_UPDATE = "internal_tasks.clientReconnectionUpdate"
    CLIENT_TYPE_UPDATE = "internal.clientTypeUpdate"
    REGISTER_CLIENT = "internal.registerClient"
    LEARN_SCHEMA = "internal.schema.learnSchema.%s"
    CLIENTS_UPDATE = "internal_tasks.clientsUpdate.%s.%s"
    CLIENT_ERRORS = "internal.clientErrors"
    GET_SCHEMA = "internal.schema.getSchema.%s"
    UPDATES = "internal.updates.%s"
    REGISTER_SCHEMA = "internal_tasks.schema.registerSchema.%s"
    START_CLIENT = "internal.startClient.%s"


class EnvVarsMeta(type):
    @property
    def SUPERSTREAM_HOST(cls) -> str:
        return os.getenv("SUPERSTREAM_HOST")

    @property
    def SUPERSTREAM_TOKEN(cls) -> str:
        return os.getenv("SUPERSTREAM_TOKEN", "no-auth")

    @property
    def SUPERSTREAM_LEARNING_FACTOR(cls) -> int:
        return int(os.getenv("SUPERSTREAM_LEARNING_FACTOR", 20))

    @property
    def SUPERSTREAM_TAGS(cls) -> str:
        return os.getenv("SUPERSTREAM_TAGS", "")

    @property
    def SUPERSTREAM_DEBUG(cls) -> bool:
        return os.getenv("SUPERSTREAM_DEBUG", "False").lower() in ("true")

    @property
    def SUPERSTREAM_RESPONSE_TIMEOUT(cls) -> float:
        return float(os.getenv("SUPERSTREAM_RESPONSE_TIMEOUT", SuperstreamValues.DEFAULT_SUPERSTREAM_TIMEOUT))

    @property
    def SUPERSTREAM_REDUCTION_ENABLED(cls) -> bool:
        return os.getenv("SUPERSTREAM_REDUCTION_ENABLED", "") == "true"


class EnvVars(metaclass=EnvVarsMeta):
    pass


class KafkaProducerConfigKeys:
    BOOTSTRAP_SERVERS = "bootstrap.servers"
    COMPRESSION_CODEC = "compression.codec"
    COMPRESSION_TYPE = "compression.type"
