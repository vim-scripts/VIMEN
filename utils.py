import os

def wrap_text(s):
  temp = []
  for item in s.split('\\'):
    item = item.replace('"', '\\"')
    item = item.replace('\n', '\\n')
    item = item.replace('\b', '\\b')
    item = item.replace('\r', '\\r')
    item = item.replace('\t', '\\t')
    temp.append(item)
  return '\\\\'.join(temp)
  
def wrap_string(s):
  return '"' + wrap_text(s) + '"'

def npath(s):
  return os.path.abspath(s)

def ipath(s):
  return os.path.abspath(s).replace('\\', '/')

def bpath(s):
  return os.path.basename(s)

try:
  oskill = os.kill
  def kill_process(pid):
    return oskill(pid, signal.SIGINT)
  print 'USE python kill'
except AttributeError:
  try:
    import win32api
    def kill_process(pid):
      h = win32api.OpenProcess(1, 0, pid)
      return win32api.TerminateProcess(h)
    print 'USE win32api kill simulator'
  except ImportError:
    try:
      import ctypes
      def kill_process(pid):
        h = ctypes.windll.kernel32.OpenProcess(1, 0, pid)
        return ctypes.windll.kernel32.TerminateProcess(h)
      print 'USE ctype kill simulator'
    except (ImportError, AttributeError):
      def kill_process(pid):
        print 'Please should kill process %d yourself' % pid
      print 'NO kill'

