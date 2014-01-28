#!/usr/bin/env python3

import re
import sys
import fileinput
import operator


class Symbol(object):
    KIND_MAP = {'f': 'f',
                'c': 'c',
                'm': 'm\taccess:public',
                'M': 'm\taccess:private'}

    SCOPE_MAP = {'f': 'procedure',
                 'c': 'class',
                 'm': 'method',
                 'M': 'method'}

    def __init__(self, name, filename, line, kind, lineno, parent):
        self.name = name
        self.filename = filename
        self.line = line
        self.lineno = lineno
        self._kind = kind
        self.parent = parent

    def to_tags_line(self):
        '''Format this simple for use in ``tags``.

        The result is a string formatted according to the tags_ format, i.e.::

            <symbolname>\t<filename>\t/^<content>$/;"\t<kind>\t[<scope>]

        .. _tags: http://vimdoc.sourceforge.net/htmldoc/tagsrch.html#tags-file-format.
        '''
        res = '{0.name}\t{0.filename}\t/^{0.line}$/;"\t{0.kind}\tline:{0.lineno}'.format(self)
        parent = self.get_named_parent()
        if parent:
            res += '\t{0.scope}:{0.qualified_name}'.format(parent)
        return res

    @property
    def qualified_name(self):
        '''Get the qualified name (i.e. including the name of all ancestors).

        The qualified name is in the form ``A,B,C``.
        '''
        name_parts = []
        cur = self
        while cur:
            name = cur.name
            if name:
                name_parts.append(name)
            cur = cur.parent

        return ','.join(reversed(name_parts))

    @property
    def scope(self):
        return self.SCOPE_MAP[self._kind]

    @property
    def kind(self):
        return self.KIND_MAP[self._kind]

    def get_named_parent(self):
        '''Get the nearest ancestor which has a valid name.

        If there are no ancestors having names, this method returns None.
        '''
        cur = self.parent
        while cur:
            if cur.name:
                return cur
            else:
                cur = cur.parent


