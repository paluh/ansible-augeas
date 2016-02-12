#!/usr/bin/python -tt
# -*- coding: utf-8 -*-

# (c) 2013, Tomasz Rybarczyk <paluho@gmail.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#

DOCUMENTATION = '''
---
module: augeas
author: Tomasz Rybarczyk
short_description: Augeas support
description:
  - Augeas module which exposes simple API for "match", "set" and "rm". You can execute commands one by one or in chunk.
version_added: "1.1"
requirements:
  - augeas + lenses (augeas-lenses on Debian)
  - "augeas python bindings (python-augeas on Debian, note: on Debian Wheezy you also need to install libpython2.7, since python-augeas package wrongly does not list it as a requirement)"
options:
  command:
    required: false
    choices: [ set, ins, rm, match, lensmatch ]
    description:
      - 'Whether given path should be modified, inserted, removed or matched. Command "match" (and "lensmatch") passes results through "result" attribute - every item on this list is an object with "label" and "value" (check third example below). Other commands returns true in case of any modification (so this value is always equal to "changed" attribue - this make more sens in case of bulk execution)'
  path:
    required: false
    description:
      - 'Variable path. With `lensmatch`, it is the relative path within the file tree.'
  value:
    required: false
    description:
      - 'Variable value (required for "set" command).'
  label:
    required: false
    description:
      - 'Label for new node.'
  where:
    required: false
    choices: [before, after]
    description:
      - 'Position of node insertion against given path.'
  lens:
    required: false
    description:
      - 'Augeas lens to be loaded.'
  file:
    required: false
    description:
      - 'File to parse.'
  commands:
    required: false
    description:
      - 'Execute many commands at once (some configuration entries have to be created/updated at once - it is impossible to split them across multiple "set" calls). Standard shell quoting is allowed (rember to escape all quotes inside pahts/values - check last example). Expected formats: "set path value", "rm path" or "match path" (look into examples for more details). You can separate commands with any white chars (new lines, spaces etc.). Result is passed through "result" attribute and contains list of tuples: (command, command result).'
  root:
    required: false
    description:
      - 'The filesystem root - config files are searched realtively to this path (fallbacks to AUGEAS_ROOT or /).'
  loadpath:
    required: false
    description:
      - 'Colon-spearated list of directories that modules should be searched in.'
examples:
  - code: 'augeas: path=/files/etc/sudoers/spec[user=\\"sudo\\"]/host_group/command/tag value=PASSWD'
    description: 'Simple value change'

  - code: |
      - name: Check wether given user is listed in sshd_config
        action: augeas command='match' path="/files/etc/ssh/sshd_config/AllowUsers/*[.=\\"{{ user }}\\"]"
        register: user_entry
      - name: Allow user to login through ssh
        action: augeas command="set" path="/files/etc/ssh/sshd_config/AllowUsers/01" value="{{ user }}"
        when: "user_entry.result|length == 0"
    description: "Quite complex modification - fetch values lists and append new value only if it doesn't exists already in config"

  - code: 'action: augeas commands="lensmatch" lens="sshd" file="/home/paluh/programming/ansible/tests/sshd_config" path="AllowUsers/*"'
    description: Modify sshd_config in custom location

  - code: |
      - name: Add new host to /etc/hosts
        action:  augeas commands=\'set /files/etc/hosts/01/ipaddr 192.168.0.1
                                  set /files/etc/hosts/01/canonical pigiron.example.com
                                  set /files/etc/hosts/01/alias[1] pigiron
                                  set /files/etc/hosts/01/alias[2] piggy\'
    description: "Bulk command execution."

  - code: |
      - name: Redifine eth0 interface
        action:  augeas commands=\'rm /files/etc/network/interfaces/iface[.=\\"eth0\\"]
                                  set /files/etc/network/interfaces/iface[last()+1] eth0
                                  set /files/etc/network/interfaces/iface[.=\\"eth0\\"]/family inet
                                  set /files/etc/network/interfaces/iface[.=\\"eth0\\"]/method manual
                                  set /files/etc/network/interfaces/iface[.=\\"eth0\\"]/pre-up "ifconfig $IFACE up"
                                  set /files/etc/network/interfaces/iface[.=\\"eth0\\"]/pre-down "ifconfig $IFACE down"\'
    description: "Correct quoting in commands expressions (augeas requires quotes in path matching expressions: iface[.=\\"eth0\\"])"
'''

try:
    import augeas
except ImportError:
    augeas = None
from collections import namedtuple
import ctypes
import re
import shlex

