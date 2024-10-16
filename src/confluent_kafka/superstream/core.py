import asyncio
import base64
import json
import socket
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Union

import nats
from google.protobuf.descriptor import Descriptor
from nats.aio.client import Client as NatsClient
from nats.errors import Error as NatsError
from nats.js import JetStreamContext

from confluent_kafka.superstream.constants import (
    EnvVars,
    NatsValues,
    SdkInfo,
    SuperstreamKeys,
    SuperstreamSubjects,
    SuperstreamValues,
)
from confluent_kafka.superstream.exceptions import ErrGenerateConnectionId
from confluent_kafka.superstream.factory import SuperstreamFactory
from confluent_kafka.superstream.std import SuperstreamStd
from confluent_kafka.superstream.types import (
    ClientConfigUpdateReq,
    ClientCounterUpdateRequest,
    ClientReconnectionUpdateReq,
    ClientTypeUpdateReq,
    CompressionUpdate,
    GetSchemaReq,
    LearnedSchemaUpdate,
    RegisterReq,
    RegisterResp,
    SchemaUpdateReq,
    SuperstreamClientType,
    SuperstreamCounters,
    ToggleReductionUpdate,
    TopicsPartitionsPerProducerConsumer,
    Update,
)
from confluent_kafka.superstream.update_manager import SuperstreamUpdateManager
from confluent_kafka.superstream.utils import (
    KafkaUtil,
    TaskUtil,
    _name,
    compile_descriptor,
)