class SimpleOzParser(object):
    '''A simple Oz parser.

    This parser only recognizes fun, proc, class and meth.
    '''

    # The parser recognizes the following patterns:
    #
    # The "lexer" should recognize:
    #
    #   ScopeStart = choice|cond|dis|do|functor|local|lock|not|of|or|raise|then|thread|try
    #   Atom       = [a-z]\w* | '([^\\']|\\.)*'
    #   Variable   = [A-Z]\w* | `([^\\`]|\\.)*`
    #   String     = "([^\\"]|\\.)*"
    #   Comment    = /\*([^*]|\*[^/])*\*/
    #   Comment2   = %.*
    #   Comment3   = [^a-zA-Z'`"/%{!$]+
    #   class
    #   fun|proc
    #   meth
    #   {
    #   !
    #   $
    #

    (IGNORE, CLASS, PROC, METH, END, BRACE, EXCL, DOLLAR, SCOPE, ATOM, VAR) \
            = range(11)

    LEXER_PATTERNS = [
        (re.compile(r'class\b'), CLASS),
        (re.compile(r'(?:fun|proc)\b'), PROC),
        (re.compile(r'meth\b'), METH),
        (re.compile(r'end\b'), END),
        (re.compile(r'\{'), BRACE),
        (re.compile(r'!(?!!)'), EXCL),
        (re.compile(r'\$'), DOLLAR),
        (re.compile(r'''(?:
            # standard scope starters.
                local|if|case|lock|thread|try|raise|
            # constraint programming
                not|cond|or|dis|choice|
            # others
                functor|for)\b''', re.X), SCOPE),
        (re.compile(r"[a-z]\w*|'(?:[^\\']|\\.)*'"), ATOM),
        (re.compile(r'[A-Z]\w*|`(?:[^\\`]|\\.)*`'), VAR),
        (re.compile(r'/\*(?:[^*]|\*[^/])*\*/'), IGNORE),
        (re.compile(r'%.*'), IGNORE),
        (re.compile(r'&(?:[^\\]|\\(?:[xX][0-9a-fA-F]{2}|[^xX]))'), IGNORE),
        (re.compile(r'''/(?!\*)|[^a-zA-Z'`"%/&{!$]+'''), IGNORE)
    ]

    # The "parser" should recognize:
    #
    #   fun Atom? "{" Variable    -> start of function
    #   proc Atom? "{" Variable   -> start of procedure
    #   class Variable          -> start of class
    #   meth Atom               -> start of public method
    #   meth ! Variable         -> start of private method
    #   meth Variable           -> start of private method
    #   fun Atom? { $           -> start of anonymous scope
    #   proc Atom? { $          -> start of anonymous scope
    #   ScopeStart              -> start of anonymous scope
    #

    (ST_INIT, ST_PROC_1, ST_PROC_2, ST_CLASS_1, ST_METH_1) = range(5)
    CS_PROC = 'f'
    CS_CLASS = 'c'
    CS_PUB_METH = 'm'
    CS_PRIV_METH = 'M'
    CS_SCOPE = 's'
    CS_END = 'e'

    PARSER_TRANS_TABLE = [
        # ST_INIT
        {PROC: ST_PROC_1, CLASS: ST_CLASS_1, METH: ST_METH_1,
         END: CS_END, SCOPE: CS_SCOPE},
        # ST_PROC_1
        {ATOM: ST_PROC_1, BRACE: ST_PROC_2},
        # ST_PROC_2
        {DOLLAR: CS_SCOPE, VAR: CS_PROC},
        # ST_CLASS_1
        {VAR: CS_CLASS},
        # ST_METH_1
        {EXCL: ST_METH_1, ATOM: CS_PUB_METH, VAR: CS_PRIV_METH},
    ]

    def __init__(self):
        self._lexer = self._lex()
        self._parser = self._parse()
        next(self._lexer)
        next(self._parser)

    @classmethod
    def _lex(cls):
        '''A coroutine to lex strings.'''
        current_buffer = ""

        # outer loop to keep populating the buffer.
        while True:
            current_buffer += yield

            # inner loop to consume the buffer.
            while current_buffer:
                #print(repr(current_buffer))
                for pattern, token_type in cls.LEXER_PATTERNS:
                    m = pattern.match(current_buffer)
                    if m is not None:
                        match_length = m.end()
                        if token_type:
                            token_content = current_buffer[:match_length]
                            yield (token_type, token_content)
                        current_buffer = current_buffer[match_length:]
                        break
                else:
                    # if we reach here, none of the patterns match the input,
                    # likely meaning unfinished quotes. try to populate the
                    # buffer.
                    yield
                    break

    @classmethod
    def _parse(cls):
        '''A coroutine to parse tokenized data.'''
        cur_scope = Symbol(None, None, None, None, -1, None)
        cur_symbol = None
        cur_name = None
        cur_state = cls.ST_INIT

        while True:
            ((token_type, token_content), line, lineno, filename) = yield cur_symbol
            cur_symbol = None

            if token_type in (cls.ATOM, cls.VAR):
                cur_name = token_content

            trans_table = cls.PARSER_TRANS_TABLE[cur_state]
            cur_state = trans_table.get(token_type, cls.ST_INIT)

            if cur_state in (cls.CS_PROC, cls.CS_CLASS, cls.CS_PUB_METH, cls.CS_PRIV_METH):
                cur_symbol = Symbol(cur_name, filename, line, cur_state, lineno, cur_scope)
                cur_scope = cur_symbol
            elif cur_state == cls.CS_SCOPE:
                cur_scope = Symbol(None, None, None, token_content, -1, cur_scope)
            elif cur_state == cls.CS_END:
                cur_scope = cur_scope.parent
            else:
                continue

            cur_state = cls.ST_INIT

    def feed(self, line, lineno, filename):
        '''Feed a line into the parser.'''
        the_input = line
        while True:
            res = self._lexer.send(the_input)
            the_input = None
            if res:
                yield self._parser.send((res, line, lineno, filename))
            else:
                break


parser = SimpleOzParser()
all_symbols = []

for line in fileinput.input():
    filename = fileinput.filename()
    line = line.rstrip('\r\n')
    lineno = fileinput.lineno()
    symbols = parser.feed(line, lineno, filename)
    true_symbols = filter(None, symbols)
    all_symbols.extend(true_symbols)

all_symbols.sort(key=operator.attrgetter('name'))
for symbol in all_symbols:
    print(symbol.to_tags_line())


# oztags.py -- Create tags for Oz source.
# Copyright (c) 2014 kennytm
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.

