import os
import traceback
from logging import getLogger
from pyparsing import *
import ibase
import config
from utils import *

class ResultRecord:
  __slots__ = ['token', 'class_', 'results']
  def __init__(self, token, class_, results):
    self.token = token
    self.class_ = class_
    self.results = results

class AsyncRecord:
  __slots__ = ['flag', 'token', 'class_', 'results']
  def __init__(self, flag, token, class_, results):
    self.flag = flag
    self.token = token
    self.class_ = class_
    self.results = results

class StreamRecord:
  __slots__ = ['flag', 'text']
  def __init__(self, flag, text):
    self.flag = flag
    self.text = text

class GDBParserManager:
  def __init__(self):
    p_token = Optional(Word(nums))
    p_symbol = Word(alphas, alphanums + '.-')
    p_string = dblQuotedString
    p_value = Forward()
    p_list0 = Literal('[]')
    p_list = '[' + delimitedList(p_value) + ']'
    p_tuple0 = Literal('{}')
    p_result = p_symbol + '=' + p_value
    p_tuple = '{' + delimitedList(p_result) + '}'
    p_value << (p_string | p_list0 | p_list | p_tuple0 | p_tuple)
    p_result_class = oneOf('done running connected error exit')
    p_async_class = oneOf('stopped')
    p_results = ZeroOrMore(Literal(',') + p_result)
    p_prompt = Literal("(gdb)") + LineEnd()

    p_result_record = Optional(p_token) \
        + Literal('^') + p_result_class \
        + p_results \
        + LineEnd()

    p_async_record = Optional(p_token) \
        + (Literal('*') | Literal('+') | Literal('=')) + p_async_class \
        + p_results \
        + LineEnd()

    p_stream_record = Optional(Literal('~') | Literal('@') | Literal('&')) + p_string
    p_out_of_band_record = p_async_record | p_stream_record
    p_entry = p_out_of_band_record | p_result_record | p_prompt

    p_token.setParseAction(self.a_token)
    p_symbol.setParseAction(self.a_symbol)
    p_string.setParseAction(self.a_string)
    p_list0.setParseAction(self.a_list0)
    p_list.setParseAction(self.a_list)
    p_tuple0.setParseAction(self.a_tuple0)
    p_tuple.setParseAction(self.a_tuple)
    p_results.setParseAction(self.a_results)
    p_result.setParseAction(self.a_result)
    p_result_record.setParseAction(self.a_result_record)
    p_async_record.setParseAction(self.a_async_record)
    p_stream_record.setParseAction(self.a_stream_record)
    p_prompt.setParseAction(self.a_prompt)

    self.parser = p_entry
    
  def a_string(self, s, l, t):
    return l, [eval(t[0])]

  def a_symbol(self, s, l, t):
    return l, t[0]
    
  def a_token(self, s, l, t):
    return l, [int(t[0])]

  def a_list0(self, s, l, t):
    return l, [[]]

  def a_list(self, s, l, t):
    return l, [t[1:-1]]

  def a_result(self, s, l, t):
    return l, [(t[0], t[2])]

  def a_tuple0(self, s, l, t):
    return l, [{}]

  def a_tuple(self, s, l, t):
    d = dict(t[1:-1])
    return l, [d]

  def a_results(self, s, l, t):
    d = {}
    tl = len(t) / 2
    for i in xrange(tl):
      item = t[i * 2 + 1]
      d[str(item[0])] = item[1]
    return l, [d]

  def a_result_record(self, s, l, t):
    if isinstance(t[0], int):
      return l, [ResultRecord(t[0], t[2], t[3])]
    else:
      return l, [ResultRecord(0, t[1], t[2])]

  def a_async_record(self, s, l, t):
    if isinstance(t[0], int):
      return l, [AsyncRecord(t[0], t[1], t[2], t[3])]
    else:
      return l, [AsyncRecord(0, t[0], t[1], t[2])]

  def a_stream_record(self, s, l, t):
    if len(t) == 1:
      return l, [StreamRecord('', t[0])]
    elif len(t) == 2:
      return l, [StreamRecord(t[0], t[1])]
    else:
      assert 0

  def a_prompt(self, s, l, t):
    return l, [None]