if augeas:
    # Augeas C API `aug_span` function was introduced on the begining of 2011
    # but python-augeas 0.4 was released month before and doesn't contain bindings for it
    # This code is copied from current devel branch of python-augeas

    # check whether augeas library supports span
    if augeas.Augeas(flags=getattr(augeas.Augeas, 'NO_MODL_AUTOLOAD', 0)).match('/augeas/span'):
        if not hasattr(augeas.Augeas, 'span'):
            class Augeas(augeas.Augeas):

                ENABLE_SPAN = 128

                def span(self, path):
                    """Get the span according to input file of the node associated with
                    PATH. If the node is associated with a file, un tuple of 5 elements is
                    returned: (filename, label_start, label_end, value_start, value_end,
                    span_start, span_end). If the node associated with PATH doesn't
                    belong to a file or is doesn't exists, ValueError is raised."""

                    if not isinstance(path, basestring):
                        raise TypeError("path MUST be a string!")
                    if not self.__handle:
                        raise RuntimeError("The Augeas object has already been closed!")

                    filename = ctypes.c_char_p()
                    label_start = ctypes.c_uint()
                    label_end = ctypes.c_uint()
                    value_start = ctypes.c_uint()
                    value_end = ctypes.c_uint()
                    span_start = ctypes.c_uint()
                    span_end = ctypes.c_uint()

                    r = ctypes.byref

                    ret = Augeas._libaugeas.aug_span(self.__handle, path, r(filename),
                                                     r(label_start), r(label_end),
                                                     r(value_start), r(value_end),
                                                     r(span_start), r(span_end))
                    if (ret < 0):
                        raise ValueError("Error during span procedure")

                    return (filename.value, label_start.value, label_end.value,
                            value_start.value, value_end.value,
                            span_start.value, span_end.value)
        else:
            Augeas = augeas.Augeas


class CommandsParseError(Exception):

    def __init__(self, msg):
        self.msg = msg
        super(CommandsParseError, self).__init__(msg)

    def format_commands(self, commands):
        return '\n'.join('%s %s' % (c, ' '.join(a if a else "''" for a in args.values())) for c,args in commands)


class MissingArgument(CommandsParseError):

    def __init__(self, command, value, already_parsed):
        if already_parsed:
            msg = ('Missing argument "%s" in "%s" statement - already parsed statements:\n%s' %
                    (value, command, self.format_commands(already_parsed)))
        else:
            msg = 'Missing argument "%s" in "%s" statement' % (value, command)
        super(MissingArgument, self).__init__(msg)


class UnknownCommand(CommandsParseError):

    def __init__(self, token, already_parsed):
        if already_parsed:
            msg = ('Incorrect command or previous command quoting:\n'
                   'invalid token: %s\n'
                   'already parsed:\n%s' % (token, self.format_commands(already_parsed)))
        else:
            msg = 'Incorrect command: "%s"' % token
        self.msg = msg
        super(UnknownCommand, self).__init__(msg)


class ParamParseError(CommandsParseError):

    def __init__(self, param, value, expected):
        super(ParamParseError,
              self).__init__('Given %(param)s value: %(value)s doesn\'t match expected '
                             'value: %(expected)s' % {'param': repr(param),
                                                      'value': repr(value),
                                                      'expected': unicode(expected)})


class TokenizerError(CommandsParseError):

    pass


class ParamParser(namedtuple('ParamValidator', ['name', 'validator'])):

    def __new__(cls, name, validator):
        return super(ParamParser, cls).__new__(cls, name, validator)

    def __call__(self, value):
        raise NotImplementedError('You should validated value here and return cleaned result')


class RegexParser(ParamParser):

    def __new__(cls, name, pattern):
        validator = re.compile(pattern)
        return super(RegexParser, cls).__new__(cls, name, validator)

    def __call__(self, value):
        if self.validator.match(value) is None:
            raise ParamParseError(self.name, value, 're.compile(%s)' % repr(self.validator.pattern))
        return value

class AnythingParser(RegexParser):

    def __new__(cls, name):
        return super(AnythingParser, cls).__new__(cls, name, '.*')


class NonEmptyParser(RegexParser):

    def __new__(cls, name):
        return super(NonEmptyParser, cls).__new__(cls, name, '.+')


class OneOfParser(RegexParser):

    def __new__(cls, name, patterns):
        return super(OneOfParser, cls).__new__(cls, name, '(%s)' % '|'.join(patterns))


