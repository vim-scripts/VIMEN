import socket, os
from logging import getLogger
from pyparsing import *

import config
import ibase
from utils import *

class Event(object):
  __slots__ = ['bufid', 'name', 'seqno', 'args']
  def __init__(self, bufid, name, seqno, args):
    self.bufid = bufid
    self.name = name
    self.seqno = seqno
    self.args = args

class Reply(object):
  __slots__ = ['seqno', 'args']
  def __init__(self, seqno, args):
    self.seqno = seqno
    self.args = args

class VimParserManager:
  def __init__(self):
    p_bufid = Word(nums + '-', nums)
    p_seqno = Word(nums)
    p_name = Word(alphas, alphanums)
    p_none = Literal("none")
    p_boolean = oneOf("T F")
    p_string = dblQuotedString
    p_number = Word(nums + '-', nums)
    p_pos = Word(nums) + '/' + Word(nums)
    p_except = Literal('!') + restOfLine
    p_arg = p_pos | p_none | p_except | p_boolean | p_string | p_number
    p_args = ZeroOrMore(p_arg) + LineEnd()
    p_reply = p_seqno + p_args
    p_event = p_bufid + ':' + p_name + '=' + p_seqno + p_args
    p_message = p_reply | p_event

    p_bufid.setParseAction(self.a_number)
    p_seqno.setParseAction(self.a_number)
    p_name.setParseAction(self.a_name)
    p_none.setParseAction(self.a_none)
    p_boolean.setParseAction(self.a_boolean)
    p_string.setParseAction(self.a_string)
    p_number.setParseAction(self.a_number)
    p_pos.setParseAction(self.a_pos)
    p_args.setParseAction(self.a_args)
    p_reply.setParseAction(self.a_reply)
    p_event.setParseAction(self.a_event)

    self.parser = p_message

  def a_number(self, s, l, t):
    return l, [int(t[0])]

  def a_name(self, s, l, t):
    return l, t[0]

  def a_string(self, s, l, t):
    return l, [eval(t[0])]

  def a_boolean(self, s, l, t):
    b = False
    if str(t[0]) == 'T':
      b = True
    return l, [b]

  def a_none(self, s, l, t):
    return l, [None]

  def a_except(self, s, l, t):
    return l, [str(t[1]).strip()]
  
  def a_pos(self, s, l, t):
    return l, [(int(t[0]), int(t[2]))]

  def a_args(self, s, l, t):
    return l, [t[:-1]]

  def a_reply(self, s, l, t):
    r = Reply(t[0], t[1])
    return l, [r]
    
  def a_event(self, s, l, t):
    e = Event(t[0], t[2], t[4], t[5])
    return l, [e]

def make_args(args):
  ca = []
  for arg in args:
    if arg is None:
      ca.append('none')
    elif isinstance(arg, tuple):
      assert len(arg) == 2
      assert isinstance(arg[0], int)
      assert isinstance(arg[1], int)
      ca.append('%d/%d' % (arg[0], arg[1]))
    elif isinstance(arg, int):
      ca.append('%d' % arg)
    elif isinstance(arg, str):
      ca.append(wrap_string(arg))
    else:
      assert 0
  return ' '.join(ca)

