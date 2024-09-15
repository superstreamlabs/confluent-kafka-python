import io
import sys
from typing import AnyStr, List

from confluent_kafka.superstream.constants import EnvVars


class SuperstreamStd:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SuperstreamStd, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            enable_stdout, enable_stderr = SuperstreamStd.check_stdout_env_var()

            self.stdout = sys.stdout if enable_stdout else io.StringIO()
            self.stderr = sys.stderr if enable_stderr else io.StringIO()

            self._initialized = True

    def write(self, s: AnyStr, **kwargs):
        if isinstance(s, str):
            s = f"{s}\n"
        self.stdout.write(s, **kwargs)

    def writelines(self, lines: List[AnyStr], **kwargs):
        self.stdout.writelines(lines, **kwargs)

    def error(self, s: AnyStr, **kwargs):
        if isinstance(s, str):
            s = f"{s}\n"
        self.stderr.write(s, **kwargs)

    def errorlines(self, *args, **kwargs):
        self.stderr.writelines(*args, **kwargs)

    @staticmethod
    def check_stdout_env_var():
        if EnvVars.SUPERSTREAM_DEBUG:
            enable_stdout = True
            enable_stderr = True
        else:
            enable_stdout = False
            enable_stderr = False
        return enable_stdout, enable_stderr