def parse_commands(commands):
    """
    Basic tests (if you are going to modify this function update/check tests too
                 - the easiest way is to copy them to separate module):

    >>> assert (parse_commands("set '/path/containing/ /space/' 'value with spaces'") == \
                [('set', {'path': '/path/containing/ /space/', 'value': 'value with spaces'})])
    >>> assert (parse_commands("set '/path' 'value\\\\nwith\\\\nnew\\\\nlines'") == \
                [('set', {'path': '/path', 'value': 'value\\\\nwith\\\\nnew\\\\nlines'})])
    >>> assert (parse_commands("set '/path' '\\"\\"'") == \
                [('set', {'path': '/path', 'value': '""'})])
    >>> assert (parse_commands("set '/path' ''") == \
                [('set', {'path': '/path', 'value': ''})])
    >>> assert (parse_commands("set '/path[.=\\"pattern\\"]' ''") == \
                [('set', {'path': '/path[.="pattern"]', 'value': ''})])
    >>> parse_commands("set '/path'")
    Traceback (most recent call last):
    ...
    MissingArgument: Missing argument "value" in "set" statement
    >>> parse_commands("set '/path' '' rm")
    Traceback (most recent call last):
    ...
    MissingArgument: Missing argument "path" in "rm" statement - already parsed statements:
    set /path ''
    >>> assert (parse_commands("ins alias before /path") == \
                [('ins', {'path': '/path', 'where': 'before', 'label': 'alias'})])
    >>> parse_commands("ins alias bfore /path")
    Traceback (most recent call last):
    ...
    CommandsParseError: Error parsing parameter value of command "ins":
    Given 'where' value: 'bfore' doesn't match expected value: re.compile('(before|after)')
    """
    path_parser = NonEmptyParser('path')
    COMMANDS = {
        'set': [path_parser, AnythingParser('value')],
        'rm': [path_parser],
        'match': [path_parser],
        'lensmatch': [path_parser, NonEmptyParser('lens'), NonEmptyParser('file')],
        'ins': [NonEmptyParser('label'), OneOfParser('where', ['before', 'after']), path_parser],
        'transform': [NonEmptyParser('lens'), OneOfParser('filter', ['incl', 'excl']), NonEmptyParser('file')],
        'load': []
    }
    try:
        tokens = iter(shlex.split(commands, comments=False))
    except ValueError, e:
        raise TokenizerError("Commands parser error (commands should be correctly quoted strings): %s" % e.args[0])
    parsed = []
    for command in tokens:
        if command not in COMMANDS:
            raise UnknownCommand(command, parsed)
        params = {}
        for parser in COMMANDS[command]:
            try:
                value = tokens.next()
            except StopIteration:
                raise MissingArgument(command, parser.name, parsed)
            try:
                params[parser.name] = parser(value)
            except ParamParseError, e:
                raise CommandsParseError('Error parsing parameter value of command "%(command)s":\n%(exception)s' %
                                         {'command': command, 'exception': e})
        parsed.append((command, params))
    return parsed


class ExceptionWithMessage(Exception):

    def __init__(self, msg, *args, **kwargs):
        self.msg = msg
        super(Exception, self).__init__(self, msg, *args, **kwargs)


class AugeasError(ExceptionWithMessage):

    path = None
    error_type = None

    def format_augeas_errors(self, augeas_instance):
        errors = []
        for error in augeas_instance.match('/augeas//error'):
            error_type = augeas_instance.get(error)
            if not self.error_type or not error_type or self.error_type == error_type:
                errors.append([(p, augeas_instance.get(p)) for p in augeas_instance.match(error + '/' + '*')])

        if errors:
            errors = '\n\n'.join('\n'.join('%s: %s'%(p, v) for p,v in error) for error in errors)
            return ('Augeas has reported following problems '
                    ' (it\'s possible that some of them are unrelated to your action):\n\n%s' % errors)
        if self.error_type is not None:
            return 'Augeas hasn\'t provided any additional info for action type (%s)' % self.error_type
        return 'Augeas hasn\'t provided any additional info'


class PathParseError(AugeasError):

    def __init__(self, augeas_instance, path, correct_subpath):
        msg = ('Path parsing error:\nfull path: %s\n'
               'correct subpath: %s\n\n%s') % (path, correct_subpath,
                                               self.format_augeas_errors(augeas_instance))
        super(PathParseError, self).__init__(msg)


class SaveError(AugeasError):

    def __init__(self, augeas_instance):
        msg = 'Augeas refused to save changes. %s' % self.format_augeas_errors(augeas_instance)
        super(SaveError, self).__init__(msg)


