from threading import Condition, Thread
from logging import getLogger
import vimi, gdbi, config
from utils import *
import os

class MessageQueue(object):
  def __init__(self, capacity, lock = None):
    self.__capacity = capacity 
    self.__queue = []
    if lock is None:
      self.__cond = Condition()
    else:
      self.__cond = lock
  def clear(self, item):
    self.__cond.acquire()
    self.__queue.insert(0, item)
    del self.__queue[1:]
    self.__cond.notify()
    self.__cond.release()
  def put(self, item):
    self.__cond.acquire()
    while len(self.__queue) >= self.__capacity:
      self.__cond.wait()
    self.__queue.append(item)
    self.__cond.notify()
    self.__cond.release()
  def peek(self):
    self.__cond.acquire()
    while len(self.__queue) == 0:
      self.__cond.wait()
    item = self.__queue.pop(0)
    self.__cond.notify()
    self.__cond.release()
    return item

class ITEM:
  def __init__(self, filename, line, id):
    self.id        = id
    self.filename  = filename
    self.line      = line
    self.anno_id   = 0

class IDE(object):

  def __init__(self, program):
    self.program = ipath(program)
    self.params = ''
    self.__msgq = MessageQueue(2)

    # session instance
    self.vim = vimi.Session(self)
    self.gdb = None

    # internal data
    self.pc     = None
    self.bufs   = [] # [(filename, bufid) ... ]
    self.bkpts  = {} # (filename, line) -> ITEM

    self.max_anid  = 0
    self.max_bufid = config.Editor.EDITOR_BUFID

  def open(self):
    self.vim.open()
    bufid = config.Editor.DEBUGGER_BUFID
    self.vim.set_buffer_filename(bufid, '*dbg*')
    text = 'Press <F5> to start debugging "%s".\n' % self.program
    self.vim.insert_buffer_text(bufid, 0, text)
    self.vim.set_buffer_dirty(bufid, True)
    self.vim.set_buffer_owner(bufid, True)
    self.vim.mark_buffer_init_done(bufid)

    # self.vim.create_buffer(config.Editor.THREAD_BUFID)
    # self.vim.create_buffer(config.Editor.FRAME_BUFID)
    # self.vim.create_buffer(config.Editor.WATCH_BUFID)

  def kill(self):
    self.__msgq.clear(None)
    try:
      self.gdb.results.cancel()
    except:
      pass
    try:
      self.vim.results.cancel()
    except:
      pass

  def put_msg(self, session, msg):
    self.__msgq.put((session, msg))

  def stop_debugger(self):
    try:
      self.clear_pc()
    except:
      pass

    if self.gdb is not None:
      getLogger('core').debug('stopping debugger...')
      try:
        self.gdb.kill()
      except:
        pass
      self.gdb = None
  
  def echo(self, text, type=None):
    self.vim.echo(text, type)
    
  def stop_editor(self):
    if self.vim is not None:
      getLogger('core').debug('stopping editor...')
      try:
        self.vim.kill()
      except:
        pass
      self.vim = None

  def serve_for_ever(self):
    while True:
      getLogger('core').debug('peeking message from queue...')
      msg = self.__msgq.peek()
      if msg is None:
        break
      else:
        pass

      assert isinstance(msg, tuple)
      assert len(msg) == 2

      session, record = msg
      en = session.get_event_name(record)
      if en is None:
        continue
      fn = 'on_' + en
      if not hasattr(session, fn):
        getLogger('core').debug('unknown event name "%s".' % en)
        continue
      func = getattr(session, fn)
      func(record)

    try:
      self.stop_debugger()
    except:
      pass

  def get_buf_filename(self, bufid):
    for buf in self.bufs:
      if buf[1] == bufid:
        return buf[0]

  def get_bufid(self, filename):
    filename = ipath(filename)
    for buf in self.bufs:
      if buf[0] == filename:
        return buf[1]
    return 0

  def alloc_anid(self):
    self.max_anid += 1
    return self.max_anid

  def alloc_bufid(self):
    self.max_bufid += 1
    return self.max_bufid

  def log(self, text):
    pass
    #l = self.vim.get_buffer_length(config.Editor.DEBUGGER_BUFID)
    #self.vim.insert_buffer_text(config.Editor.DEBUGGER_BUFID, l, text)
    
  def start_debugging(self):
    self.stop_debugger()
    self.gdb = gdbi.Session(self)
    self.gdb.open()
    self.gdb.set_new_console()
    self.gdb.exec_file(self.program)
    if self.params != '':
      self.gdb.exec_arguments(self.params)
    self.clear_pc()

  def init_buffer(self, bufid):
    self.vim.define_buffer_anno(bufid, config.Editor.ANNO_BKPT)
    self.vim.define_buffer_anno(bufid, config.Editor.ANNO_BKPT0)
    self.vim.define_buffer_anno(bufid, config.Editor.ANNO_PC)
    self.vim.define_buffer_anno(bufid, config.Editor.ANNO_FRAME)
    self.vim.mark_buffer_init_done(bufid)
    
  def open_file_in_editor(self, filename):
    filename = ipath(filename)
    bufid = self.get_bufid(filename)
    if bufid == 0:
      bufid = self.alloc_bufid()
      self.vim.edit_file_in_buffer(bufid, filename)
      self.bufs.append((filename, bufid))
      self.init_buffer(bufid)
    return bufid
  
  def accept_buffer(self, filename):
    if filename.endswith('*'):
      return 0
    filename = ipath(filename)
    bufid = self.get_bufid(filename)
    if bufid == 0:
      bufid = self.alloc_bufid()
      self.bufs.append((filename, bufid))
      self.vim.bind_buffer(bufid, filename)
      self.init_buffer(bufid)
    return bufid

  def go_or_continue(self):
    if self.gdb is None:
      self.start_debugging()
      if len(self.bkpts) > 0:
        if self.reaply_bkpts() == 0:
          self.gdb.break_at_main()
      else:
        self.gdb.break_at_main()
      self.gdb.exec_run()
    else:
      self.clear_pc()
      self.gdb.exec_continue()

  def set_pc(self, filename, line):
    self.clear_pc()
    filename = ipath(filename)
    anno_id = self.alloc_anid()
    bufid = self.open_file_in_editor(filename)
    self.pc = (filename, line, anno_id)
    self.vim.insert_buffer_anno(bufid, anno_id, config.Editor.ANNO_PC, line)
    self.vim.set_cursor(bufid, line, 0)
    self.vim.bring_to_front()

  def clear_pc(self):
    if self.pc is None:
      return
    filename, line, anno_id = self.pc
    self.pc = None
    bufid = self.get_bufid(filename)
    if bufid == 0:
      return
    self.vim.remove_buffer_anno(bufid, anno_id)

  def update_bkpt(self, bkpt):
    bufid = self.get_bufid(bkpt.filename)
    if bufid == 0:
      return
    if bkpt.anno_id != 0:
      self.vim.remove_buffer_anno(bufid, bkpt.anno_id)
    if bkpt.id != 0:
      self.vim.insert_buffer_anno(bufid, bkpt.anno_id, config.Editor.ANNO_BKPT, bkpt.line)
    else:
      bkpt.anno_id = self.alloc_anid()
      self.vim.insert_buffer_anno(bufid, bkpt.anno_id, config.Editor.ANNO_BKPT0, bkpt.line)

  def reaply_bkpts(self):
    for bkpt in self.bkpts.values():
      bkpt.id = self.gdb.break_insert(bkpt.filename, bkpt.line)
      self.update_bkpt(bkpt)

  def toggle_bkpt(self, bufid, line):
    filename = self.get_buf_filename(bufid)
    try:
      bkpt = self.bkpts.pop((filename, line))
      if bkpt.id != 0:
        self.gdb.break_remove(bkpt.id)
      self.vim.remove_buffer_anno(bufid, bkpt.anno_id)
      return None
    except KeyError, err:
      id = 0
      if self.gdb is not None:
        id = self.gdb.break_insert(filename, line)
        if id == 0:
          anno = config.Editor.ANNO_BKPT0
        else:
          anno = config.Editor.ANNO_BKPT
      else:
        anno = config.Editor.ANNO_BKPT0
      bkpt = ITEM(filename, line, id)
      self.bkpts[(filename, line)] = bkpt
      bkpt.anno_id = self.alloc_anid()
      self.vim.insert_buffer_anno(bufid, bkpt.anno_id, anno, line)
      return bkpt

  def step_over(self):
    if self.gdb is not None:
      self.clear_pc()
      self.gdb.exec_next()

  def step_into(self):
    if self.gdb is not None:
      self.clear_pc()
      self.gdb.exec_step()

  def step_return(self):
    if self.gdb is not None:
      self.clear_pc()
      r = self.gdb.exec_return()
      if r is not None:
        self.set_pc(r[0], r[1])

  def step_to_line(self, bufid, line):
    filename = self.get_buf_filename(bufid)
    if (self.gdb is not None) and (filename is not None):
      self.clear_pc()
      self.gdb.exec_until(filename, line)

  def show_tooltip_value(self, expression):
    if self.gdb is not None:
      value = self.gdb.evaluate(expression)
      if value is not None:
        self.vim.show_balloon(value)

  def change_program_param(self):
    r = self.vim.input_text('Input New Params', self.params, '{cancel}')
    if r != '{cancel}':
      self.params = r
      if self.gdb is not None:
        self.gdb.exec_arguments(self.params)

def main():
  import sys
  from logging import basicConfig, DEBUG

  logfile = npath(os.path.dirname(__file__) + '/vimen.log')
  index = 1
  for arg in sys.argv[1:]:
    if not arg.startswith('-'):
      break
    elif arg.startswith('-l'):
      logfile = arg[2:]
    elif arg.startswith('-nl'):
      logfile = None
    else:
      print_help()
      sys.exit(1)
    index += 1

  if logfile is None:
    basicConfig(level=DEBUG,
        format='# %(name)-9s %(levelname)-8s %(message)s')
  else:
    basicConfig(level=DEBUG,
        format='# %(name)-9s %(levelname)-8s %(message)s',
        filename=logfile,
        filemode='w')

  ide = IDE(sys.argv[index])
  ide.open()
  ide.serve_for_ever()
  
if __name__ == '__main__':
  main()

