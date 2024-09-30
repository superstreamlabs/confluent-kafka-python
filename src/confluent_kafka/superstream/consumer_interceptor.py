import asyncio
import sys
import time
from typing import Any, Dict, List, Optional

from confluent_kafka.superstream.constants import SuperstreamKeys
from confluent_kafka.superstream.core import Superstream
from confluent_kafka.superstream.types import SuperstreamClientType
from confluent_kafka.superstream.utils import KafkaUtil, proto_to_json


class SuperstreamConsumerInterceptor:
    def __init__(self, config: Dict):
        self._superstream_config_ = Superstream.init_superstream_props(config, SuperstreamClientType.CONSUMER)

    def set_full_configuration(self, config: Dict[str, Any]):
        full_config = KafkaUtil.enrich_consumer_config(config)
        if self.superstream:
            self.superstream.set_full_client_configs(full_config)

    @property
    def superstream(self) -> Superstream:
        return self._superstream_config_.get(SuperstreamKeys.CONNECTION)
    
    def wait_for_superstream_configs_sync(self, config: Dict[str, Any]) -> Dict[str, Any]:
        if self.superstream:
            return self.superstream.wait_for_superstream_configs_sync(config)
        return config

    def __update_topic_partitions(self, message):
        if self.superstream is None:
            return
        topic = message.topic()
        partition = message.partition()
        self.superstream.update_topic_partitions(topic, partition)

    def poll(self, message) -> Any:
        if message is None:
            return message
        return self.__intercept(message)

    def consume(self, messages) -> Optional[List[Any]]:
        if messages is None:
            return messages
        return [self.__intercept(message) for message in messages]

    def __intercept(self, message: Any) -> Any:
        if not message:
            return message
        self.__update_topic_partitions(message)
        try:
            return asyncio.run(self.__deserialize(message))
        except Exception:
            return message

    async def __deserialize(self, message: Any) -> Any:
        message_value = message.value()
        headers = message.headers()

        if not headers or not message_value:
            return message

        # superstream.client_counters.total_bytes_after_reduction += len(message_value)
        schema_id = None
        for key, value in headers:
            if key == "superstream_schema":
                schema_id = value.decode("utf-8") if isinstance(value, bytes) else value
                break

        if not schema_id:
            # if superstream.superstream_ready:
            #   superstream.client_counters.total_bytes_before_reduction += len(message_value)
            #   superstream.client_counters.total_messages_failed_consume += 1
            return message

        wait_time = 60
        check_interval = 5

        for _ in range(0, wait_time, check_interval):
            if self.superstream and self.superstream.superstream_ready:
                break
            time.sleep(check_interval)

        if not self.superstream or not self.superstream.superstream_ready:
            sys.stderr.write(
                "superstream: cannot connect with superstream and consume message that was modified by superstream"
            )
            return message

        descriptor = self.superstream.consumer_proto_desc_map.get(schema_id)
        if not descriptor:
            await self.superstream.send_get_schema_request(schema_id)
            descriptor = self.superstream.consumer_proto_desc_map.get(schema_id)
            if not descriptor:
                await self.superstream.handle_error(f"error getting schema with id: {schema_id}")
                return message

        try:
            deserialized_msg = proto_to_json(message_value, descriptor)
            # superstream.client_counters.total_bytes_before_reduction += len(deserialized_msg)
            # superstream.client_counters.total_messages_successfully_consumed += 1
            message.set_value(deserialized_msg.encode("utf-8"))
            return message
        except Exception as e:
            await self.superstream.handle_error(f"error deserializing data: {e!s}")
            return message
