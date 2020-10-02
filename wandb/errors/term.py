import click
import os
import sys

import wandb.env as env
import wandb.util as util


LOG_STRING = click.style('wandb', fg='blue', bold=True)
LOG_STRING_NOCOLOR = 'wandb'
ERROR_STRING = click.style('ERROR', bg='red', fg='green')
WARN_STRING = click.style('WARNING', fg='yellow')
PRINTED_MESSAGES = set()


def termlog(string='', newline=True, repeat=True, prefix=True, silent=False):
    """Log to standard error with formatting.

    Args:
            string (str, optional): The string to print
            newline (bool, optional): Print a newline at the end of the string
            repeat (bool, optional): If set to False only prints the string once per process
    """
    silent = silent or env.get_silent()
    if string:
        if prefix:
            line = '\n'.join(['{}: {}'.format(LOG_STRING, s)
                          for s in string.split('\n')])
        else:
            line = string
    else:
        line = ''
    if not repeat and line in PRINTED_MESSAGES:
        return
    # Repeated line tracking limited to 1k messages
    if len(PRINTED_MESSAGES) < 1000:
        PRINTED_MESSAGES.add(line)
    if silent:
        util.mkdir_exists_ok(os.path.dirname(util.get_log_file_path()))
        with open(util.get_log_file_path(), 'w') as log:
            click.echo(line, file=log, nl=newline)
    else:
        click.echo(line, file=sys.stderr, nl=newline)


def termwarn(string, **kwargs):
    silent = env.get_warnings() == "disable"
    string = '\n'.join(['{} {}'.format(WARN_STRING, s)
                        for s in string.split('\n')])
    termlog(string=string, newline=True, silent=silent, **kwargs)


def termerror(string, **kwargs):
    silent = env.get_log_level() == ""
    string = '\n'.join(['{} {}'.format(ERROR_STRING, s)
                        for s in string.split('\n')])
    termlog(string=string, newline=True, silent=True, **kwargs)