class Session(ibase.Session):
  def init(self):
    self.name = 'vimi'
    self.parser = VimParserManager().parser
    host = 'localhost'
    port = config.Editor.PORT
    name = config.Editor.NAME
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for i in xrange(5):
      try:
        s.bind(('localhost', port))
        self.servername = '%s:%d' % (name, port)
        break
      except socket.error:
        port += 1
        continue
    startup_filename = npath(os.path.dirname(__file__) + '/startup.vim')
    prog_name = 'vim -g'
    if os.name == 'nt':
      prog_name = 'gvim'
    program = '%s -nb:localhost:%d:%s --servername %s -S %s' % (
        prog_name, port, name, self.servername, startup_filename)
    getLogger('vimi.init').debug('starting %s ...' % program)
    self.pipe = os.popen(program)
    s.listen(1)
    getLogger('vimi.init').debug('waiting for editor in %s:%d' % (host, port))
    self.connection, addr = s.accept()
    self.rfile = self.connection.makefile('r')
    getLogger('vimi.init').debug('editor connected from %s:%d' % (addr[0], addr[1]))
    l = self.read().strip()
    assert l == ('AUTH %s' % name)
    while True: 
      l = self.read().strip()
      if l == '0:startupDone=0':
        break
    getLogger('vimi.init').debug('editor ready')
    self.block = False
  def read(self):
    try:
      r = self.rfile.readline()
    except:
      r = ''
    if r == '':
      self.ide.kill()
    return r
  def write(self, text):
    self.connection.send(text)
  def make_command(self, tag, name, bufid, *args, **kws):
    assert len(kws) == 0
    text = '%d:%s!%d %s\n' % (bufid, name, tag, make_args(args))
    return text
  def make_call(self, tag, name, bufid, *args, **kws):
    assert len(kws) == 0
    text = '%d:%s/%d %s\n' % (bufid, name, tag, make_args(args))
    return text
  def is_block_record(self, record):
    return False
  def get_reply_tag(self, record):
    if isinstance(record, Reply):
      return record.seqno
    else:
      return None
  def get_event_name(self, record):
    if isinstance(record, Event):
      return record.name
  def eval_expression(self, expr):
    s = 'vim --remote-expr %s --servername %s' % \
        (wrap_string(expr), self.servername)
    getLogger('vimi.vim').debug(s)
    p = os.popen(s)
    r = p.read()
    p.close()
    return r.rstrip()
  def send_control_command(self, cmd):
    s = 'vim --remote-send %s --servername %s' % \
        (wrap_string(cmd), self.servername)
    getLogger('vimi.vim').debug(s)
    p = os.popen(s)
    r = p.read()
    p.close()
    return r
  def input_text(self, msg, old_value, cancel_value):
    return self.eval_expression('inputdialog(%s, %s, %s)' % \
        (wrap_string(msg), wrap_string(old_value), wrap_string(cancel_value)))
  # commands
  def bring_to_front(self):
    self.command('raise', config.Editor.NONE_BUFID)
  def delay_exit(self, delay):
    self.command('setExitDelay', config.Editor.NONE_BUFID, delay)
  def close_buffer(self, bufid):
    self.command('close', bufid)
  def create_buffer(self, bufid):
    self.command('create', bufid)
  def mark_buffer_init_done(self, bufid):
    self.command('initDone', bufid)
  def edit_file_in_buffer(self, bufid, filename):
    self.command('editFile', bufid, npath(filename))
  def define_buffer_anno(self, bufid, anno):
    filename = anno[3]
    if len(filename) > 2:
      filename = npath(os.path.dirname(__file__) + '/' + filename)
    self.command('defineAnnoType', bufid, anno[0], anno[1], anno[2], filename, anno[4], anno[5])
  def insert_buffer_anno(self, bufid, anno_id, anno, line):
    type_id = anno[0]
    self.command('addAnno', bufid, anno_id, type_id, (line, 1), 1)
  def remove_buffer_anno(self, bufid, anno_id):
    self.command('removeAnno', bufid, anno_id)
  def start_buffer_atomic(self, bufid):
    self.command('startAtomic', bufid)
  def end_buffer_atomic(self, bufid):
    self.command('endAtomic', bufid)
  def bind_buffer(self, bufid, filename, make_current=True):
    filename = npath(filename)
    if make_current:
      self.command('setBufferNumber', bufid, filename)
    else:
      self.command('putBufferNumber', bufid, filename)
  def set_buffer_owner(self, bufid, is_owner):
    self.command('netbeansBuffer', bufid, is_owner)
  def save_buffer(self, bufid):
    self.command('save', bufid)
  def set_cursor(self, bufid, line, col):
    self.command('setDot', bufid, (line, col))
  def set_buffer_filename(self, bufid, filename):
    self.command('setFullName', bufid, filename)
  def set_buffer_dirty(self, bufid, is_dirty):
    self.command('setModified', bufid, is_dirty)
  def set_buffer_title(self, bufid, title):
    self.command('setTitle', bufid, title)
  def set_buffer_visible(self, bufid, is_visible):
    self.command('setVisible', bufid, is_visible)
  def enable_buffer_listen(self, bufid, is_enabled):
    if is_enabled:
      self.command('startDocumentListen', bufid)
    else:
      self.command('stopDocumentListen', bufid)
  def protect_buffer_text(self, bufid, offset, len, is_protected):
    if is_protected:
      self.command('guard', bufid, offset, len)
    else:
      self.command('unguard', bufid, offset, len)  
  def show_balloon(self, text):
    self.command('showBalloon', 0, text)
  def echo(self, text, type):
    if type is None:
      self.send_control_command('<ESC>:echo %s<CR>' % wrap_string(text))
    else:
      self.send_control_command('<ESC>:echohl WarningMsg<CR>')
      self.send_control_command('<ESC>:echo %s | echohl None<CR>' % wrap_string(text))
  # functions
  def get_cursor(self):
    record = self.call('getCursor', config.Editor.NONE_BUFID)
    bufid, line, col, offset = record.args
    return bufid, line, col, offset
  def get_buffer_length(self, bufid):
    record = self.call('getLength', bufid)
    l = record.args[0]
    return int(l)
  def is_buffer_dirty(self, bufid):
    record = self.call('getModified', bufid)
    return record.args[0] == 1
  def get_buffer_text(self, bufid):
    record = self.call('getText', bufid)
    return record.args[0]
  def insert_buffer_text(self, bufid, offset, text):
    record = self.call('insert', bufid, offset, text)
    return len(record.args) == 0
  def remove_buffer_text(self, bufid, offset, text):
    record = self.call('remove', bufid, offset, len)
    return len(record.args) == 0
  def save_and_exit(self):
    record = self.call('saveAndExit', config.Editor.NONE_BUFID, bufid)
    return len(record.args) == 0

  # event handlers
  def on_keyAtPos(self, record):
    key, offset, pos = record.args
    if key == 'd':
      self.ide.start_debugging()
    if key == 'g':
      self.ide.go_or_continue()
    elif key == 'G':
      self.ide.stop_debugger()
    elif key == 'b':
      self.ide.toggle_bkpt(record.bufid, pos[0])
    elif key == 'n':
      self.ide.step_over()
    elif key == 'N':
      self.ide.step_into()
    elif key == 'r':
      self.ide.step_return()
    elif key == 'u':
      self.ide.step_to_line(record.bufid, pos[0])
    elif key == 'p':
      self.ide.change_program_param()
  def on_balloonText(self, record):
    text = record.args[0]
    self.ide.show_tooltip_value(text)
  def on_fileOpened(self, record):
    filename = record.args[0]
    if os.path.isfile(filename):
      self.ide.accept_buffer(filename)
