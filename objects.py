#
# RTEMS Objects Support
# Copyright 2010 Chris Johns (chrisj@rtems.org)
#
# $Id$
#

import gdb
import itertools
import re

class infotables:
    """Manage the object information tables."""

    tables_types = {
        'classic/tasks'          : ('Thread_Control',        '_RTEMS_tasks_Information'),
        'classic/timers'         : ('Timer_Control',         '_Timers_Information'),
        'classic/semaphores'     : ('Semaphore_Control',     '_Semaphore_Information'),
        'classic/message_queues' : ('Message_queue_Control', '_Message_queue_Information'),
        'classic/partitions'     : ('Partition_Control',     '_Partition_Information'),
        'classic/regions'        : ('Region_Control',        '_Regions_Information'),
        'classic/ports'          : ('Port_Control',          '_Port_Information'),
        'classic/periods'        : ('Period_Control',        '_Period_Information'),
        'classic/extensions'     : ('Extension_Control',     '_Extension_Information'),
        'classic/barriers'       : ('Barrier_Control',       '_Barrier_Information')
        }

    def __init__(self):
        self.invalidate()

    def invalidate(self):
        self.tables = {}

    def name(self, api, _class):
        return api + '/' + _class

    def load(self, n):
        if n in self.tables_types:
            if n not in self.tables:
                self.tables[n] = gdb.parse_and_eval(self.tables_types[n][1])

    def get(self, api, _class):
        n = self.name(api, _class)
        self.load(n)
        if n in self.tables:
            return self.tables[n]
        return None

    def maximum(self, api, _class):
        n = self.name(api, _class)
        self.load(n)
        return int(self.tables[n]['maximum'])

    def object(self, id):
        if type(id) == gdb.Value:
            id = ident(id)
        if type(id) == tuple:
            api = id[0]
            _class = id[1]
            index = id[2]
        else:
            api = id.api()
            _class = id._class()
            index = id.index()
        n = self.name(api, _class)
        self.load(n)
        max = self.maximum(api, _class)
        if index >= max:
            raise IndexError('object index out of range (%d)' % (max))
        table_type = self.tables_types[n]
        expr = '(' + table_type[0] + '*)' + \
            table_type[1] + '.local_table[' + str(index) + ']'
        return gdb.parse_and_eval(expr)

    def is_string(self, api, _class):
        n = self.name(api, _class)
        self.load(n)
        if n in self.tables:
            if self.tables[n]['is_string']:
                return True
        return False

#
# Global info tables. These are global in the target.
#
information = infotables()

class ident:
    "An RTEMS object id with support for its bit fields."

    bits = [
        { 'index': (0, 15),
          'node':  (0, 0),
          'api':   (8, 10),
          'class': (11, 15) },
        { 'index': (0, 15),
          'node':  (16, 23),
          'api':   (24, 26),
          'class': (27, 31) } 
        ]

    OBJECT_16_BITS = 0
    OBJECT_31_BITS = 1

    api_labels = [
        'none',
        'internal',
        'classic',
        'posix',
        'itron'
        ]

    class_labels = {
        'internal' : ('threads',
                      'mutexes'),
        'classic' : ('none',
                     'tasks',
                     'timers',
                     'semaphores',
                     'message_queues',
                     'partitions',
                     'regions',
                     'ports',
                     'periods',
                     'extensions',
                     'barriers'),
        'posix' : ('none',
                   'threads',
                   'keys',
                   'interrupts',
                   'message_queue_fds',
                   'message_queues',
                   'mutexes',
                   'semaphores',
                   'condition_variables',
                   'timers',
                   'barriers',
                   'spinlocks',
                   'rwlocks'),
        'itron' : ('none',
                   'tasks',
                   'eventflags',
                   'mailboxes',
                   'message_buffers',
                   'ports',
                   'semaphores',
                   'variable_memory_pools',
                   'fixed_memory_pools')
        }
    
    def __init__(self, id):
        if type(id) != gdb.Value and type(id) != int and type(id) != unicode:
            raise TypeError('%s: must be gdb.Value, int, unicoded int' % (type(id)))
        if type(id) == int:
            id = gdb.Value(id)
        self.id = id
        if self.id.type.sizeof == 2:
            self.idSize = self.OBJECT_16_BITS
        else:
            self.idSize = self.OBJECT_31_BITS

    def get(self, field):
        if field in self.bits[self.idSize]:
            bits = self.bits[self.idSize][field]
            if bits[1] > 0:
                return (int(self.id) >> bits[0]) & ((1 << (bits[1] - bits[0] + 1)) - 1)
        return 0

    def value(self):
        return int(self.id)

    def index(self):
        return self.get('index')

    def node(self):
        return self.get('node')

    def api_val(self):
        return self.get('api')

    def class_val(self):
        return self.get('class')

    def api(self):
        api = self.api_val()
        if api < len(self.api_labels):
            return self.api_labels[api]
        return 'none'

    def _class(self):
        api = self.api()
        if api == 'none':
            return 'invalid'
        _class = self.class_val()
        if _class < len(self.class_labels[api]):
            return self.class_labels[api][_class]
        return 'invalid'

    def valid(self):
        return self.api() != 'none' and self._class() != 'invalid'

