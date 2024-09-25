from typing import Any, Dict, List, Optional

from confluent_kafka.cimpl import Consumer as _ConsumerImpl

from .consumer_interceptor import SuperstreamConsumerInterceptor


class SuperstreamConsumer(_ConsumerImpl):
    def __init__(self, config: Dict):
        self._interceptor = SuperstreamConsumerInterceptor(config)
        config = self._interceptor.wait_for_superstream_configs_sync(config)
        self._interceptor.set_full_configuration(config)
        super().__init__(config)

    def poll(self, *args, **kwargs) -> Any:
        message = super().poll(*args, **kwargs)
        if message is None:
            return message
        return self._interceptor.poll(message)

    def consume(self, *args, **kwargs) -> Optional[List[Any]]:
        messages = super().consume(*args, **kwargs)
        if messages is None:
            return messages
        return [self._interceptor.consume(message) for message in messages]