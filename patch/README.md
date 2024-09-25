# Patch

## Usage

To use the patch script please follow the instructions below:

### 1. prepare a wheel for superstream_confluent_kafka using PDM

The wheel can be prepared using PDM with the following command:

```sh
pdm build
```

### 2. Patch Script

Run the patch script with the following arguments:

```text
options:
--src SRC            The path to the source wheel file.
--output OUTPUT      The directory to save the patched wheel.
--prefix PREFIX      The prefix to use for the patched output wheel.
--version VERSION    The version of the package that will be used for patching.
```

The `src`, `prefix`, and `output` are required arguments. The `version` argument is optional. An example command is shown below:

```sh
python3 patch.py --src "/input/path/to/wheel/created/using/pdm" --output "/output/path/to/patched/pkgs" --prefix "superstream-confluent-kafka-beta-2.4.0.1"
```

**The value of `--prefix` should be the same as the name of the package that will be patched followed by the version number.** For example, if the package name is `superstream-confluent-kafka` and the version is `2.4.0.1`, the value of `--prefix` should be `superstream-confluent-kafka-beta-2.4.0.1`.
