from threading import Thread, RLock, Condition
from logging import getLogger
from pyparsing import ParseException

class Session:
  def __init__(self, ide):
    self.name = None
    self.max_tag = 0
    self.ide = ide
    self.block = False
    self.results = Results()
    self.lock = RLock()
    self.init()
  def open(self):
    self.thr = Thread(target=self.serve)
    self.thr.start()
  def serve(self):
    while True:
      r = self.read()
      if r == '':
        getLogger(self.name + '.recv').debug('<EOF>')
        break
      getLogger(self.name + '.recv').debug(repr(r))
      record = self.parse(r)
      if record is None:
        continue
      tag = self.get_reply_tag(record)
      if tag is None:
        self.ide.put_msg(self, record)
      else:
        self.results.put((self, tag), record)
    getLogger(self.name).debug(self.name + ' down')
  def command(self, *args, **kws):
    if not self.block:
      tag = self.alloc_tag()
      text = self.make_command(tag, *args, **kws)
      self.transfer(text)
      return tag
    else:
      return 0
  def call(self, *args, **kws):
    tag = self.acall(*args, **kws)
    return self.wait(tag)
  def acall(self, *args, **kws):
    if not self.block:
      tag = self.alloc_tag()
      text = self.make_call(tag, *args, **kws)
      self.transfer(text)
      return tag
    else:
      return 0
  def transfer(self, text):
    self.write(text)
    getLogger(self.name + '.send').debug(repr(text))
  def wait(self, tag):
    if tag != 0:
      getLogger(self.name).debug('waiting reply of %d' % tag)
      record = self.results.get((self, tag))
      getLogger(self.name).debug('got reply of %d' % tag)
      if self.is_block_record(record):
        getLogger(self.name).debug('BLOCKED')
        try:
          self.ide.echo('DEBUGGER BUSY')
        except:
          pass
        self.block = True
      return record
    else:
      return None
  def alloc_tag(self):
    self.lock.acquire()
    self.max_tag += 1
    tag = self.max_tag
    self.lock.release()
    return tag
  def parse(self, content):
    try:
      toks = self.parser.parseString(content)
      return toks[0]
    except ParseException, err:
      text = content[err.loc:min(err.loc+5, len(content))]
      getLogger(self.name + '.p').warning('PARSE ERROR: %s near %s' % (err.msg, repr(text)))
    return None
  def init(self):
    pass
  def read(self):
    pass
  def write(self, text):
    pass
  def make_command(self, tag, name, *args, **kws):
    pass
  def make_call(self, tag, name, *args, **kws):
    pass
  def is_block_record(self, record):
    pass
  def get_reply_tag(self, record):
    pass
  def get_event_name(self, record):
    pass

class Results:
  def __init__(self):
    self.__values = {}
    self.__cond = Condition()
    self.__cancel = False
  def cancel(self):
    self.__cond.acquire()
    self.__cancel = True
    self.__cond.notify()
    self.__cond.release()
  def put(self, key, value):
    self.__cond.acquire()
    self.__values[key] = value
    self.__cond.notify()
    self.__cond.release()
  def get(self, key):
    self.__cond.acquire()
    while not (self.__cancel or self.__values.has_key(key)):
      self.__cond.wait()
    r = self.__values.pop(key)
    self.__cond.release()
    return r
