class Editor:
  PORT = 3220
  NAME = 'VIMEN'

  NONE_BUFID      = 0
  DEBUGGER_BUFID  = 1
  CONSOLE_BUFID   = 2
  THREAD_BUFID    = 3
  FRAME_BUFID     = 4
  WATCH_BUFID     = 5
  VARS_BUFID      = 6
  EDITOR_BUFID    = 20
  ANNO_BKPT     = (1, 'bkpt', '', 'bkpt.xpm', None, None)
  ANNO_BKPT0    = (2, 'bkpt0', '', 'bkpt0.xpm', None, None)
  ANNO_PC       = (3, 'pc', '', '', None, 0x08802f)
  ANNO_FRAME    = (4, 'frame', '', '', None, 0x0000a5)