class Session(ibase.Session):
  def init(self):
    self.name = 'gdbi'
    self.parser = GDBParserManager().parser
    program = 'gdb --interpreter=mi --quiet'
    getLogger('gdbi.init').debug('starting %s ...' % (program))
    self.stdin, self.stdout = os.popen2(program)
    while True:
      r = self.stdout.readline()
      if r == '':
        getLogger('gdbi.init').error('FAILD IN starting %s' % program)
        break
      if r.strip() == '(gdb)':
        break
      else:
        getLogger('gdbi.read').debug(repr(r))
    getLogger('gdbi.init').debug('gdb ready')
  def read(self):
    try:
      r = self.stdout.readline()
      try:
        self.ide.log(r)
      except:
        traceback.print_exc()
      return r
    except:
      return ''
  def write(self, text):
    self.stdin.write(text)
  def make_command(self, *args, **kws):
    return self.make_call(*args, **kws)
  def make_call(self, tag, name, *args, **kws):
    assert len(args) < 2
    assert len(kws) == 0
    if len(args) == 0:
      text = '%d%s\n' % (tag, name)
    else:
      text = '%d%s%s\n' % (tag, name, args[0])
    return text
  def is_block_record(self, record):
    if isinstance(record, ResultRecord):
      return (record.class_ in ['running'])
  def get_reply_tag(self, record):
    if isinstance(record, ResultRecord):
      return record.token
    else:
      return None
  def get_event_name(self, record):
    if isinstance(record, AsyncRecord):
      return record.class_
  def kill(self, force = False):
    if self.block:
      getLogger('gdbi').debug('killing process')
      pid = self.proc.pid
      getLogger('gdbi').debug('killing process %d' % pid)
      kill_process(pid)
    else:
      getLogger('gdbi').debug('sending exit command')
      self.command('-gdb-exit')
    self.stdin = self.stdout = None
  def set_new_console(self, mode=True):
    if mode == True:
      self.call('-gdb-set new-console on')
    else:
      self.call('-gdb-set new-console off')
  def exec_file(self, filename):
    record = self.call('-file-exec-and-symbols %s' % ipath(filename))
    if record is None:
      return False
    else:
      return record.class_ == 'done'
  def exec_arguments(self, args):
    record = self.call('-exec-arguments %s' % args)
    if record is None:
      return False
    else:
      return record.class_ == 'done'
  def exec_continue(self):
    record = self.call('-exec-continue')
    if record is None:
      return False
    else:
      return record.class_ == 'running'
  def exec_next(self):
    record = self.call('-exec-next')
    if record is None:
      return False
    else:
      return record.class_ == 'running'
  def exec_step(self):
    record = self.call('-exec-step')
    if record is None:
      return False
    else:
      return record.class_ == 'running'
  def exec_return(self):
    record = self.call('-exec-return')
    try:
      return record.results['frame']['file'], int(record.results['frame']['line'])
    except:
      return None
  def exec_until(self, filename, line):
    record = self.call('-exec-until %s:%d' % (bpath(filename), line))
    if record is None:
      return False
    else:
      return record.class_ == 'running'
  def exec_run(self):
    record = self.call('-exec-run')
    if record is None:
      return False
    else:
      return record.class_ == 'running'
  def break_insert(self, filename, line):
    record = self.call('-break-insert %s:%d' % (bpath(filename), line))
    if (record is not None) and (record.class_ == 'done'):
      return int(record.results['bkpt']['number'])
    else:
      return 0
  def break_at_main(self):
    record = self.call('-break-insert -t main')
    if (record is not None) and (record.class_ == 'done'):
      return int(record.results['bkpt']['number'])
    else:
      return 0
  def break_remove(self, id):
    record = self.call('-break-delete %d' % id)
    if record is None:
      return False
    else:
      return record.class_ == 'done'
  def evaluate(self, expr):
    record = self.call('-data-evaluate-expression %s' % wrap_string(expr))
    if (record is not None) and (record.class_ == 'done'):
      return record.results['value']
    else:
      return None
  def on_stopped(self, record):
    reason = record.results.get('reason')
    if self.block:
      self.block = False
      getLogger(self.name).debug('UNBLOCKED')
      self.ide.echo('DEBUGGER READY')
    try:
      filename = record.results['frame']['file']
      line = int(record.results['frame']['line'])
      self.ide.set_pc(filename, line)
    except KeyError:
      self.ide.clear_pc()
      if reason is not None:
        getLogger('gdbi').debug('stopped for the reason: %s' % reason)
        if reason == 'exited-normally':
          self.ide.stop_debugger()
