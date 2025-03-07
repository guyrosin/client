import json
import logging
import os

import six
from wandb.errors import Error
from wandb.lib import filesystem
from wandb.util import load_yaml
import yaml


logger = logging.getLogger("wandb")


class ConfigError(Error):  # type: ignore
    pass


def dict_from_proto_list(obj_list):
    d = dict()
    for item in obj_list:
        d[item.key] = dict(desc=None, value=json.loads(item.value_json))
    return d


def dict_no_value_from_proto_list(obj_list):
    d = dict()
    for item in obj_list:
        d[item.key] = json.loads(item.value_json)["value"]
    return d


# TODO(jhr): these functions should go away once we merge jobspec PR
def save_config_file_from_dict(config_filename, config_dict):
    s = b"wandb_version: 1"
    if config_dict:  # adding an empty dictionary here causes a parse error
        s += b"\n\n" + yaml.dump(
            config_dict,
            Dumper=yaml.SafeDumper,
            default_flow_style=False,
            allow_unicode=True,
            encoding="utf-8",
        )
    data = s.decode("utf-8")
    filesystem._safe_makedirs(os.path.dirname(config_filename))
    with open(config_filename, "w") as conf_file:
        conf_file.write(data)


def dict_from_config_file(filename, must_exist=False):
    if not os.path.exists(filename):
        if must_exist:
            raise ConfigError("config file %s doesn't exist" % filename)
        logger.debug('no default config file found in %s' % filename)
        return None
    try:
        conf_file = open(filename)
    except OSError:
        raise ConfigError("Couldn't read config file: %s" % filename)
    try:
        loaded = load_yaml(conf_file)
    except yaml.parser.ParserError:
        raise ConfigError("Invalid YAML in config yaml")
    config_version = loaded.pop("wandb_version", None)
    if config_version is not None and config_version != 1:
        raise ConfigError("Unknown config version")
    data = dict()
    for k, v in six.iteritems(loaded):
        data[k] = v["value"]
    return data