class name:
    """The Objects_Name can either be told what the name is or can take a
    guess."""

    def __init__(self, name, is_string = None):
        self.name = name
        if is_string == None:
            self.is_string = 'auto'
        else:
            if is_string:
                self.is_string = 'yes'
            else:
                self.is_string = 'no'

    def __str__(self):
        if self.is_string != 'yes':
            u32 = int(self.name['name_u32'])
            s = chr((u32 >> 24) & 0xff) + \
                chr((u32 >> 16) & 0xff) + chr((u32 >> 8) & 0xff) + \
                chr(u32 & 0xff)
            for c in range(0,4):
                if s[c] < ' ' or s[c] > '~':
                    s = None
                    break
            if s:
                return s
        return str(self.name['name_p'].dereference())

class control:
    """The Objects_Control structure."""

    def __init__(self, object):
        self.object = object
        self._id = ident(self.object['id'])

    def node(self):
        return self.object['Node']

    def id(self):
        return self.object['id']

    def name(self):
        is_string = information.is_string(self._id.api(), self._id._class())
        return str(name(self.object['name'], is_string))

class id_printer:
    """Print an object given the ID. Print using the struct display hint and an
    iterator."""

    class iterator:
        """Use an iterator for each field expanded from the id so GDB output
        is formatted correctly."""

        def __init__(self, id):
            self.id = id
            self.count = 0

        def __iter__(self):
            return self

        def next(self):
            self.count += 1
            if self.count == 1:
                return int(self.id.value())
            elif self.count == 2:
                return self.id.node()
            elif self.count == 3:
                return self.id.api()
            elif self.count == 4:
                return self.id._class()
            elif self.count == 5:
                return self.id.index()
            raise StopIteration

    def __init__(self, id):
        self.id = ident(id)

    def to_string(self):
        return ''

    @staticmethod
    def key(i):
        if i == 0:
            return 'id'
        elif i == 1:
            return 'node'
        elif i == 2:
            return 'api'
        elif i == 3:
            return 'class'
        elif i == 4:
            return 'index'
        return 'bad'

    def children(self):
        counter = itertools.imap (self.key, itertools.count())
        return itertools.izip (counter, self.iterator(self.id))

    def display_hint (self):
        return 'struct'

class name_printer:
    """Pretty printer for an object's name. It has to guess the type as no
    information is available to help determine it."""

    def __init__(self, name):
        self.name = name(name)

    def to_string(self):
        return gdb.Value(str(self.name))

class control_printer:

    class iterator:
        """Use an iterator for each field expanded from the id so GDB output
        is formatted correctly."""

        def __init__(self, object):
            self.object = object
            self.count = 0

        def __iter__(self):
            return self

        def next(self):
            self.count += 1
            if self.count == 1:
                return self.object.node()
            elif self.count == 2:
                return self.object.id()
            elif self.count == 3:
                return self.object.name()
            raise StopIteration

    def to_string(self):
        return ''

    def __init__(self, object):
        self.object = control(object)

    @staticmethod
    def key(i):
        if i == 0:
            return 'Node'
        elif i == 1:
            return 'id'
        elif i == 2:
            return 'name'
        return 'bad'

    def children(self):
        counter = itertools.imap (self.key, itertools.count())
        return itertools.izip (counter, self.iterator(self.object))

    def display_hint (self):
        return 'struct'
