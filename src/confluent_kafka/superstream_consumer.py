from typing import Any, Dict, List, Optional

from superstream import SuperstreamConsumerInterceptor

from confluent_kafka.cimpl import Consumer as _ConsumerImpl


class SuperstreamConsumer(_ConsumerImpl):
    def __init__(self, config: Dict):
        super().__init__(config)
        self._interceptor = SuperstreamConsumerInterceptor(config)

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
