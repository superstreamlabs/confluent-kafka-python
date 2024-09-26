import asyncio
import queue
import threading
from typing import Dict

from confluent_kafka.cimpl import Producer as _ProducerImpl

from .producer_interceptor import SuperstreamProducerInterceptor


class SuperstreamProducer:
    def __init__(self, config: Dict):
        self._lock = threading.Lock()
        self._message_queue = queue.Queue()
        self._interceptor = SuperstreamProducerInterceptor(config)
        config = self._interceptor.wait_for_superstream_configs_sync(config)
        self._interceptor.set_full_configuration(config)
        self._p = _ProducerImpl(config)
        self._interceptor.set_producer_handler(self._p.produce)
        self._interceptor.set_config_update_cb(self._update_config)
        self._config = config
        self._loop = asyncio.get_event_loop()

    def __len__(self):
        return len(self._p)

    def produce(self, *args, **kwargs):
        if self._lock.locked():
            self._message_queue.put((args, kwargs))
        else:
            self._interceptor.produce(*args, **kwargs)

    async def _produce_messages_from_queue(self):
        while not self._message_queue.empty():
            args, kwargs = self._message_queue.get()
            self._interceptor.produce(*args, **kwargs)

    def _update_config(self, new_config: Dict):
        with self._lock:
            try:
                self.poll(0)
                self.flush()

                self._p = _ProducerImpl(new_config)
                
                self._interceptor.set_full_configuration(new_config)
                self._interceptor.set_producer_handler(self._p.produce)
                asyncio.run_coroutine_threadsafe(
                    self._produce_messages_from_queue(), self._loop
                )

            except Exception as e:
                print(e)
                pass

    def poll(self, *args, **kwargs):
        return self._p.poll(*args, **kwargs)

    def flush(self, *args, **kwargs):
        return self._p.flush(*args, **kwargs)

    def purge(self, *args, **kwargs):
        return self._p.purge(*args, **kwargs)

    def list_topics(self, *args, **kwargs):
        return self._p.list_topics(*args, **kwargs)

    def init_transactions(self, *args, **kwargs):
        return self._p.init_transactions(*args, **kwargs)

    def begin_transaction(self, *args, **kwargs):
        return self._p.begin_transaction(*args, **kwargs)

    def send_offsets_to_transaction(self, *args, **kwargs):
        return self._p.send_offsets_to_transaction(*args, **kwargs)

    def commit_transaction(self, *args, **kwargs):
        return self._p.commit_transaction(*args, **kwargs)

    def abort_transaction(self, *args, **kwargs):
        return self._p.abort_transaction(*args, **kwargs)

    def set_sasl_credentials(self, *args, **kwargs):
        return self._p.set_sasl_credentials(*args, **kwargs)
