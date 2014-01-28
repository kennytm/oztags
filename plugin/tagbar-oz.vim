"" If Vim does not recognize the Oz file type, uncomment the following first.
"" Otherwise Tagbar cannot work.
"
"au BufNewFile,BufRead *.oz set filetype=oz

if executable('oztags')
    let g:tagbar_type_oz = {
        \ 'ctagsbin': 'oztags',
        \ 'ctagsargs': '',
        \ 'sro': ',',
        \ 'kinds': [
            \ 'f:procedures',
            \ 'c:classes',
            \ 'm:methods:1',
        \ ],
        \ 'kind2scope': {'f': 'procedure', 'c': 'class', 'm': 'method'},
        \ 'scope2kind': {'procedure': 'f', 'class': 'c', 'method': 'm'},
    \ }
endif

