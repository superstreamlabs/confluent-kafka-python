from typing import Dict

from superstream import SuperstreamProducerInterceptor

from confluent_kafka.cimpl import Producer as _ProducerImpl


class SuperstreamProducer(_ProducerImpl):
    def __init__(self, config: Dict):
        super().__init__(config)
        self._interceptor = SuperstreamProducerInterceptor(config, super().produce)

    def produce(self, *args, **kwargs):
        self._interceptor.produce(*args, **kwargs)
