#!/usr/bin/env python3
import json
import random

import psycopg
from IPython.terminal.embed import InteractiveShellEmbed
from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers import JsonLexer

from tools.utils import connect


def hl(obj):
    print(highlight(json.dumps(obj, indent=2), JsonLexer(), TerminalFormatter()))


conn = connect()
InteractiveShellEmbed()()
