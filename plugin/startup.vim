function VimenLayout()
  let src_bn = bufnr('%')
  let dbg_bn = bufnr('*dbg*')  
  " let thr_bn = bufnr('*thr*')
  " let frm_bn = bufnr('*frm*')
  " let wat_bn = bufnr('*wat*')
  only
  exec "buffer " src_bn
  sp #
endfunction

set ballooneval
map <F5> <F21>g    " run
map <S-F5> <F21>G  " stop
map <F6> <F21>b    " toggle breakpoint
map <F7> <F21>N    " step-into
map <S-F7> <F21>r  " step-out
map <F8> <F21>n    " step-over
map <C-F8> <F21>u  " run to
map <F12> <F21>p   " set program param