class CommandError(AugeasError):

    def __init__(self, command, params, augeas_instance):
        msg = 'Augeas command execution error (command=%s, params=%s). %s' % (command, params,
                                                                              self.format_augeas_errors(augeas_instance))
        super(CommandError, self).__init__(msg)


class SetError(CommandError):

    error_type = 'put_failed'


class InsertError(CommandError):

    pass


def execute(augeas_instance, commands):
    results = []
    changed = False
    for command, params in commands:
        result = None
        if command == 'set':
            path = params['path']
            value = params['value']
            if augeas_instance.get(path) != value:
                try:
                    augeas_instance.set(path, value)
                except ValueError:
                    raise SetError(command, params, augeas_instance)
                result = changed = True
            else:
                result = False
        elif command == 'rm':
            path = params['path']
            if augeas_instance.match(path):
                augeas_instance.remove(path)
                result = changed = True
            else:
                result = False
        elif command == 'ins':
            path = params['path']
            label = params['label']
            where = params['where']
            try:
                augeas_instance.insert(path, label, where == 'before')
            except ValueError:
                raise InsertError(command, params, augeas_instance)
            result = changed = True
        elif command == 'transform':
            lens = params['lens']
            file_ = params['file']
            excl = params['filter'] == 'excl'
            augeas_instance.transform(lens, file_, excl)
        elif command == 'load':
            augeas_instance.load()
        elif command == 'lensmatch':
            augeas_instance.transform(params['lens'], params['file'])
            augeas_instance.load()
            result = [{'label': s, 'value': augeas_instance.get(s)} for s in augeas_instance.match(params['path'])]
        else: # match
            result = [{'label': s, 'value': augeas_instance.get(s)} for s in augeas_instance.match(**params)]
        results.append((command + ' ' + ' '.join(p if p else '""' for p in params.values()), result))

    try:
        augeas_instance.save()
    except IOError:
        raise SaveError(augeas_instance)
    return results, changed

def main():
    module = AnsibleModule(
        argument_spec=dict(
            loadpath=dict(default=None),
            root=dict(default=None),
            command=dict(required=False, choices=['set', 'rm', 'match', 'lensmatch', 'ins', 'transform', 'load']),
            path=dict(aliases=['name', 'context']),
            value=dict(default=None),
            commands=dict(default=None),
            where=dict(default=None),
            label=dict(default=None),
            lens=dict(default=None),
            file=dict(defulat=None),
            filter=dict(default=None)
        ),
        mutually_exclusive=[['commands', 'command'], ['commands', 'value'],
                            ['commands', 'path']],
        required_together=[('command', 'path')],
        required_one_of=[('command', 'commands')],
    )
    if augeas is None:
        module.fail_json(msg='Could not import python augeas module.'
                             ' Please install augeas related packages and '
                             'augeas python bindings.')
    augeas_instance = Augeas(root=module.params['root'], loadpath=module.params['loadpath'],
                             flags=getattr(Augeas, 'ENABLE_SPAN', 0))
    commands = None
    if module.params['command'] is not None:
        command = module.params['command']
        if command == 'set':
            if module.params['value'] is None:
                module.fail_json(msg='You should use "value" argument with "set" command.')
            params = {'path': module.params['path'], 'value': module.params['value']}
        elif command == 'ins':
            if module.params['label'] is None:
                module.fail_json(msg='You have to use "label" argument with "ins" command.')
            if module.params['path'] is None:
                module.fail_json(msg='You have to use "path" argument with "ins" command.')
            params = {'label': module.params['label'], 'path': module.params['path'],
                      'where': module.params['where'] or 'before'}
        elif command == 'transform':
            params = {'lens': module.params['lens'], 'file': module.params['file'],
                      'filter': module.params['filter']}
        elif command == 'load':
            params = {}
        elif command == 'lensmatch':
            params = {'lens': module.params['lens'], 'file': module.params['file']}
            params['path'] = "/files%s/%s" % ( params['file'] , module.params['path'] )
        else: # rm or match
            params = {'path': module.params['path']}
        commands = [(command, params)]
    else:
        try:
            commands = parse_commands(module.params['commands'])
        except CommandsParseError, e:
            module.fail_json(msg=e.msg)
    try:
        results, changed = execute(augeas_instance, commands)
    except AugeasError, e:
        module.fail_json(msg=e.msg)

    # in case of single command execution return only one result
    # in case of multpile commands return list of (command, result) tuples
    if module.params['command'] is not None:
        results = results[0][1]
    module.exit_json(changed=changed, result=results)


# this is magic, see lib/ansible/module_common.py
#<<INCLUDE_ANSIBLE_MODULE_COMMON>>

main()