class Superstream:
    learning_factor_counter: int
    learning_request_sent: bool
    get_schema_request_sent: bool
    consumer_proto_desc_map: Dict[str, Descriptor]

    # required properties
    account_name: str

    learning_factor: int
    token: str
    host: str
    configs: Dict[str, Any]
    client_type: str
    tags: str
    compression_type: str = "zstd"
    client_counters: SuperstreamCounters
    topic_partitions: Dict[str, List[int]]

    client_ip: str
    client_host: str
    client_hash: str
    broker_connection: NatsClient
    jetstream: JetStreamContext
    nats_connection_id: str

    superstream_ready = False
    can_start = False

    update_manager: SuperstreamUpdateManager
    producer_proto_desc: Optional[Descriptor]
    producer_schema_id: str

    start_sub: Any

    std: SuperstreamStd

    full_client_configs: Dict[str, Any]
    superstream_configs: Dict[str, Any]
    kafka_connection_id: int

    def __init__(
        self,
        token: str,
        host: str,
        learning_factor: int,
        configs: Dict[str, Any],
        enable_reduction: bool,
        client_type: str,
        tags: str = "",
    ):
        self.learning_factor = learning_factor
        self.token = token
        self.host = host
        self.reduction_enabled = enable_reduction
        self.client_type = client_type
        self.configs = configs
        self.tags = tags
        self.topic_partitions = {}
        self.std = SuperstreamStd()

        self.learning_factor_counter = 0
        self.learning_request_sent = False
        self.get_schema_request_sent = False
        self.producer_proto_desc = None

        self.consumer_proto_desc_map = {}
        self.client_counters = SuperstreamCounters()

        self.client_hash = None
        self.superstream_configs = {}
        self.optimized_config_received = False
        self._initial_topic_partition_update_sent = False

        self._config_update_cb = None

    async def _request(
        self,
        subject: str,
        payload: bytes,
        timeout: float = 30,
        timeout_retries: int = 1,
    ):
        """
        Send a request to the broker and wait for the response.
        :param timeout: Time to wait for the response. Default is 30 seconds.
        """
        try:
            res = await self.broker_connection.request(
                subject, payload, timeout=timeout
            )
            return res
        except Exception as e:
            if "timeout" not in str(e).lower() or timeout_retries <= 0:
                raise e
            return await self._request(
                subject, payload, timeout=timeout, timeout_retries=timeout_retries - 1
            )

    async def _send_client_errors_to_backend(self, err_msg: str):
        await self._publish(SuperstreamSubjects.CLIENT_ERRORS, err_msg.encode())

    async def _publish(self, subject: str, payload: bytes):
        await self.broker_connection.publish(subject, payload)

    async def _js_publish(self, subject: str, payload: bytes):
        await self.jetstream.publish(subject, payload)

    async def handle_error(self, msg: str):
        if self.broker_connection is None or not self.superstream_ready:
            return
        err_msg = f"[sdk: {SdkInfo.LANGUAGE}][version: {SdkInfo.VERSION}][tags: {self.tags}] {msg}"
        if self.client_hash is not None and self.client_hash != "":
            err_msg = f"[clientHash: {self.client_hash}] {err_msg}"
        await self._send_client_errors_to_backend(err_msg)

    async def send_register_schema_req(self):
        if self.learning_request_sent:
            return
        try:
            await self._publish(
                SuperstreamSubjects.REGISTER_SCHEMA % self.client_hash, b""
            )
            self.learning_request_sent = True
        except Exception as e:
            await self.handle_error(
                f"{_name(self.send_register_schema_req)} at publish {e!s}"
            )

    async def send_learning_message(self, msg: bytes):
        try:
            await self._publish(
                SuperstreamSubjects.LEARN_SCHEMA % self.client_hash, msg
            )
        except Exception as e:
            await self.handle_error(
                f"{_name(self.send_learning_message)} at publish {e!s}"
            )

    async def send_client_type_update_req(self):
        if not self.client_type:
            return

        if self.client_type not in [
            SuperstreamClientType.PRODUCER.value,
            SuperstreamClientType.CONSUMER.value,
            SuperstreamClientType.ADMIN.value,
        ]:
            return

        try:
            await self._publish(
                SuperstreamSubjects.CLIENT_TYPE_UPDATE,
                ClientTypeUpdateReq(client_hash=self.client_hash, type=self.client_type)
                .model_dump_json()
                .encode(),
            )
        except Exception as e:
            await self.handle_error(
                f"{_name(self.send_client_type_update_req)} at publish {e!s}"
            )

    async def wait_for_can_start(self):
        async def check_can_start():
            while not self.can_start:
                await asyncio.sleep(0.2)

        try:
            await asyncio.wait_for(
                check_can_start(), timeout=SuperstreamValues.MAX_TIME_WAIT_CAN_START
            )
            if not self.can_start:
                raise Exception("could not start within the expected timeout period")
        except Exception as e:
            self.std.error(f"superstream {e}")

    async def execute_send_client_config_update_req_with_wait(self):
        try:
            await self.wait_for_can_start()
            await self.send_client_config_update_req()
        except Exception as e:
            self.std.error(
                f"superstream: error sending client config update request: {e!s}"
            )

    def wait_for_superstream_configs_sync(self, config: Dict) -> Dict[str, Any]:
        config = config.copy() if config else {}

        timeout = (
            EnvVars.SUPERSTREAM_RESPONSE_TIMEOUT
            or SuperstreamValues.DEFAULT_SUPERSTREAM_TIMEOUT
        )
        end_time = datetime.now() + timedelta(milliseconds=timeout)

        try:
            while not self.optimized_config_received:
                if datetime.now() > end_time:
                    raise Exception(
                        "client configuration was not set within the expected timeout period"
                    )
                time.sleep(0.2)

            for key, value in self.superstream_configs.items():
                if self.client_type == SuperstreamClientType.PRODUCER.value:
                    if KafkaUtil.is_valid_producer_key(key):
                        config[key] = value
                elif self.client_type == SuperstreamClientType.CONSUMER.value:
                    if KafkaUtil.is_valid_consumer_key(key):
                        config[key] = value
            return config
        except Exception as e:
            self.std.error(f"superstream {e}")
            return config

    async def wait_for_superstream_configs(self, update_cb: Callable | None = None):
        async def check_superstream_configs():
            while not self.superstream_configs:
                await asyncio.sleep(0.2)

        timeout_ms = (
            EnvVars.SUPERSTREAM_RESPONSE_TIMEOUT
            or SuperstreamValues.DEFAULT_SUPERSTREAM_TIMEOUT
        )
        timeout = timeout_ms / 1000

        try:
            await asyncio.wait_for(check_superstream_configs(), timeout=timeout)
            if not self.superstream_configs:
                raise Exception(
                    "client configuration was not set within the expected timeout period"
                )

            if update_cb is None:
                return

            valid_configs = {}
            for key, value in self.superstream_configs.items():
                if self.client_type == SuperstreamClientType.PRODUCER.value:
                    if KafkaUtil.is_valid_producer_key(key):
                        valid_configs[key] = value
                elif self.client_type == SuperstreamClientType.CONSUMER.value:
                    if KafkaUtil.is_valid_consumer_key(key):
                        valid_configs[key] = value
            update_cb(valid_configs)
        except Exception as e:
            self.std.error(f"superstream {e}")

    async def _send_initial_topic_partitions_update(self):
        """
        Update the client's topic partitions with the superstream.
        This is used to update the client's topic partitions only once if there is no topic partition update sent by the client.
        This makes it faster to get topic and partition information of a client from the superstream.
        """
        try:
            topic_partition_payload = TopicsPartitionsPerProducerConsumer(
                producer_topics_partitions={},
                consumer_group_topics_partitions={},
                connection_id=self.kafka_connection_id,
            )
            if self.topic_partitions:
                topic_partition_payload = TopicsPartitionsPerProducerConsumer(
                    producer_topics_partitions=self.topic_partitions
                    if self.client_type == SuperstreamClientType.PRODUCER.value
                    else {},
                    consumer_group_topics_partitions=self.topic_partitions
                    if self.client_type == SuperstreamClientType.CONSUMER.value
                    else {},
                    connection_id=self.kafka_connection_id,
                )
            await self._publish(
                SuperstreamSubjects.CLIENTS_UPDATE % ("config", self.client_hash),
                topic_partition_payload.model_dump_json().encode(),
            )
            self._initial_topic_partition_update_sent = True
        except Exception as e:
            await self.handle_error(f"{_name(self.report_clients_update)}: {e!s}")

    async def report_clients_update(self):
        async def client_update_task():
            async def update_client_counters():
                backup_read_bytes = self.client_counters.get_total_read_bytes_reduced()
                backup_write_bytes = (
                    self.client_counters.get_total_write_bytes_reduced()
                )
                self.client_counters.reset()

                request = ClientCounterUpdateRequest.from_superstream_counters(
                    self.client_counters, self.kafka_connection_id
                )
                try:
                    await self._publish(
                        SuperstreamSubjects.CLIENTS_UPDATE
                        % ("counters", self.client_hash),
                        request.model_dump_json().encode(),
                    )
                except Exception as e:
                    self.client_counters.increment_total_read_bytes_reduced(
                        backup_read_bytes
                    )
                    self.client_counters.increment_total_write_bytes_reduced(
                        backup_write_bytes
                    )
                    await self.handle_error(
                        f"{_name(self.report_clients_update)} at publish {e!s}"
                    )

            async def update_client_topic_partitions():
                try:
                    topic_partition_payload = TopicsPartitionsPerProducerConsumer(
                        producer_topics_partitions={},
                        consumer_group_topics_partitions={},
                        connection_id=self.kafka_connection_id,
                    )
                    if self.topic_partitions:
                        topic_partition_payload = TopicsPartitionsPerProducerConsumer(
                            producer_topics_partitions=self.topic_partitions
                            if self.client_type == SuperstreamClientType.PRODUCER.value
                            else {},
                            consumer_group_topics_partitions=self.topic_partitions
                            if self.client_type == SuperstreamClientType.CONSUMER.value
                            else {},
                            connection_id=self.kafka_connection_id,
                        )
                    await self._publish(
                        SuperstreamSubjects.CLIENTS_UPDATE
                        % ("config", self.client_hash),
                        topic_partition_payload.model_dump_json().encode(),
                    )

                except Exception as e:
                    await self.handle_error(
                        f"{_name(self.report_clients_update)}: {e!s}"
                    )

            if not self.broker_connection or not self.superstream_ready:
                return

            # await update_client_counters()
            await update_client_topic_partitions()

        async def start_periodic_task(interval, update_task):
            async def task_wrapper():
                while True:
                    await update_task()
                    await asyncio.sleep(interval)

            TaskUtil.create_task(task_wrapper())

        await start_periodic_task(10 * 60, client_update_task)

    def _compile_descriptor(
        self,
        descriptor: Union[str, bytes],
        msg_struct_name: str,
        file_name: str,
    ):
        try:
            return compile_descriptor(descriptor, msg_struct_name, file_name)
        except Exception as e:
            self.std.write(
                f"{_name(self._compile_descriptor)} at compile_descriptor {e!s}"
            )
            raise e

    async def send_get_schema_request(self, schema_id: str):
        req_bytes = GetSchemaReq(schema_id=schema_id).model_dump_json().encode()

        try:
            msg = await self._request(
                SuperstreamSubjects.GET_SCHEMA % self.client_hash, req_bytes, 30
            )
            resp = SchemaUpdateReq.model_validate_json(msg.data)
            desc = self._compile_descriptor(
                resp.desc, resp.master_msg_name, resp.file_name
            )
            if desc is not None:
                self.consumer_proto_desc_map[resp.schema_id] = desc
            else:
                await self.handle_error(
                    f"{_name(self.send_get_schema_request)}: error compiling schema"
                )
                raise Exception("superstream: error compiling schema")
        except Exception as e:
            await self.handle_error(
                f"{_name(self.send_get_schema_request)} at request {e!s}"
            )

    async def send_client_config_update_req(self):
        try:
            full_config = self.full_client_configs.copy()
            if full_config.get(SuperstreamKeys.CONNECTION):
                full_config.pop(SuperstreamKeys.CONNECTION)
            req = ClientConfigUpdateReq(
                client_hash=self.client_hash, config=full_config
            )
            await self._publish(
                SuperstreamSubjects.CLIENT_CONFIG_UPDATE, req.model_dump_json().encode()
            )
        except Exception as e:
            await self.handle_error(
                f"{_name(self.send_client_config_update_req)} at publish {e!s}"
            )

    async def register_client(self):
        def populate_config_to_send(configs):
            config_to_send = {}
            if configs:
                for key, value in configs.items():
                    if key.lower() not in (SuperstreamKeys.CONNECTION.lower()):
                        config_to_send[key] = value
            return config_to_send

        try:
            kafka_id = self.consume_latest_connection_id()
            if kafka_id:
                try:
                    kafka_id = int(kafka_id)
                except Exception:
                    kafka_id = 0
            else:
                kafka_id = 0

            self.kafka_connection_id = kafka_id
            local_host = socket.gethostbyname(socket.gethostname())
            self.client_ip = local_host
            self.client_host = socket.gethostname()

            register_req = RegisterReq(
                nats_connection_id=self.nats_connection_id,
                language=SdkInfo.LANGUAGE,
                version=SdkInfo.VERSION,
                learning_factor=self.learning_factor,
                config=populate_config_to_send(self.configs),
                reduction_enabled=self.reduction_enabled,
                connection_id=kafka_id,
                tags=self.tags,
                client_ip=self.client_ip,
                client_host=self.client_host,
            )

            try:
                register_req_bytes = register_req.model_dump_json().encode()
                sub = SuperstreamSubjects.REGISTER_CLIENT
                resp = await self._request(sub, register_req_bytes, 60 * 5)
                register_resp = RegisterResp.model_validate_json(resp.data)
            except Exception as e:
                raise Exception("superstream: error registering client") from e

            if not register_resp:
                err = "superstream: registering client: No reply received within the timeout period."
                self.std.write(err)
                self.handle_error(err)
                return

            self.client_hash = register_resp.client_hash
            self.account_name = register_resp.account_name
            self.learning_factor = register_resp.learning_factor
            self.learning_factor_counter = 0
            self.learning_request_sent = False
            self.get_schema_request_sent = False
            self.consumer_proto_desc_map = {}

        except Exception as e:
            self.std.error(f"superstream: {e!s}")

    def consume_latest_connection_id(self) -> str:
        retries = 2
        try:
            config = KafkaUtil.copy_auth_config(self.configs)
            config.update(
                {
                    "group.id": f"superstream-consumer-group-{uuid.uuid4()}",
                    "enable.auto.commit": False,
                }
            )
            topic = SuperstreamKeys.METADATA_TOPIC
            c = SuperstreamFactory.create_consumer(config)
            partitions = c.list_topics().topics[topic].partitions
            if not partitions:
                return "0"
            topic_partitions = [
                SuperstreamFactory.create_topic_partition(topic, partition)
                for partition in partitions
            ]
            end_offsets = [c.get_watermark_offsets(tp) for tp in topic_partitions]
            topic_partitions = [
                SuperstreamFactory.create_topic_partition(
                    topic, p, offset=end_offset[1] - 1
                )
                for p, end_offset in zip(partitions, end_offsets)
            ]

            c.assign(topic_partitions)
            while retries > 0:
                msg = c.poll(timeout=10.0)
                if msg is None or msg.error():
                    retries -= 1
                    continue

                return msg.value().decode("utf-8")

        except Exception as e:
            self.std.write(f"{_name(self.consume_latest_connection_id)}: {e!s}")
            return "0"
        finally:
            if c:
                c.close()

    def _generate_nats_connection_id(self) -> str:
        try:
            cid = self.broker_connection.client_id
            server_name = self.broker_connection._server_info.get("server_name")
            return f"{server_name}:{cid}"
        except Exception as e:
            raise ErrGenerateConnectionId(e) from e

    async def _init_nats_connection(self, token: str, host: Union[str, List[str]]):
        async def on_reconnected():
            local_connection_id = ""
            try:
                local_connection_id = self._generate_nats_connection_id()
                payload = (
                    ClientReconnectionUpdateReq(
                        new_nats_connection_id=local_connection_id,
                        client_hash=self.client_hash,
                    )
                    .model_dump_json()
                    .encode()
                )
                await self._request(
                    SuperstreamSubjects.CLIENT_RECONNECTION_UPDATE, payload
                )
                await self.subscribe_to_updates()
                self.superstream_ready = True
                await self.report_clients_update()
                self.std.write("superstream: reconnected to superstream")
            except ErrGenerateConnectionId as e:
                await self._handle_error(
                    f"{_name(self._init_nats_connection)} at {_name(self._generate_nats_connection_id)}: {e!s}"
                )
                return
            except Exception as e:
                await self._handle_error(
                    f"{_name(self._init_nats_connection)} at broker connection request: {e!s}"
                )
                return
            self.nats_connection_id = local_connection_id

        async def disconnect_cb():
            self.jetstream = None
            self.nats_connection_id = ""
            self.superstream_ready = False
            self.std.error("superstream: disconnected from superstream")

        async def error_cb(e: NatsError):
            """
            Error callback for NATS connection errors.
            It does nothing. Its purpose is to override the NATS default error callback that prints the error to the console on every reconnect attempt.
            """
            if e is None:
                return
            critical_errors = [
                "invalid checksum",
                "nats: maximum account",
                "authorization violation",
            ]
            for error in critical_errors:
                if error.lower() in str(e).lower():
                    raise e

        try:
            self.broker_connection = await nats.connect(
                max_reconnect_attempts=NatsValues.INFINITE_RECONNECT_ATTEMPTS,
                reconnect_time_wait=1,  # in seconds
                connect_timeout=10,  # in seconds
                user=SuperstreamValues.INTERNAL_USERNAME,
                password=token,
                servers=host,
                reconnected_cb=on_reconnected,
                error_cb=error_cb,
                disconnected_cb=disconnect_cb,
            )
            self.jetstream = self.broker_connection.jetstream()
            self.nats_connection_id = self._generate_nats_connection_id()
        except Exception as exception:
            if "nats: maximum account" in str(exception):
                raise Exception(
                    "Cannot connect with superstream since you have reached the maximum amount of connected clients"
                ) from exception
            elif "invalid checksum" in str(exception):
                raise Exception(
                    "Error connecting with superstream: unauthorized"
                ) from exception
            else:
                raise Exception(
                    f"Error connecting with superstream: {exception!s}"
                ) from exception

    async def wait_for_start(self):
        subject = SuperstreamSubjects.START_CLIENT % self.client_hash

        async def start_cb(msg):
            try:
                message_data = json.loads(msg.data)
                if SuperstreamValues.START_KEY in message_data:
                    if message_data[SuperstreamValues.START_KEY]:
                        self.can_start = True
                        self.optimized_config_received = True
                        if (
                            SuperstreamValues.OPTIMIZED_CONFIGURATION_KEY
                            in message_data
                        ):
                            self.superstream_configs = message_data[
                                SuperstreamValues.OPTIMIZED_CONFIGURATION_KEY
                            ]
                    else:
                        err = message_data.get(SuperstreamValues.ERROR_KEY, "")
                        raise Exception(err)
            except Exception as e:
                self.std.error(f"superstream: Could not start superstream: {e}")

        async def is_started():
            while not self.can_start:
                await asyncio.sleep(0.2)

        subscription = None
        try:
            subscription = await self.broker_connection.subscribe(subject, cb=start_cb)
            await asyncio.wait_for(
                is_started(), timeout=SuperstreamValues.MAX_TIME_WAIT_CAN_START
            )
            if not self.can_start:
                self.std.error(
                    "superstream: Could not connect to superstream for 10 minutes."
                )
        except Exception as e:
            self.std.error(f"superstream: Could not start superstream: {e}")
            raise e
        finally:
            if subscription is not None:
                await subscription.unsubscribe()

    def set_config_update_cb(self, cb: Callable):
        self._config_update_cb = cb

    def process_update(self, update: Update):
        LEARNED_SCHEMA = "LearnedSchema"
        TOGGLE_REDUCTION = "ToggleReduction"
        COMPRESSION_UPDATE = "CompressionUpdate"

        def learned_schema_handler(payload: bytes):
            schema_update = LearnedSchemaUpdate.model_validate_json(payload)
            descriptor = compile_descriptor(
                schema_update.desc,
                schema_update.master_msg_name,
                schema_update.file_name,
            )
            if descriptor:
                self.producer_proto_desc = descriptor
                self.producer_schema_id = schema_update.schema_id
            else:
                raise Exception("superstream: error compiling descriptor")

        def toggle_reduction_handler(payload: bytes):
            reduction_update = ToggleReductionUpdate.model_validate_json(payload)
            self.reduction_enabled = reduction_update.enable_reduction

        def compression_update_handler(payload: bytes):
            try:
                compression_update = CompressionUpdate.model_validate_json(payload)
                if compression_update.compression_type:
                    if not KafkaUtil.is_valid_compression_type(
                        compression_update.compression_type
                    ):
                        raise Exception(
                            f"invalid compression type: {compression_update.compression_type}"
                        )

                    self.compression_type = compression_update.compression_type
                    new_config = KafkaUtil.extract_producer_config(self.configs)
                    compression_config = KafkaUtil.get_compression_config(
                        self.compression_type, new_config
                    )
                    new_config.update(compression_config)
                    if self._config_update_cb:
                        self.std.write(
                            f"superstream: updating producer config with compression type: {self.compression_type}"
                        )
                        self._config_update_cb(new_config)
            except Exception as e:
                self.std.error(
                    f"superstream: error processing compression update: {e!s}"
                )

        handlers = {
            LEARNED_SCHEMA: learned_schema_handler,
            TOGGLE_REDUCTION: toggle_reduction_handler,
            COMPRESSION_UPDATE: compression_update_handler,
        }
        try:
            update_type, update_bytes = update.type, base64.b64decode(update.payload)
            handler = handlers.get(update_type)
            if handler:
                handler(update_bytes)
        except Exception as e:
            self.handle_error(f"{_name(self.process_update)}: {e!s}")

    async def subscribe_to_updates(self):
        try:
            subject = SuperstreamSubjects.UPDATES % self.client_hash
            self.update_manager = SuperstreamUpdateManager(
                client_hash=self.client_hash,
                error_handler=self.handle_error,
                process_update_cb=self.process_update,
            )

            # ruff: noqa: RUF006
            TaskUtil.create_task(self.update_manager.listen_update())

            self.update_manager.subscription = await self.broker_connection.subscribe(
                subject, cb=self.update_manager.update_handler
            )

        except Exception as e:
            self.std.error(f"superstream: Could not subscribe to updates: {e}")

    def update_topic_partitions(self, topic: str, partition: int):
        self.topic_partitions[topic] = self.topic_partitions.get(topic, [])
        if partition not in self.topic_partitions[topic]:
            self.topic_partitions[topic].append(partition)

        if self.topic_partitions and not self._initial_topic_partition_update_sent:
            TaskUtil.create_task(self._send_initial_topic_partitions_update())

    def set_full_client_configs(self, full_client_configs: Dict[str, Any]):
        self.full_client_configs = full_client_configs
        TaskUtil.create_task(self.execute_send_client_config_update_req_with_wait())


    async def init(self):
        try:
            await self._init_nats_connection(self.token, self.host)
            if not self.broker_connection:
                raise Exception("superstream: Could not connect to superstream")

            await self.register_client()
            await self.wait_for_start()
            assert self.can_start, "superstream: Could not start superstream"

            self.std.write("Successfully connected to superstream")

            await self.subscribe_to_updates()
            self.superstream_ready = True
            await self.report_clients_update()
            await self.send_client_type_update_req()
        except Exception as e:
            await self.handle_error(
                f"superstream: error initializing superstream: {e!s}"
            )

    def init_superstream_props(
        props: Dict[str, Any], client_type: SuperstreamClientType
    ) -> Dict[str, Any]:
        props = props.copy()
        try:
            assert EnvVars.SUPERSTREAM_HOST, "superstream host is required"

            superstream = Superstream(
                token=EnvVars.SUPERSTREAM_TOKEN,
                host=EnvVars.SUPERSTREAM_HOST,
                learning_factor=EnvVars.SUPERSTREAM_LEARNING_FACTOR,
                configs=props,
                enable_reduction=EnvVars.SUPERSTREAM_REDUCTION_ENABLED,
                client_type=client_type.value,
                tags=EnvVars.SUPERSTREAM_TAGS,
            )

            def run_event_loop(loop):
                asyncio.set_event_loop(loop)
                try:
                    loop.run_forever()
                except Exception as e:
                    sys.stderr.write(f"superstream: error running event loop: {e!s}")
                finally:
                    loop.close()

            def init_in_background(task):
                new_loop = asyncio.new_event_loop()
                t = threading.Thread(target=run_event_loop, args=(new_loop,))
                t.start()
                asyncio.run_coroutine_threadsafe(task, new_loop)
                return new_loop, t

            init_in_background(superstream.init())

            props.update(
                {
                    SuperstreamKeys.HOST: EnvVars.SUPERSTREAM_HOST,
                    SuperstreamKeys.TOKEN: EnvVars.SUPERSTREAM_TOKEN,
                    SuperstreamKeys.LEARNING_FACTOR: EnvVars.SUPERSTREAM_LEARNING_FACTOR,
                    SuperstreamKeys.REDUCTION_ENABLED: EnvVars.SUPERSTREAM_REDUCTION_ENABLED,
                    SuperstreamKeys.TAGS: EnvVars.SUPERSTREAM_TAGS,
                    SuperstreamKeys.CONNECTION: superstream,
                }
            )

        except Exception as e:
            SuperstreamStd().write(
                f"superstream: error initializing superstream: {e!s}"
            )

        return props

    def init_superstream_config(
        props: Dict[str, Any], client_type: SuperstreamClientType
    ) -> Dict[str, Any]:
        props = props.copy()
        try:
            assert EnvVars.SUPERSTREAM_HOST, "superstream host is required"

            superstream = Superstream(
                token=EnvVars.SUPERSTREAM_TOKEN,
                host=EnvVars.SUPERSTREAM_HOST,
                learning_factor=EnvVars.SUPERSTREAM_LEARNING_FACTOR,
                configs=props,
                enable_reduction=EnvVars.SUPERSTREAM_REDUCTION_ENABLED,
                client_type=client_type.value,
                tags=EnvVars.SUPERSTREAM_TAGS,
            )

            def run_event_loop(loop):
                asyncio.set_event_loop(loop)
                try:
                    loop.run_forever()
                except Exception as e:
                    sys.stderr.write(f"superstream: error running event loop: {e!s}")
                finally:
                    loop.close()

            def init_in_background(task):
                new_loop = asyncio.new_event_loop()
                t = threading.Thread(target=run_event_loop, args=(new_loop,))
                t.start()
                asyncio.run_coroutine_threadsafe(task, new_loop)
                return new_loop, t

            init_in_background(superstream.init())

            props.update(
                {
                    SuperstreamKeys.HOST: EnvVars.SUPERSTREAM_HOST,
                    SuperstreamKeys.TOKEN: EnvVars.SUPERSTREAM_TOKEN,
                    SuperstreamKeys.LEARNING_FACTOR: EnvVars.SUPERSTREAM_LEARNING_FACTOR,
                    SuperstreamKeys.REDUCTION_ENABLED: EnvVars.SUPERSTREAM_REDUCTION_ENABLED,
                    SuperstreamKeys.TAGS: EnvVars.SUPERSTREAM_TAGS,
                    SuperstreamKeys.CONNECTION: superstream,
                }
            )

        except Exception as e:
            SuperstreamStd().write(
                f"superstream: error initializing superstream: {e!s}"
            )

        return props

    def close(self):
        try:
            self.std.flush()
            if self.broker_connection:
                self.broker_connection.close()
        except Exception:
            pass
