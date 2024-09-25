import asyncio
from typing import Any, Callable, Dict, Union

from confluent_kafka.superstream.constants import SuperstreamKeys
from confluent_kafka.superstream.core import Superstream
from confluent_kafka.superstream.types import SuperstreamClientType
from confluent_kafka.superstream.utils import (
    KafkaUtil,
    _try_convert_to_json,
    json_to_proto,
)


class SuperstreamProducerInterceptor:
    def __init__(self, config: Dict, producer_handler: Callable | None = None):
        self._compression_type = "zstd"
        self._superstream_config_ = Superstream.init_superstream_props(
            config, SuperstreamClientType.PRODUCER
        )
        self._producer_handler = producer_handler

    def set_producer_handler(self, producer_handler: Callable):
        self._producer_handler = producer_handler

    def set_full_configuration(self, config: Dict[str, Any]):
        full_config = KafkaUtil.enrich_producer_config(config)
        if self.superstream:
            self.superstream.set_full_client_configs(full_config)

    def wait_for_superstream_configs_sync(self, config: Dict[str, Any]) -> Dict[str, Any]:
        if self.superstream:
            return self.superstream.wait_for_superstream_configs_sync(config)
        return config

    @property
    def superstream(self) -> Superstream:
        return self._superstream_config_.get(SuperstreamKeys.CONNECTION)

    def produce(self, *args, **kwargs):
        topic_idx = 0
        value_idx = 1
        partition_idx = 3
        on_delivery_idx = 4
        headers_index = 6

        superstream: Superstream = self._superstream_config_.get(
            SuperstreamKeys.CONNECTION
        )
        if not superstream:
            self._producer_handler(*args, **kwargs)
            return

        topic = args[topic_idx]
        if len(args) > partition_idx or "partition" in kwargs:
            partition = (
                args[partition_idx]
                if len(args) > partition_idx
                else kwargs.get("partition")
            )
            superstream.update_topic_partitions(topic, partition)

        if not superstream.superstream_ready:
            self._producer_handler(*args, **kwargs)
            return

        msg = args[value_idx] if len(args) > value_idx else kwargs.get("value")
        json_msg = _try_convert_to_json(msg)
        if json_msg is None:
            self._producer_handler(*args, **kwargs)
            return

        serialized_msg, superstream_headers = self._serialize(json_msg)

        if superstream_headers is not None:
            if len(args) > headers_index:
                if args[headers_index] is None:
                    args[headers_index] = superstream_headers
                elif isinstance(args[headers_index], dict):
                    args[headers_index].update(superstream_headers)
                elif isinstance(args[headers_index], list):
                    args[headers_index].extend(list(superstream_headers.items()))
            else:
                if kwargs.get("headers") is None:
                    kwargs["headers"] = superstream_headers
                elif isinstance(kwargs["headers"], dict):
                    kwargs["headers"].update(superstream_headers)
                elif isinstance(kwargs["headers"], list):
                    kwargs["headers"].extend(list(superstream_headers.items()))

        if len(args) > value_idx:
            args = args[:value_idx] + (serialized_msg,) + args[value_idx + 1 :]
        elif "value" in kwargs:
            kwargs["value"] = serialized_msg

        if len(args) > on_delivery_idx:
            original_on_delivery_cb = args[on_delivery_idx]
        if "on_delivery" in kwargs:
            original_on_delivery_cb = kwargs["on_delivery"]

        def updated_on_delivery_cb(err, msg):
            if err:
                original_on_delivery_cb(err, msg)
            else:
                topic = msg.topic()
                partition = msg.partition()
                superstream.update_topic_partitions(topic, partition)
                original_on_delivery_cb(err, msg)

        if len(args) > on_delivery_idx:
            args = (
                args[:on_delivery_idx]
                + (updated_on_delivery_cb,)
                + args[on_delivery_idx + 1 :]
            )
        elif "on_delivery" in kwargs:
            kwargs["on_delivery"] = updated_on_delivery_cb

        self._producer_handler(*args, **kwargs)

    def _serialize(self, json_msg: str) -> Union[bytes, Dict[str, Any]]:
        superstream: Superstream = self._superstream_config_.get(
            SuperstreamKeys.CONNECTION
        )
        byte_msg = json_msg.encode("utf-8")
        headers: Dict[str, Any] = {}

        # superstream.client_counters.total_bytes_before_reduction += len(byte_msg)

        if superstream.producer_proto_desc and superstream.reduction_enabled:
            try:
                byte_msg = json_to_proto(byte_msg, superstream.producer_proto_desc)
                # superstream.client_counters.total_messages_successfully_produce += 1
                headers = {"superstream_schema": superstream.producer_schema_id}
            except Exception as e:
                superstream.handle_error(f"error serializing data: {e}")
                # superstream.client_counters.total_messages_failed_produce += 1
                return byte_msg, headers
        
        elif superstream.reduction_enabled:
            try:
                if superstream.learning_factor_counter <= superstream.learning_factor:
                    asyncio.run(superstream.send_learning_message(byte_msg))
                    superstream.learning_factor_counter += 1
                elif not superstream.learning_request_sent:
                    asyncio.run(superstream.send_register_schema_req())
            except Exception as e:
                asyncio.run(superstream.handle_error(f"error sending learning message: {e}"))
                
        return byte_msg, headers
