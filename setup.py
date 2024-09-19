#!/usr/bin/env python

import os
import platform
from distutils.core import Extension

from setuptools import setup

if platform.system() == "Windows":
    librdkafka_libname = "librdkafka"
else:
    librdkafka_libname = "rdkafka"


cimpl_dir_prefix = "src/confluent_kafka/src"

module = Extension(
    "confluent_kafka.cimpl",
    libraries=[librdkafka_libname],
    sources=[
        os.path.join(cimpl_dir_prefix, "confluent_kafka.c"),
        os.path.join(cimpl_dir_prefix, "Producer.c"),
        os.path.join(cimpl_dir_prefix, "Consumer.c"),
        os.path.join(cimpl_dir_prefix, "Metadata.c"),
        os.path.join(cimpl_dir_prefix, "AdminTypes.c"),
        os.path.join(cimpl_dir_prefix, "Admin.c"),
    ],
)


setup(
    ext_modules=[module],
)
